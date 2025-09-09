import base64

from flask import abort, jsonify, make_response, request
from flask_login import login_user
from webauthn import (
    generate_authentication_options,
    options_to_json,
    verify_authentication_response,
)
from webauthn.helpers import parse_authentication_credential_json
from webauthn.helpers.exceptions import InvalidAuthenticationResponse
from webauthn.helpers.structs import (
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
)

from app import cache, db
from app.auth import bp
from app.models import User, utcnow


# ----------------------------------------------------------------------
# Passkey options
@bp.route("/passkeys/login_options", methods=["POST"])
def passkey_options():
    request_json = request.get_json(force=True)
    user = User.query.filter(
        User.user_name == request_json["username"],
        User.ap_id == None,
        User.banned == False,
    ).first()
    if user:
        options = generate_authentication_options(
            rp_id=request.host,
            timeout=120000,
            allow_credentials=allowed_credentials(user),
            user_verification=UserVerificationRequirement.PREFERRED,
        )
        cache.set(f"challenge_{user.id}", options.challenge, timeout=3600)
        json_obj = options_to_json(options)
        response = make_response(json_obj)
        response.content_type = "application/json"
        return response
    else:
        abort(404)


# ----------------------------------------------------------------------
def allowed_credentials(user):
    if user.passkeys.count():
        return [
            PublicKeyCredentialDescriptor(id=base64.b64decode(pk.passkey_id))
            for pk in user.passkeys
        ]
    else:
        return []


# ----------------------------------------------------------------------
# Passkey verification
@bp.route("/passkeys/login_verification", methods=["POST"])
def passkey_verification():
    request_json = request.get_json(force=True)
    username = request_json["username"]
    redirect = request_json["redirect"]
    error_message = ""

    auth_credential = parse_authentication_credential_json(request_json["response"])
    user = User.query.filter(
        User.user_name == request_json["username"],
        User.ap_id == None,
        User.banned == False,
    ).first()
    if user:
        if not user.passkeys:
            error_message = f"No passkeys found for {username}"
        else:
            challenge = cache.get(f"challenge_{user.id}")
            success = False
            for passkey in user.passkeys:
                try:
                    # Use the public_key directly - could be bytes or base64 string
                    if isinstance(passkey.public_key, str):
                        try:
                            credential_public_key = base64.b64decode(passkey.public_key)
                        except Exception:
                            credential_public_key = passkey.public_key.encode("utf-8")
                    else:
                        credential_public_key = passkey.public_key

                    verify_authentication_response(
                        credential=auth_credential,
                        expected_rp_id=request.host,
                        expected_challenge=challenge,
                        expected_origin=f"https://{request.host}",
                        credential_public_key=credential_public_key,
                        credential_current_sign_count=0,
                        require_user_verification=False,
                    )
                    # print(f'{passkey} is valid')
                    passkey.counter += 1
                    passkey.used = utcnow()
                    success = True
                    break
                except InvalidAuthenticationResponse:
                    pass  # try another passkey instead by continuing to loop through all their passkeys
            if not success:
                error_message = f"No valid passkeys found for {username}"
            db.session.commit()
    else:
        # print(f'No user with email {username}')
        error_message = f"No valid passkeys found for {username}"

    if error_message:
        return jsonify({"verified": False, "message": error_message})
    else:
        login_user(user, remember=True)
        redirect_to = redirect or "/"
        return jsonify({"verified": True, "redirectTo": redirect_to})
