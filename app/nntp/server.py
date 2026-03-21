"""NNTP bridge for PieFed.

Exposes PieFed communities as NNTP newsgroups, posts as top-level articles,
and post replies as threaded replies to those articles.

Article numbering: posts and replies within a community are sorted by date
and assigned sequential numbers 1..N.  This keeps the OVER range tight so
NNTP clients don't iterate millions of empty slots.

Message-ID format:
  - Posts:   <post-{id}@{domain}>
  - Replies: <reply-{id}@{domain}>

Usage::

    from app import create_app
    from app.nntp.server import PieFedNNTPServer, PieFedNNTPConnectionHandler

    flask_app = create_app()
    server = PieFedNNTPServer(
        flask_app,
        ("0.0.0.0", 1119),
        PieFedNNTPConnectionHandler,
    )
    server.serve_forever()
"""

import base64
import re
import time
import threading
import datetime
import urllib.request
import uuid
from typing import Dict, Optional, Tuple, Union

from .nntpserver import (
    NNTPServer,
    NNTPGroup,
    NNTPConnectionHandler,
    NNTPPostSetting,
    NNTPAuthSetting,
    NNTPPostError,
    NNTPAuthenticationError,
    ArticleInfo,
    Article,
    NNTPArticleNotFound,
)

# How long (seconds) to cache a community's article index before rebuilding it.
COMMUNITY_INDEX_TTL = 120

# How long (seconds) to cache the full group list.
GROUPS_CACHE_TTL = 60

# Thread-local: each connection thread stores the current community_id here.
_tl = threading.local()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_group_name(name: str) -> str:
    clean = re.sub(r'[^a-z0-9._-]', '_', name.lower())
    parts = clean.split('.')
    parts.reverse()
    return '.'.join(parts)


def _make_message_id(kind: str, obj_id: int, domain: str) -> str:
    return f"<{kind}-{obj_id}@{domain}>"


def _parse_message_id(message_id: str) -> Tuple[str, int]:
    """Return (kind, id) from a message-id string, or raise ValueError."""
    m = re.match(r'^<?(post|reply)-(\d+)@', message_id.strip('<>'))
    if not m:
        raise ValueError(f"Unrecognized message-id: {message_id!r}")
    return m.group(1), int(m.group(2))


