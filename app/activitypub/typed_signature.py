"""Typed HTTP and LD signature utilities using Python 3.13 features"""
from __future__ import annotations
from typing import Optional, Dict, Any, Literal, TypedDict, Protocol, cast
from datetime import datetime, timedelta
import base64
import json
from urllib.parse import urlparse
from email.utils import formatdate

import arrow
import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from dateutil import parser
from flask import Request, current_app
from furl import furl
from pyld import jsonld
from sqlalchemy import text

from app import db, httpx_client
from app.constants import DATETIME_MS_FORMAT
from app.models_typed import TypedUser, TypedCommunity, TypedInstance
from app.models_typed_activitypub import TypedActivityPubLog, TypedSendQueue
from app.models_typed_relations import TypedCommunityMember
from app.utils import get_task_session
from app.federation.types import ActivityObject, HttpUrl, PrivateKey, PublicKey

# Type aliases
type KeyId = str
type Algorithm = Literal["rsa-sha256", "hs2019"]
type HttpMethod = Literal["get", "post", "GET", "POST"]
type SignatureBytes = bytes
type Base64String = str

# TypedDict definitions
class HttpSignatureDetails(TypedDict):
    """Details of an HTTP signature"""
    algorithm: Algorithm
    headers: list[str]
    signature: SignatureBytes
    keyid: KeyId


class LDSignatureOptions(TypedDict):
    """JSON-LD signature options"""
    context: str | list[str] | dict[str, Any]
    creator: str
    created: str
    signatureValue: Optional[str]
    type: Optional[str]


class VerificationError(Exception):
    """There was an error with verifying the signature"""
    pass


class VerificationFormatError(VerificationError):
    """There was an error with the format of the signature (not if it is valid)"""
    pass


class RsaKeys:
    """RSA key generation utilities"""
    
    @classmethod
    def generate_keypair(cls) -> tuple[PrivateKey, PublicKey]:
        """Generates a new RSA keypair"""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        private_key_serialized = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")
        public_key_serialized = (
            private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("ascii")
        )
        return private_key_serialized, public_key_serialized


