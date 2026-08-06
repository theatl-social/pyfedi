# This file is part of PieFed, which is licensed under the GNU Affero General Public License (AGPL) version 3.0.
# You should have received a copy of the GPL along with this program. If not, see <http://www.gnu.org/licenses/>.

import logging
from logging.handlers import SMTPHandler, RotatingFileHandler
import os
from flask import Flask, request, current_app, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_bootstrap import Bootstrap5
from flask_mail import Mail
from flask_babel import Babel, lazy_gettext as _l
from flask_caching import Cache
from flask_compress import Compress
from flask_limiter import Limiter
from flask_smorest import Api
from flask_bcrypt import Bcrypt
from werkzeug.middleware.proxy_fix import ProxyFix
from celery import Celery
from sqlalchemy_searchable import make_searchable
import httpx
from authlib.integrations.flask_client import OAuth

from config import Config


def get_locale():
    try:
        if current_user.is_authenticated and current_user.interface_language:
            return current_user.interface_language
        elif session.get("ui_language", None):
            return session["ui_language"]
        else:
            try:
                return request.accept_languages.best_match(
                    current_app.config["LANGUAGES"]
                )
            except:
                return "en"
    except:
        return "en"


def get_ip_address() -> str:
    # CF-Connecting-IP is set by Cloudflare on every proxied request and cannot
    # be forged by the client. request.remote_addr is resolved by
    # ProxyFix(x_for=1) from the rightmost X-Forwarded-For hop -- the one our
    # own reverse proxy appended -- so it is trustworthy too. The raw
    # X-Forwarded-For header is not: its leftmost entry is client-supplied, and
    # this is the Flask-Limiter key function, so trusting it let a client pick
    # its own rate-limit bucket. See docs/TRUSTED_CLIENT_IP.md.
    ip = request.headers.get("CF-Connecting-IP") or request.remote_addr
    if "," in ip:  # Remove all but first ip addresses
        ip = ip[: ip.index(",")].strip()
    return ip


_engine_options = {"pool_recycle": 3600}
if not Config.SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
    _engine_options["pool_size"] = Config.DB_POOL_SIZE
    _engine_options["max_overflow"] = Config.DB_MAX_OVERFLOW
db = SQLAlchemy(session_options={"autoflush": False}, engine_options=_engine_options)
make_searchable(db.metadata)
migrate = Migrate()
login = LoginManager()
login.login_view = "auth.login"
login.login_message = _l("Please log in to access this page.")
mail = Mail()
bootstrap = Bootstrap5()
babel = Babel(locale_selector=get_locale)
cache = Cache()
compress = Compress()
limiter = Limiter(
    get_ip_address,
    storage_uri="redis+" + Config.CACHE_REDIS_URL
    if Config.CACHE_REDIS_URL.startswith("unix://")
    else Config.CACHE_REDIS_URL,
)
celery = Celery(__name__, broker=Config.CELERY_BROKER_URL)
httpx_client = httpx.Client(http2=True)
oauth = OAuth()
redis_client = None  # Will be initialized in create_app()
rest_api = Api()
app_bcrypt = Bcrypt()