def _ensure_utc(dt: Optional[datetime.datetime]) -> datetime.datetime:
    if dt is None:
        return datetime.datetime.now(datetime.timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _user_addr(user, domain: str) -> str:
    if user is None:
        return f"anonymous@{domain}"
    addr_domain = getattr(user, 'ap_domain', None) or domain
    return f"{user.user_name}@{addr_domain}"


def _post_body_text(post) -> str:
    parts = []
    url = ''
    if post.url:
        parts.append(f"URL: {post.url}")
        url = post.url
    if post.type == 3 and post.image:
        if post.image.source_url != url:
            parts.append(f"Image: {post.image.source_url}")
    if post.body:
        parts.append(post.body)
    return "\n\n".join(parts)


def _community_group_name(community) -> str:
    if community is None:
        return "PieFed.unknown"
    return _sanitize_group_name(f'{community.name}.{community.ap_domain or "local"}')


def _post_to_info(post, domain: str, seq_num: int) -> ArticleInfo:
    body = _post_body_text(post)
    community_name = _community_group_name(post.community)
    date = _ensure_utc(post.posted_at or post.created_at)
    web_url = f"https://{domain}/post/{post.id}"
    return ArticleInfo(
        number=seq_num,
        subject=post.title or "(no subject)",
        from_=_user_addr(post.author, domain),
        date=date,
        message_id=_make_message_id('post', post.id, domain),
        references='',
        bytes=len(body.encode('utf-8')),
        lines=body.count('\n') + 1,
        headers={
            'Newsgroups': community_name,
            'Archived-At': f'<{web_url}>',
            'X-Url': web_url,
        },
    )


def _reply_to_info(reply, domain: str, seq_num: int) -> ArticleInfo:
    body = reply.body or ''
    community_name = _community_group_name(reply.community)
    date = _ensure_utc(reply.posted_at or reply.created_at)
    references = (
        _make_message_id('reply', reply.parent_id, domain)
        if reply.parent_id
        else _make_message_id('post', reply.post_id, domain)
    )
    subject = "(no subject)"
    if reply.post:
        subject = f"Re: {reply.post.title or '(no subject)'}"
    web_url = f"https://{domain}/post/{reply.post_id}#comment-{reply.id}"
    return ArticleInfo(
        number=seq_num,
        subject=subject,
        from_=_user_addr(reply.author, domain),
        date=date,
        message_id=_make_message_id('reply', reply.id, domain),
        references=references,
        bytes=len(body.encode('utf-8')),
        lines=body.count('\n') + 1,
        headers={
            'Newsgroups': community_name,
            'Archived-At': f'<{web_url}>',
            'X-Url': web_url,
        },
    )


# ---------------------------------------------------------------------------
# Per-community sequential article index
# ---------------------------------------------------------------------------

class CommunityArticleIndex:
    """Sequential article numbering (1..N) for a single community.

    Posts and replies are sorted by posted_at so the NNTP overview range is
    tight: no large sparse gaps.  The index itself holds only (kind, db_id)
    pairs; full ArticleInfo objects are fetched from the DB on demand and
    cached for the lifetime of the index.
    """

    def __init__(self, community_id: int, flask_app, domain: str) -> None:
        self.community_id = community_id
        self._app = flask_app
        self._domain = domain
        self._seq_map: Dict[int, Tuple[str, int]] = {}   # seq_num → (kind, db_id)
        self._id_map: Dict[Tuple[str, int], int] = {}    # (kind, db_id) → seq_num
        self._info_cache: Dict[int, ArticleInfo] = {}
        self._high: int = 0
        self._loaded_at: float = 0.0

    # -- Loading -------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if time.monotonic() - self._loaded_at < COMMUNITY_INDEX_TTL:
            return
        self._rebuild()

    def _rebuild(self) -> None:
        with self._app.app_context():
            from app.models import Post, PostReply
            from sqlalchemy.orm import load_only

            posts = (
                Post.query
                .filter_by(community_id=self.community_id, deleted=False)
                .options(load_only(Post.id, Post.posted_at, Post.created_at))
                .all()
            )
            replies = (
                PostReply.query
                .filter_by(community_id=self.community_id, deleted=False)
                .options(load_only(PostReply.id, PostReply.posted_at, PostReply.created_at))
                .all()
            )

        items = []
        for p in posts:
            items.append((_ensure_utc(p.posted_at or p.created_at), 'post', p.id))
        for r in replies:
            items.append((_ensure_utc(r.posted_at or r.created_at), 'reply', r.id))
        items.sort(key=lambda x: x[0])

        seq_map: Dict[int, Tuple[str, int]] = {}
        id_map: Dict[Tuple[str, int], int] = {}
        for seq, (_, kind, db_id) in enumerate(items, start=1):
            seq_map[seq] = (kind, db_id)
            id_map[(kind, db_id)] = seq

        self._seq_map = seq_map
        self._id_map = id_map
        self._info_cache = {}
        self._high = len(seq_map)
        self._loaded_at = time.monotonic()

    # -- Public accessors ----------------------------------------------------

    def get_info(self, number: int) -> ArticleInfo:
        self._ensure_loaded()
        if number in self._info_cache:
            return self._info_cache[number]
        if number not in self._seq_map:
            raise NNTPArticleNotFound(str(number))
        kind, db_id = self._seq_map[number]
        info = self._fetch_info(kind, db_id, number)
        self._info_cache[number] = info
        return info

    def get_info_by_message_id(self, message_id: str) -> ArticleInfo:
        self._ensure_loaded()
        try:
            kind, db_id = _parse_message_id(message_id)
        except ValueError:
            raise NNTPArticleNotFound(message_id)
        seq = self._id_map.get((kind, db_id))
        if seq is None:
            raise NNTPArticleNotFound(message_id)
        return self.get_info(seq)

    @property
    def low(self) -> int:
        self._ensure_loaded()
        return 1 if self._high > 0 else 0

    @property
    def high(self) -> int:
        self._ensure_loaded()
        return self._high

    @property
    def count(self) -> int:
        self._ensure_loaded()
        return self._high

    # -- Internal ------------------------------------------------------------

    def _fetch_info(self, kind: str, db_id: int, seq_num: int) -> ArticleInfo:
        with self._app.app_context():
            from app.models import Post, PostReply
            if kind == 'post':
                post = Post.query.filter_by(id=db_id, deleted=False).first()
                if not post:
                    raise NNTPArticleNotFound(f"post-{db_id}")
                return _post_to_info(post, self._domain, seq_num)
            else:
                reply = PostReply.query.filter_by(id=db_id, deleted=False).first()
                if not reply:
                    raise NNTPArticleNotFound(f"reply-{db_id}")
                return _reply_to_info(reply, self._domain, seq_num)


# ---------------------------------------------------------------------------
# Article dict proxy
# ---------------------------------------------------------------------------

class IndexArticleDict:
    """Dict-like proxy backed by a CommunityArticleIndex.

    Integer keys look up by sequential article number within the group.
    String keys (message-ids) look up first within the group index, then
    fall back to a direct DB lookup (for cross-group or no-group requests).
    """

    def __init__(self, index: Optional[CommunityArticleIndex], flask_app, domain: str) -> None:
        self._index = index
        self._app = flask_app
        self._domain = domain

    def __getitem__(self, key: Union[int, str]) -> ArticleInfo:
        if isinstance(key, int):
            if self._index is None:
                raise NNTPArticleNotFound(str(key))
            return self._index.get_info(key)
        # String key: try group index first, then global fallback
        if self._index is not None:
            try:
                return self._index.get_info_by_message_id(key)
            except NNTPArticleNotFound:
                pass
        return self._global_by_message_id(key)

    def _global_by_message_id(self, message_id: str) -> ArticleInfo:
        with self._app.app_context():
            from app.models import Post, PostReply
            try:
                kind, db_id = _parse_message_id(message_id)
            except ValueError:
                raise NNTPArticleNotFound(message_id)
            if kind == 'post':
                post = Post.query.filter_by(id=db_id, deleted=False).first()
                if not post:
                    raise NNTPArticleNotFound(message_id)
                return _post_to_info(post, self._domain, post.id)
            else:
                reply = PostReply.query.filter_by(id=db_id, deleted=False).first()
                if not reply:
                    raise NNTPArticleNotFound(message_id)
                return _reply_to_info(reply, self._domain, reply.id)

    def values(self):
        raise NotImplementedError("Full article iteration not supported via this proxy")


# ---------------------------------------------------------------------------
# NNTPGroup implementation
# ---------------------------------------------------------------------------

class PieFedNNTPGroup(NNTPGroup):
    """Wraps a PieFed Community as an NNTP newsgroup.

    low/high/count are precomputed at load time from DB aggregate queries.
    They will match the CommunityArticleIndex sequential numbering (1..N).
    """

    def __init__(
        self,
        community_id: int,
        community_name: str,
        community_title: str,
        created_at: datetime.datetime,
        count: int,
        nsfw: bool = False,
        nsfl: bool = False,
        low_quality: bool = False,
        instance_id: Optional[int] = None,
    ) -> None:
        self._community_id = community_id
        self._name = _sanitize_group_name(community_name)
        self._short_description = community_title or community_name
        self._created = _ensure_utc(created_at)
        self._count = count
        self.nsfw = nsfw
        self.nsfl = nsfl
        self.low_quality = low_quality
        self.instance_id = instance_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def short_description(self) -> str:
        return self._short_description

    @property
    def number(self) -> int:
        return self._count

    @property
    def low(self) -> int:
        return 1 if self._count > 0 else 0

    @property
    def high(self) -> int:
        return self._count

    @property
    def articles(self) -> dict:
        # Only used in the default newnews fallback, which we override.
        return {}

    @property
    def created(self) -> datetime.datetime:
        return self._created

    @property
    def posting_permitted(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# NNTP server
# ---------------------------------------------------------------------------

class PieFedNNTPServer(NNTPServer):
    """NNTP server that maps PieFed communities/posts/replies to newsgroups/articles."""

    allow_reuse_address = True
    daemon_threads = True   # connection threads die with the process
    block_on_close = False  # don't wait for threads in server_close()

    def __init__(self, flask_app, *args, **kwargs) -> None:
        self._app = flask_app
        self._domain = flask_app.config.get('SERVER_NAME', 'localhost')
        self._groups_cache: Optional[Dict[str, PieFedNNTPGroup]] = None
        self._groups_cache_at: float = 0.0
        self._user_groups_cache: Dict[int, Tuple[float, Dict[str, PieFedNNTPGroup]]] = {}
        self._community_indices: Dict[int, CommunityArticleIndex] = {}
        kwargs.setdefault('can_post', NNTPPostSetting.POST | NNTPPostSetting.AUTHREQUIRED)
        kwargs.setdefault('auth', NNTPAuthSetting.REQUIRED)
        super().__init__(*args, **kwargs)

    # -- Required abstract methods ------------------------------------------

    def refresh(self) -> None:
        now = time.monotonic()
        if now - self._groups_cache_at > GROUPS_CACHE_TTL:
            self._groups_cache = None
        # Expire per-user caches too
        self._user_groups_cache = {
            uid: (ts, g) for uid, (ts, g) in self._user_groups_cache.items()
            if now - ts <= GROUPS_CACHE_TTL
        }

    @property
    def groups(self) -> Dict[str, PieFedNNTPGroup]:
        user_id = getattr(_tl, 'user_id', None)
        if user_id is not None:
            return self._groups_for_user(user_id)
        # Unauthenticated fallback — return full list
        if self._groups_cache is None:
            self._groups_cache = self._load_groups()
            self._groups_cache_at = time.monotonic()
        return self._groups_cache

    def _groups_for_user(self, user_id: int) -> Dict[str, PieFedNNTPGroup]:
        cached = self._user_groups_cache.get(user_id)
        if cached and time.monotonic() - cached[0] <= GROUPS_CACHE_TTL:
            return cached[1]
        # Ensure the base list is loaded
        if self._groups_cache is None:
            self._groups_cache = self._load_groups()
            self._groups_cache_at = time.monotonic()
        filtered = self._filter_groups_for_user(user_id, self._groups_cache)
        self._user_groups_cache[user_id] = (time.monotonic(), filtered)
        return filtered

    def _filter_groups_for_user(
        self, user_id: int, base: Dict[str, PieFedNNTPGroup]
    ) -> Dict[str, PieFedNNTPGroup]:
        with self._app.app_context():
            from app.models import User
            from app.utils import (
                communities_banned_from,
                blocked_or_banned_instances,
                filtered_out_communities,
            )
            user = User.query.get(user_id)
            if not user:
                return base

            banned_ids = set(communities_banned_from(user_id))
            blocked_instance_ids = set(blocked_or_banned_instances(user_id))
            filtered_ids = set(filtered_out_communities(user))
            excluded_ids = banned_ids | filtered_ids

        result: Dict[str, PieFedNNTPGroup] = {}
        for name, group in base.items():
            if group._community_id in excluded_ids:
                continue
            if user.hide_nsfw == 1 and group.nsfw:
                continue
            if user.hide_nsfl == 1 and group.nsfl:
                continue
            if getattr(user, 'hide_low_quality', False) and group.low_quality:
                continue
            if blocked_instance_ids and group.instance_id in blocked_instance_ids:
                continue
            result[name] = group
        return result

    @property
    def articles(self) -> IndexArticleDict:
        """Returns an article dict scoped to the current connection's selected community."""
        community_id = getattr(_tl, 'community_id', None)
        index = self._get_index(community_id) if community_id is not None else None
        return IndexArticleDict(index, self._app, self._domain)

    def article(self, key: Union[str, int]) -> Article:
        community_id = getattr(_tl, 'community_id', None)
        index = self._get_index(community_id) if community_id is not None else None
        proxy = IndexArticleDict(index, self._app, self._domain)
        info = proxy[key]
        body, extra_headers = self._fetch_body_and_headers(info.message_id)
        if extra_headers:
            info = info._replace(headers={**info.headers, **extra_headers})
        return Article(info=info, body=body)

    # -- Auth and posting ---------------------------------------------------

    def auth_user(self, user: str, password: str) -> bytes:
        with self._app.app_context():
            from sqlalchemy import func
            from app.models import User, utcnow
            from app import db

            u = (
                db.session.query(User)
                .filter(func.lower(User.user_name) == user.lower())
                .filter_by(ap_id=None, deleted=False)
                .first()
            )
            if u is None:
                u = (
                    db.session.query(User)
                    .filter(func.lower(User.email) == user.lower())
                    .filter_by(ap_id=None, deleted=False)
                    .first()
                )
            if u is None or not u.check_password(password):
                raise NNTPAuthenticationError("Invalid username or password")
            if u.banned:
                raise NNTPAuthenticationError("Account is banned")
            if not u.verified:
                raise NNTPAuthenticationError("Account is not verified")

            u.last_seen = utcnow()
            db.session.commit()

            _tl.user_id = u.id
            return f"Bearer {u.encode_jwt_token()}".encode()

    def post(self, auth_token: Optional[bytes], lines: str) -> None:
        import logging
        log = logging.getLogger('nntp.post')

        log.info("POST received, raw article length: %d chars", len(lines))
        log.debug("Raw article:\n%s", lines)

        # Parse RFC 2822-style headers + blank line + body
        if '\n\n' in lines:
            header_part, body = lines.split('\n\n', 1)
        else:
            header_part, body = lines, ''

        headers: Dict[str, str] = {}
        for line in header_part.splitlines():
            if ':' in line:
                key, _, value = line.partition(':')
                headers[key.strip().lower()] = value.strip()

        log.info("Parsed headers: %s", headers)
        log.info("Body length: %d chars", len(body))

        subject = headers.get('subject', '(no subject)')
        newsgroups = headers.get('newsgroups', '').strip()
        references = headers.get('references', '').strip()

        log.info("Subject: %r  Newsgroups: %r  References: %r", subject, newsgroups, references)

        auth = auth_token.decode()  # 'Bearer {jwt}'

        with self._app.app_context():
            from flask import g
            from app.models import Site
            from app.utils import get_setting
            g.site = Site.query.get(1)
            g.admin_ids = get_setting('admin_ids', [])

            if references:
                log.info("Article has References — treating as reply")
                # Derive community from the parent message-id rather than the Newsgroups
                # header — clients echo whatever Newsgroups value was in their local cache,
                # which may be stale or just the short community name.
                parent_msg_id = references.split()[-1]
                log.info("Parent message-id: %r", parent_msg_id)
                try:
                    kind, db_id = _parse_message_id(parent_msg_id)
                except ValueError:
                    log.error("Cannot parse References header: %r", parent_msg_id)
                    raise NNTPPostError(f"Cannot parse References: {parent_msg_id!r}")

                if kind == 'post':
                    post_id = db_id
                    parent_id = None
                    from app.models import Post
                    parent_post = Post.query.get(post_id)
                    if not parent_post:
                        raise NNTPPostError(f"Parent post {post_id} not found")
                    community_id = parent_post.community_id
                else:
                    from app.models import PostReply
                    parent = PostReply.query.get(db_id)
                    if not parent:
                        log.error("Parent reply %d not found in DB", db_id)
                        raise NNTPPostError(f"Parent reply {db_id} not found")
                    post_id = parent.post_id
                    parent_id = db_id
                    community_id = parent.community_id

                log.info("Calling post_reply: post_id=%d parent_id=%s community_id=%d",
                         post_id, parent_id, community_id)
                from app.api.alpha.utils.reply import post_reply as _api_post_reply
                try:
                    _api_post_reply(auth, {
                        'body': body.strip(),
                        'post_id': post_id,
                        'parent_id': parent_id,
                    })
                    log.info("post_reply succeeded")
                except Exception as exc:
                    log.exception("post_reply failed: %s", exc)
                    raise NNTPPostError(str(exc))
            else:
                # New post — must resolve community from Newsgroups header
                log.info("No References — treating as new post")
                group_name = newsgroups.split(',')[0].strip()
                group = self.groups.get(group_name)
                if group is None:
                    log.error("Unknown newsgroup: %r (known groups sample: %s)",
                              group_name, list(self.groups.keys())[:5])
                    raise NNTPPostError(f"Unknown newsgroup: {group_name}")
                community_id = group._community_id
                log.info("Resolved group %r to community_id=%d", group_name, community_id)

                from app.api.alpha.utils.post import post_post as _api_post_post
                try:
                    _api_post_post(auth, {
                        'title': subject,
                        'community_id': community_id,
                        'body': body.strip(),
                        'url': None,
                    })
                    log.info("post_post succeeded")
                except Exception as exc:
                    log.exception("post_post failed: %s", exc)
                    raise NNTPPostError(str(exc))

        # Invalidate the community article index so the new article appears on next refresh.
        self._community_indices.pop(community_id, None)

    # -- Optional overrides -------------------------------------------------

    def newnews(self, wildmat, date):
        results = []
        for group in self.groups.values():
            if wildmat != '*' and group.name != wildmat:
                continue
            index = self._get_index(group._community_id)
            index._ensure_loaded()
            for seq in list(index._seq_map):
                try:
                    info = index.get_info(seq)
                    if info.date >= date:
                        results.append(info)
                except NNTPArticleNotFound:
                    pass
        return iter(results)

    # -- Internal -----------------------------------------------------------

    def _get_index(self, community_id: int) -> CommunityArticleIndex:
        if community_id not in self._community_indices:
            self._community_indices[community_id] = CommunityArticleIndex(
                community_id, self._app, self._domain
            )
        return self._community_indices[community_id]

    def _load_groups(self) -> Dict[str, PieFedNNTPGroup]:
        with self._app.app_context():
            from app.models import Community, Post, PostReply
            from sqlalchemy import func
            from app import db

            post_counts = (
                db.session.query(Post.community_id, func.count(Post.id).label('n'))
                .filter(Post.deleted == False)
                .group_by(Post.community_id)
                .all()
            )
            reply_counts = (
                db.session.query(PostReply.community_id, func.count(PostReply.id).label('n'))
                .filter(PostReply.deleted == False)
                .group_by(PostReply.community_id)
                .all()
            )
            pc = {row.community_id: row.n for row in post_counts}
            rc = {row.community_id: row.n for row in reply_counts}

            communities = (
                Community.query.filter_by(banned=False, private=False).order_by(Community.name).all()
            )

            result: Dict[str, PieFedNNTPGroup] = {}
            for community in communities:
                count = pc.get(community.id, 0) + rc.get(community.id, 0)
                group = PieFedNNTPGroup(
                    community_id=community.id,
                    community_name=f'{community.name}.{community.ap_domain}',
                    community_title=community.title or '',
                    created_at=community.created_at or datetime.datetime.utcnow(),
                    count=count,
                    nsfw=bool(community.nsfw),
                    nsfl=bool(community.nsfl),
                    low_quality=bool(getattr(community, 'low_quality', False)),
                    instance_id=community.instance_id,
                )
                result[group.name] = group

            return result

    def _fetch_body_and_headers(self, message_id: str) -> Tuple[str, Dict[str, str]]:
        """Return (body, extra_headers).  Image posts get a MIME multipart body."""
        with self._app.app_context():
            from app.models import Post, PostReply
            try:
                kind, db_id = _parse_message_id(message_id)
            except ValueError:
                raise NNTPArticleNotFound(message_id)
            if kind == 'post':
                post = Post.query.filter_by(id=db_id, deleted=False).first()
                if not post:
                    raise NNTPArticleNotFound(message_id)
                if post.type == 3 and post.image:
                    return self._build_image_body(post)
                return _post_body_text(post), {}
            else:
                reply = PostReply.query.filter_by(id=db_id, deleted=False).first()
                if not reply:
                    raise NNTPArticleNotFound(message_id)
                return reply.body or '', {}

    def _build_image_body(self, post) -> Tuple[str, Dict[str, str]]:
        """Build a MIME multipart body with the post text and image attachment."""
        import logging
        log = logging.getLogger('nntp.image')

        text = _post_body_text(post)
        image_url = post.image.medium_url()
        boundary = uuid.uuid4().hex

        # Attempt to fetch the image
        image_part = ''
        if image_url:
            try:
                req = urllib.request.Request(image_url, headers={'User-Agent': 'PieFed-nntp/1.0'})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    content_type = resp.headers.get_content_type() or 'image/jpeg'
                    ext = content_type.split('/')[-1] if '/' in content_type else 'jpg'
                    image_data = base64.b64encode(resp.read()).decode('ascii')
                    # Wrap base64 at 76 chars per RFC 2045
                    image_data = '\n'.join(
                        image_data[i:i + 76] for i in range(0, len(image_data), 76)
                    )
                image_part = (
                    f'--{boundary}\r\n'
                    f'Content-Type: {content_type}\r\n'
                    f'Content-Transfer-Encoding: base64\r\n'
                    f'Content-Disposition: inline; filename="image.{ext}"\r\n'
                    f'\r\n'
                    f'{image_data}\r\n'
                )
            except Exception as exc:
                log.warning("Could not fetch image %s for post %d: %s", image_url, post.id, exc)

        body = (
            f'--{boundary}\r\n'
            f'Content-Type: text/plain; charset=UTF-8\r\n'
            f'\r\n'
            f'{text}\r\n'
            + image_part +
            f'--{boundary}--'
        )
        headers = {
            'MIME-Version': '1.0',
            'Content-Type': f'multipart/mixed; boundary="{boundary}"',
        }
        return body, headers


# ---------------------------------------------------------------------------
# Custom connection handler
# ---------------------------------------------------------------------------

class PieFedNNTPConnectionHandler(NNTPConnectionHandler):
    """Extends NNTPConnectionHandler to keep thread-local community context."""

    def select_group(self, group_name: str) -> bool:
        result = super().select_group(group_name)
        if result and group_name in self.server.groups:
            _tl.community_id = self.server.groups[group_name]._community_id
        else:
            _tl.community_id = None
        return result