class HttpSignature:
    """Allows for calculation and verification of HTTP signatures"""
    
    @classmethod
    def calculate_digest(cls, data: bytes, algorithm: str = "sha-256") -> str:
        """Calculates the digest header value for a given HTTP body"""
        if algorithm == "sha-256":
            digest = hashes.Hash(hashes.SHA256())
            digest.update(data)
            return "SHA-256=" + base64.b64encode(digest.finalize()).decode("ascii")
        else:
            raise ValueError(f"Unknown digest algorithm {algorithm}")
    
    @classmethod
    def headers_from_request(cls, request: Request, header_names: list[str]) -> str:
        """Creates the to-be-signed header payload from a Flask request"""
        headers: Dict[str, str] = {}
        for header_name in header_names:
            if header_name == "(request-target)":
                value = f"{request.method.lower()} {request.path}"
            elif header_name == '(created)':
                value = signature_part(request.headers.get('Signature', ''), 'created')
            elif header_name == '(expires)':
                value = signature_part(request.headers.get('Signature', ''), 'expires')
            elif header_name == "content-type":
                value = request.headers.get("Content-Type", "")
            elif header_name == "content-length":
                value = request.headers.get("Content-Length", "")
            else:
                value = request.headers.get(header_name.replace("-", "_").upper(), "")
            headers[header_name] = value
        return "\n".join(f"{name.lower()}: {value}" for name, value in headers.items())
    
    @classmethod
    def parse_signature(cls, signature: str) -> HttpSignatureDetails:
        """Parse HTTP signature header into components"""
        bits: Dict[str, str] = {}
        for item in signature.split(","):
            name, value = item.split("=", 1)
            value = value.strip('"')
            bits[name.lower()] = value
        try:
            signature_details = HttpSignatureDetails(
                headers=bits["headers"].split(),
                signature=base64.b64decode(bits["signature"]),
                algorithm=cast(Algorithm, bits["algorithm"]),
                keyid=bits["keyid"],
            )
        except KeyError as e:
            key_names = " ".join(bits.keys())
            raise VerificationError(
                f"Missing item from details (have: {key_names}, error: {e})"
            )
        return signature_details
    
    @classmethod
    def compile_signature(cls, details: HttpSignatureDetails) -> str:
        """Compile signature details into HTTP signature header value"""
        value = f'keyId="{details["keyid"]}",headers="'
        value += " ".join(h.lower() for h in details["headers"])
        value += '",signature="'
        value += base64.b64encode(details["signature"]).decode("ascii")
        value += f'",algorithm="{details["algorithm"]}"'
        return value
    
    @classmethod
    def verify_signature(
        cls,
        signature: SignatureBytes,
        cleartext: str,
        public_key: PublicKey,
    ) -> None:
        """Verify RSA signature against cleartext using public key"""
        public_key_instance: rsa.RSAPublicKey = cast(
            rsa.RSAPublicKey,
            serialization.load_pem_public_key(public_key.encode("ascii")),
        )
        try:
            public_key_instance.verify(
                signature,
                cleartext.encode("ascii"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except InvalidSignature:
            raise VerificationError("Signature mismatch")
    
    @classmethod
    def verify_request(
        cls, 
        request: Request, 
        public_key: PublicKey, 
        skip_date: bool = False
    ) -> bool:
        """Verifies that the request has a valid signature for its body"""
        # Verify body digest
        if "digest" in request.headers:
            expected_digest = HttpSignature.calculate_digest(request.data)
            if request.headers["digest"] != expected_digest:
                raise VerificationFormatError("Digest is incorrect")
        
        # Verify date header
        if "date" in request.headers and not skip_date:
            header_date = parse_http_date(request.headers["date"])
            if abs((arrow.utcnow() - header_date).total_seconds()) > 3600:
                raise VerificationFormatError("Date is too far away")
        
        # Get the signature details
        if "signature" not in request.headers:
            raise VerificationFormatError("No signature header present")
        signature_details = cls.parse_signature(request.headers["signature"])
        
        # Reject unknown algorithms
        if (
            signature_details["algorithm"] != "rsa-sha256"
            and signature_details["algorithm"] != "hs2019"
        ):
            raise VerificationFormatError("Unknown signature algorithm")
        
        # Create the signature payload
        headers_string = cls.headers_from_request(request, signature_details["headers"])
        cls.verify_signature(
            signature_details["signature"],
            headers_string,
            public_key,
        )
        return True
    
    @classmethod
    def signed_request(
        cls,
        uri: HttpUrl,
        body: Optional[ActivityObject],
        private_key: PrivateKey,
        key_id: KeyId,
        content_type: str = "application/activity+json",
        method: HttpMethod = "post",
        timeout: int = 5,
    ) -> httpx.Response:
        """Performs a request to the given path, with a document, signed as an identity"""
        if "://" not in uri:
            raise ValueError("URI does not contain a scheme")
        
        # Create the core header field set
        uri_parts = urlparse(uri)
        date_string = http_date()
        headers: Dict[str, str] = {
            "(request-target)": f"{method.lower()} {uri_parts.path}",
            "Host": uri_parts.hostname or "",
            "Date": date_string,
        }
        
        # If we have a body, add a digest and content type
        body_bytes: bytes
        if body is not None:
            if '@context' not in body:
                body['@context'] = default_context()
            body_bytes = json.dumps(body).encode("utf8")
            headers["Digest"] = cls.calculate_digest(body_bytes)
            headers["Content-Type"] = content_type
        else:
            body_bytes = b""
        
        # GET requests get implicit accept headers added
        if method.lower() == "get":
            headers["Accept"] = "application/ld+json"
        
        # Sign the headers
        signed_string = "\n".join(
            f"{name.lower()}: {value}" for name, value in headers.items()
        )
        private_key_instance: rsa.RSAPrivateKey = cast(
            rsa.RSAPrivateKey,
            serialization.load_pem_private_key(
                private_key.encode("ascii"),
                password=None,
            ),
        )
        signature = private_key_instance.sign(
            signed_string.encode("ascii"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        headers["Signature"] = cls.compile_signature(
            HttpSignatureDetails(
                keyid=key_id,
                headers=list(headers.keys()),
                signature=signature,
                algorithm="rsa-sha256",
            )
        )
        
        headers["User-Agent"] = f'PieFed/{current_app.config["VERSION"]}; +https://{current_app.config["SERVER_NAME"]}'
        
        # Send the request with all those headers except the pseudo one
        del headers["(request-target)"]
        
        try:
            response = httpx_client.request(
                method,
                uri,
                headers=headers,
                data=body_bytes,
                timeout=timeout,
                follow_redirects=method.upper() == "GET",
            )
        except httpx.HTTPError as ex:
            raise httpx.HTTPError(f"HTTP Exception for {ex.request.url} - {ex}") from None
        
        if (
            method.upper() == "POST"
            and 400 <= response.status_code < 500
            and response.status_code != 404
        ):
            raise ValueError(
                f"POST error to {uri}: {response.status_code} {response.content!r}"
            )
        
        return response


class LDSignature:
    """Creates and verifies signatures of JSON-LD documents"""
    
    @classmethod
    def verify_signature(cls, document: Dict[str, Any], public_key: PublicKey) -> None:
        """Verifies a document"""
        try:
            # Strip out the signature from the incoming document
            signature = document.pop("signature")
            # Create the options document
            options: LDSignatureOptions = {
                "context": "https://w3id.org/security/v1",
                "creator": signature["creator"],
                "created": signature["created"],
            }
        except KeyError:
            raise VerificationFormatError("Invalid signature section")
        
        if signature["type"].lower() != "rsasignature2017":
            raise VerificationFormatError("Unknown signature type")
        
        # Get the normalised hash of each document
        final_hash = cls.normalized_hash(options) + cls.normalized_hash(document)
        
        # Verify the signature
        public_key_instance: rsa.RSAPublicKey = cast(
            rsa.RSAPublicKey,
            serialization.load_pem_public_key(public_key.encode("ascii")),
        )
        try:
            public_key_instance.verify(
                base64.b64decode(signature["signatureValue"]),
                final_hash,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except InvalidSignature:
            raise VerificationError("Signature mismatch")
    
    @classmethod
    def create_signature(
        cls, 
        document: Dict[str, Any], 
        private_key: PrivateKey, 
        key_id: KeyId
    ) -> LDSignatureOptions:
        """Creates the signature for a document"""
        # Create the options document
        options = LDSignatureOptions(
            context="https://w3id.org/security/v1",
            creator=key_id,
            created=format_ld_date(utcnow()),
        )
        
        # Get the normalised hash of each document
        final_hash = cls.normalized_hash(options) + cls.normalized_hash(document)
        
        # Create the signature
        private_key_instance: rsa.RSAPrivateKey = cast(
            rsa.RSAPrivateKey,
            serialization.load_pem_private_key(
                private_key.encode("ascii"),
                password=None,
            ),
        )
        signature = base64.b64encode(
            private_key_instance.sign(
                final_hash,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        )
        
        # Add it to the options document along with other bits
        options["signatureValue"] = signature.decode("ascii")
        options["type"] = "RsaSignature2017"
        return options
    
    @classmethod
    def normalized_hash(cls, document: Dict[str, Any]) -> bytes:
        """
        Takes a JSON-LD document and create a hash of its URDNA2015 form,
        in the same way that Mastodon does internally.
        """
        norm_form = jsonld.normalize(
            document,
            {"algorithm": "URDNA2015", "format": "application/n-quads"},
        )
        digest = hashes.Hash(hashes.SHA256())
        digest.update(norm_form.encode("utf8"))
        return digest.finalize().hex().encode("ascii")


# Helper functions
def http_date(epoch_seconds: Optional[float] = None) -> str:
    """Format date for HTTP headers"""
    if epoch_seconds is None:
        epoch_seconds = arrow.utcnow().timestamp()
    return formatdate(epoch_seconds, usegmt=True)


def format_ld_date(value: datetime) -> str:
    """Format date for JSON-LD"""
    return f"{value.strftime(DATETIME_MS_FORMAT)[:-4]}Z"


def parse_http_date(http_date_str: str) -> datetime:
    """Parse HTTP date header"""
    parsed_date = arrow.get(http_date_str, 'ddd, DD MMM YYYY HH:mm:ss Z')
    return parsed_date.datetime


def parse_ld_date(value: Optional[str]) -> Optional[datetime]:
    """Parse JSON-LD date"""
    if value is None:
        return None
    return parser.isoparse(value).replace(microsecond=0)


def signature_part(signature: str, key: str) -> str:
    """Get a piece of the signature string"""
    parts = signature.split(',')
    for part in parts:
        part_parts = part.split('=')
        part_parts[0] = part_parts[0].strip()
        if part_parts[0] == key:
            return part_parts[1].strip().replace('"', '')
    return ''


def default_context() -> list[str] | list[str | dict[str, Any]]:
    """Get default ActivityPub context"""
    context: list[Any] = [
        "https://www.w3.org/ns/activitystreams",
        "https://w3id.org/security/v1",
    ]
    if current_app.config.get('FULL_AP_CONTEXT'):
        context.append({
            "lemmy": "https://join-lemmy.org/ns#",
            "litepub": "http://litepub.social/ns#",
            "pt": "https://joinpeertube.org/ns#",
            "sc": "http://schema.org/",
            "ChatMessage": "litepub:ChatMessage",
            "commentsEnabled": "pt:commentsEnabled",
            "sensitive": "as:sensitive",
            "matrixUserId": "lemmy:matrixUserId",
            "postingRestrictedToMods": "lemmy:postingRestrictedToMods",
            "removeData": "lemmy:removeData",
            "stickied": "lemmy:stickied",
            "moderators": {
                "@type": "@id",
                "@id": "lemmy:moderators"
            },
            "expires": "as:endTime",
            "distinguished": "lemmy:distinguished",
            "language": "sc:inLanguage",
            "identifier": "sc:identifier"
        })
    return context


def utcnow() -> datetime:
    """Get current UTC time"""
    return datetime.utcnow()


# Request sending functions
async def send_post_request(
    uri: HttpUrl,
    body: Optional[ActivityObject],
    private_key: PrivateKey,
    key_id: KeyId,
    content_type: str = "application/activity+json",
    method: HttpMethod = "post",
    timeout: int = 10,
    retries: int = 0
) -> bool:
    """Send ActivityPub request (async version for Redis Streams)"""
    current_app.logger.info(f'send_post_request called: uri={uri}, body_type={body.get("type") if body else "None"}')
    
    if current_app.debug:
        # In debug mode, send synchronously
        return post_request(
            uri=uri, 
            body=body, 
            private_key=private_key, 
            key_id=key_id, 
            content_type=content_type,
            method=method, 
            timeout=timeout, 
            retries=retries
        )
    else:
        # Queue to Redis Streams
        from app.federation.producer import get_producer
        
        producer = get_producer()
        msg_id = await producer.queue_activity(
            activity=body or {},
            destination=uri,
            private_key=private_key,
            key_id=key_id
        )
        current_app.logger.info(f'Activity queued with id={msg_id}')
        return True


def post_request(
    uri: HttpUrl,
    body: Optional[ActivityObject],
    private_key: PrivateKey,
    key_id: KeyId,
    content_type: str = "application/activity+json",
    method: HttpMethod = "post",
    timeout: int = 10,
    retries: int = 0
) -> bool:
    """Send ActivityPub request (sync version)"""
    session = get_task_session()
    
    try:
        current_app.logger.info(f'post_request: uri={uri}, body_type={body.get("type") if body else "None"}')
        
        if body and '@context' not in body:
            body['@context'] = default_context()
        
        activity_type = body.get('type', '') if body else ''
        activity_id = body.get('id', 'no-id') if body else 'no-body'
        
        # Create log entry
        log = TypedActivityPubLog(
            direction='out',
            activity_type=activity_type,
            result='processing',
            activity_id=activity_id,
            exception_message='',
            activity_json=json.dumps(body) if body else '{}'
        )
        session.add(log)
        session.commit()
        
        http_status_code: Optional[int] = None
        
        if not uri:
            log.result = 'failure'
            log.exception_message = 'empty uri'
            current_app.logger.error('post_request: empty uri provided')
        else:
            try:
                result = HttpSignature.signed_request(
                    uri, body, private_key, key_id, 
                    content_type, method, timeout
                )
                http_status_code = result.status_code
                
                if result.status_code not in [200, 202, 204]:
                    log.result = 'failure'
                    log.exception_message = f'{result.status_code}: {result.text[:100]}'
                    
                    if 'DOCTYPE html' in result.text:
                        log.result = 'ignored'
                        log.exception_message = f'{result.status_code}: HTML instead of JSON response'
                    elif 'community_has_no_followers' in result.text:
                        fix_local_community_membership(uri, private_key)
                    
                log.exception_message += f' {uri}'
                
            except Exception as e:
                log.result = 'failure'
                log.exception_message = f'could not send: {str(e)}'
                current_app.logger.error(f'Exception while sending to {uri}: {e}')
                http_status_code = 404
        
        if log.result == 'processing':
            log.result = 'success'
            current_app.logger.info(f'Successfully sent {activity_type} to {uri}')
        
        session.commit()
        
        # Handle retries for failures
        if log.result == 'failure' and http_status_code:
            if http_status_code == 429 or http_status_code >= 500:
                if content_type == "application/activity+json":
                    # Exponential backoff
                    backoff = min(60 * (2 ** retries), 15360)  # Max 4h
                    
                    send_queue = TypedSendQueue(
                        activity_id=activity_id,
                        activity_type=activity_type,
                        activity_json=json.dumps(body) if body else '{}',
                        recipient_inbox=uri,
                        private_key=private_key,
                        key_id=key_id,
                        attempts=retries,
                        next_attempt_at=datetime.utcnow() + timedelta(seconds=backoff)
                    )
                    session.add(send_queue)
                    session.commit()
        
        return log.result != 'failure'
        
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def signed_get_request(
    uri: HttpUrl,
    private_key: PrivateKey,
    key_id: KeyId,
    content_type: str = "application/activity+json",
    timeout: int = 10
) -> httpx.Response:
    """Make signed GET request"""
    return HttpSignature.signed_request(
        uri, None, private_key, key_id, 
        content_type, "get", timeout
    )


def fix_local_community_membership(uri: HttpUrl, private_key: PrivateKey) -> None:
    """Fix local community membership for remote instance"""
    community = TypedCommunity.query.filter_by(private_key=private_key).first()
    parsed_url = urlparse(uri)
    instance_domain = parsed_url.netloc
    instance = TypedInstance.query.filter_by(domain=instance_domain).first()
    
    if community and instance:
        followers = TypedCommunityMember.query.filter_by(community_id=community.id). \
            join(TypedUser, TypedUser.id == TypedCommunityMember.user_id). \
            filter(TypedUser.instance_id == instance.id)
        
        for f in followers:
            db.session.execute(
                text('DELETE FROM "community_member" WHERE user_id = :user_id AND community_id = :community_id'),
                {'user_id': f.user_id, 'community_id': community.id}
            )