class StripCookieVaryForAnonymous:
    """WSGI middleware that removes 'Cookie' from the Vary header for requests
    that have no session cookie. This allows Cloudflare to cache responses for
    anonymous users, which Flask's session middleware prevents by always adding
    Vary: Cookie when it processes the session."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        has_session_cookie = "session=" in environ.get("HTTP_COOKIE", "")

        def custom_start_response(status, headers, exc_info=None):
            if not has_session_cookie:
                new_headers = []
                for name, value in headers:
                    if name.lower() == "vary":
                        value = ", ".join(
                            part.strip()
                            for part in value.split(",")
                            if part.strip().lower() != "cookie"
                        )
                    new_headers.append((name, value))
                headers = new_headers
            return start_response(status, headers, exc_info)

        return self.app(environ, custom_start_response)


_SECRET_KEY_KNOWN_BAD = frozenset(
    {
        "you-will-never-guesss",
        "you-will-never-guess",
        "change-me",
        "changeme",
        "secret",
        "dev",
        "development",
        "test",
    }
)
_SECRET_KEY_MIN_LENGTH = 32


def _validate_secret_key(
    secret_key, min_length=_SECRET_KEY_MIN_LENGTH, known_bad=_SECRET_KEY_KNOWN_BAD
):
    if not secret_key:
        raise RuntimeError(
            "SP-003: SECRET_KEY is not set. Generate a strong random key "
            f"(min {min_length} chars) and set the SECRET_KEY environment "
            "variable. See env.sample."
        )
    # SP-012: normalize before comparison so that copy-paste artifacts
    # ('YOU-WILL-NEVER-GUESSS', ' you-will-never-guesss ', etc.) don't slip
    # past the known-bad list. The comparison is case- and whitespace-
    # insensitive but the actual SECRET_KEY used by Flask is unchanged.
    normalized = secret_key.strip().lower()
    if normalized in known_bad:
        raise RuntimeError(
            "SP-003: SECRET_KEY is set to a known-default value. Generate a "
            f"strong random key (min {min_length} chars) and set the "
            "SECRET_KEY environment variable. See env.sample."
        )
    if len(secret_key) < min_length:
        raise RuntimeError(
            f"SP-003: SECRET_KEY is too short ({len(secret_key)} chars). "
            f"Use at least {min_length} characters."
        )


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    _validate_secret_key(app.config.get("SECRET_KEY"))
    if (
        app.config["HTTP_PROTOCOL"] == "mixed"
    ):  # mixed mode is for instances like retro.piefed.com which has a web ui that uses http while federation happens over https
        app.config["SERVER_URL"] = f"https://{app.config['SERVER_NAME']}"
    else:
        app.config["SERVER_URL"] = (
            f"{app.config['HTTP_PROTOCOL']}://{app.config['SERVER_NAME']}"
        )

    if app.config["SENTRY_DSN"]:
        import sentry_sdk

        sentry_sdk.init(
            dsn=app.config["SENTRY_DSN"],
            enable_tracing=False,
        )

    app.wsgi_app = StripCookieVaryForAnonymous(ProxyFix(app.wsgi_app, x_for=1))

    app.config["API_TITLE"] = "PieFed 1.7 Alpha API"
    app.config["API_VERSION"] = "alpha 1.7"
    app.config["OPENAPI_VERSION"] = "3.1.1"
    if app.config["SERVE_API_DOCS"]:
        app.config["OPENAPI_URL_PREFIX"] = "/api/alpha"
        app.config["OPENAPI_JSON_PATH"] = "/swagger.json"
        app.config["OPENAPI_SWAGGER_UI_PATH"] = "/swagger"
        app.config["OPENAPI_SWAGGER_UI_URL"] = (
            "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"
        )
        app.config["API_SPEC_OPTIONS"] = {
            "security": [{"bearerAuth": []}],
            "components": {
                "securitySchemes": {
                    "bearerAuth": {
                        "type": "http",
                        "scheme": "bearer",
                        "bearerFormat": "JWT",
                    }
                }
            },
            "servers": [
                {
                    "url": f"{app.config['HTTP_PROTOCOL']}://{app.config['SERVER_NAME']}",
                    "description": "This instance",
                },
                {
                    "url": "https://crust.piefed.social",
                    "description": "Development instance",
                },
                {
                    "url": "https://piefed.social",
                },
                {"url": "https://preferred.social"},
                {"url": "https://feddit.online"},
                {"url": "https://piefed.world"},
            ],
            "info": {
                "title": "PieFed 1.7 Alpha API",
                "contact": {
                    "name": "Developer",
                    "url": "https://codeberg.org/rimu/pyfedi",
                },
                "license": {
                    "name": "AGPLv3",
                    "url": "https://www.gnu.org/licenses/agpl-3.0.en.html#license-text",
                },
            },
        }
    rest_api.init_app(app)
    rest_api.DEFAULT_ERROR_RESPONSE_NAME = (
        None  # Don't include default errors, define them ourselves
    )

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    login.init_app(app)
    mail.init_app(app)
    bootstrap.init_app(app)
    babel.init_app(app, locale_selector=get_locale)
    cache.init_app(app)
    compress.init_app(
        app
    )  # registered before the after_request in pyfedi.py, so it runs after it
    limiter.init_app(app)
    app_bcrypt.init_app(app)
    # Celery configuration.
    #
    # This deliberately does NOT do `celery.conf.update(app.config)`. That bulk
    # merge pushed every uppercase Flask setting (S3_REGION, S3_BUCKET,
    # CACHE_DIR, BOUNCE_PASSWORD, ...) into Celery, where Celery's legacy-name
    # compatibility layer reads uppercase keys as pre-4.0 Celery options and
    # warns about them ahead of Celery 6. None of those settings mean anything
    # to Celery. Only the options below are Celery's business, and each uses
    # the modern lowercase name.
    #
    # SP-018: task_serializer / result_serializer / accept_content pin Celery to
    # JSON for both broker messages and task results. Celery 5.x already
    # defaults to JSON, but defaults can shift across major versions, so the
    # allowlist is stated explicitly rather than inherited. Unsafe legacy
    # serializers (the p-word, and yaml's default Loader) execute arbitrary
    # code on deserialization; against attacker-influenced broker messages that
    # is remote code execution on every worker process. Note that dropping the
    # bulk app.config merge also closes a second door: a CELERY_TASK_SERIALIZER
    # environment variable can no longer reach Celery at all, because Flask
    # config is no longer forwarded. Keep this explicit pin anyway — it is the
    # assertion that survives future refactors. See SECURITY_PATCHES.md.
    celery.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["RESULT_BACKEND"],
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_routes={
            "app.shared.tasks.users.check_user_application": {"queue": "background"},
            "app.user.utils.purge_user_then_delete_task": {"queue": "background"},
            "app.community.util.retrieve_mods_and_backfill": {"queue": "background"},
            "app.community.util.send_to_remote_instance_task": {"queue": "send"},
            "app.activitypub.signature.post_request": {"queue": "send"},
            # Maintenance tasks - all go to background queue
            "app.shared.tasks.maintenance.*": {"queue": "background"},
            "app.admin.routes.*": {"queue": "background"},
            "app.admin.util.*": {"queue": "background"},
        },
        # Recycle worker children to bound leaked memory: after 1000 tasks, or
        # when RSS exceeds 512MB (value is in KB).
        worker_max_tasks_per_child=1000,
        worker_max_memory_per_child=512000,
        broker_connection_retry_on_startup=True,
    )

    # Initialize redis_client
    global redis_client
    from app.utils import get_redis_connection

    redis_client = get_redis_connection(app.config["CACHE_REDIS_URL"])

    oauth.init_app(app)
    if app.config["GOOGLE_OAUTH_CLIENT_ID"]:
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_OAUTH_CLIENT_ID"],
            client_secret=app.config["GOOGLE_OAUTH_SECRET"],
            access_token_url="https://oauth2.googleapis.com/token",
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            api_base_url="https://www.googleapis.com/",
            client_kwargs={"scope": "email profile"},
        )
    if app.config["MASTODON_OAUTH_CLIENT_ID"]:
        oauth.register(
            name="mastodon",
            client_id=app.config["MASTODON_OAUTH_CLIENT_ID"],
            client_secret=app.config["MASTODON_OAUTH_SECRET"],
            access_token_url=f"https://{app.config['MASTODON_OAUTH_DOMAIN']}/oauth/token",
            authorize_url=f"https://{app.config['MASTODON_OAUTH_DOMAIN']}/oauth/authorize",
            api_base_url=f"https://{app.config['MASTODON_OAUTH_DOMAIN']}/api/v1/",
            client_kwargs={"response_type": "code"},
        )

    if app.config["DISCORD_OAUTH_CLIENT_ID"]:
        oauth.register(
            name="discord",
            client_id=app.config["DISCORD_OAUTH_CLIENT_ID"],
            client_secret=app.config["DISCORD_OAUTH_SECRET"],
            access_token_url="https://discord.com/api/oauth2/token",
            authorize_url="https://discord.com/api/oauth2/authorize",
            api_base_url="https://discord.com/api/",
            client_kwargs={"scope": "identify email"},
        )

    from app.main import bp as main_bp

    app.register_blueprint(main_bp)

    from app.errors import bp as errors_bp

    app.register_blueprint(errors_bp)

    from app.admin import bp as admin_bp

    app.register_blueprint(admin_bp, url_prefix="/admin")

    from app.activitypub import bp as activitypub_bp

    app.register_blueprint(activitypub_bp)

    from app.auth import bp as auth_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")

    from app.community import bp as community_bp

    app.register_blueprint(community_bp, url_prefix="/community")

    from app.post import bp as post_bp

    app.register_blueprint(post_bp)

    from app.user import bp as user_bp

    app.register_blueprint(user_bp)

    from app.domain import bp as domain_bp

    app.register_blueprint(domain_bp)

    from app.feed import bp as feed_bp

    app.register_blueprint(feed_bp)

    from app.instance import bp as instance_bp

    app.register_blueprint(instance_bp)

    from app.topic import bp as topic_bp

    app.register_blueprint(topic_bp)

    from app.chat import bp as chat_bp

    app.register_blueprint(chat_bp)

    from app.search import bp as search_bp

    app.register_blueprint(search_bp)

    from app.tag import bp as tag_bp

    app.register_blueprint(tag_bp)

    from app.dev import bp as dev_bp

    app.register_blueprint(dev_bp)

    from app.api.alpha import bp as app_api_bp

    app.register_blueprint(app_api_bp)

    # API Namespaces
    from app.api.alpha import (
        site_bp,
        misc_bp,
        comm_bp,
        feed_bp,
        topic_bp,
        user_bp,
        reply_bp,
        post_bp,
        upload_bp,
        private_message_bp,
        admin_bp,
        private_admin_bp,
    )

    rest_api.register_blueprint(site_bp)
    rest_api.register_blueprint(misc_bp)
    rest_api.register_blueprint(comm_bp)
    rest_api.register_blueprint(feed_bp)
    rest_api.register_blueprint(topic_bp)
    rest_api.register_blueprint(user_bp)
    rest_api.register_blueprint(reply_bp)
    rest_api.register_blueprint(post_bp)
    rest_api.register_blueprint(upload_bp)
    rest_api.register_blueprint(private_message_bp)
    rest_api.register_blueprint(admin_bp)
    rest_api.register_blueprint(private_admin_bp)

    # send error reports via email
    if app.config["MAIL_SERVER"] and app.config["ERRORS_TO"]:
        auth = None
        if app.config["MAIL_USERNAME"] or app.config["MAIL_PASSWORD"]:
            auth = (app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])
        secure = None
        if app.config["MAIL_USE_TLS"]:
            secure = ()
        mail_handler = SMTPHandler(
            mailhost=(app.config["MAIL_SERVER"], app.config["MAIL_PORT"]),
            fromaddr=(app.config["MAIL_FROM"]),
            toaddrs=app.config["ERRORS_TO"],
            subject="PieFed error",
            credentials=auth,
            secure=secure,
            timeout=5.0,
        )
        mail_handler.setLevel(logging.ERROR)
        app.logger.addHandler(mail_handler)

    # log rotation
    if not os.path.exists("logs"):
        os.mkdir("logs")
    file_handler = RotatingFileHandler(
        "logs/pyfedi.log", maxBytes=1002400, backupCount=15
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
        )
    )
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)

    app.logger.setLevel(logging.INFO)

    # Load plugins
    from app.plugins import load_plugins

    load_plugins()

    return app


from app import models
