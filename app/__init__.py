"""Application factory and Flask application setup."""

from flask import Flask, jsonify, request
from flask_limiter.errors import RateLimitExceeded
from redis import Redis
from redis.exceptions import RedisError

from app.config import (
    DEFAULT_DEMO_OWNER_PASSWORD,
    DEFAULT_SECRET_KEY,
    Config,
    is_loopback_url,
    seed_startup_error,
)
from app.csrf import install_csrf_protection
from app.extensions import db, limiter, migrate
from app.health import health_bp
from app.observability import configure_observability
from app.services.email import build_email_service
from app.sessions import RedisSessionInterface

DEPENDENCY_UNAVAILABLE_MESSAGE = (
    "Authentication services are temporarily unavailable. Please try again."
)
BASE_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; base-uri 'self'; object-src 'none'; "
    "script-src 'self'; style-src 'self'; style-src-attr 'none'; "
    "font-src 'self'; img-src 'self'; connect-src 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)
PAYMENT_HANDOFF_CONTENT_SECURITY_POLICY = BASE_CONTENT_SECURITY_POLICY.replace(
    "form-action 'self'",
    "form-action 'self' https://sandbox.payfast.co.za https://www.payfast.co.za",
)


def content_security_policy_for(endpoint: str | None) -> str:
    """Return the global CSP, with PayFast form destinations only on its handoff."""
    if endpoint == "payments.payfast_handoff":
        return PAYMENT_HANDOFF_CONTENT_SECURITY_POLICY
    return BASE_CONTENT_SECURITY_POLICY


def create_app(test_config: dict[str, object] | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    configure_observability(app)

    if app.config.get("APP_ENV") == "production":
        for variable, value, service in (
            (
                "DATABASE_URL",
                app.config.get("SQLALCHEMY_DATABASE_URI"),
                "a managed PostgreSQL connection URL",
            ),
            ("REDIS_URL", app.config.get("REDIS_URL"), "a managed Redis connection URL"),
            (
                "RATELIMIT_STORAGE_URI",
                app.config.get("RATELIMIT_STORAGE_URI"),
                "a managed Redis connection URL",
            ),
        ):
            if is_loopback_url(value):
                raise RuntimeError(
                    f"{variable} must be set to {service}; localhost and loopback URLs "
                    "are not allowed."
                )

        email_backend = app.config.get("EMAIL_BACKEND")
        if email_backend == "smtp":
            required_email = {
                "SMTP_HOST": bool(app.config.get("SMTP_HOST")),
                "SMTP_FROM_ADDRESS": bool(app.config.get("SMTP_FROM_ADDRESS")),
                "SMTP_TLS_MODE": app.config.get("SMTP_TLS_MODE") in {"starttls", "ssl"},
                "SMTP_CREDENTIALS": not (
                    bool(app.config.get("SMTP_USERNAME")) != bool(app.config.get("SMTP_PASSWORD"))
                ),
            }
        elif email_backend == "http_api":
            provider = app.config.get("EMAIL_PROVIDER")
            required_email = {
                "EMAIL_PROVIDER": provider in {"brevo", "resend", "mailgun"},
                "EMAIL_API_KEY": bool(app.config.get("EMAIL_API_KEY")),
                "EMAIL_FROM_ADDRESS": bool(app.config.get("EMAIL_FROM_ADDRESS")),
            }
            if provider == "mailgun":
                required_email["EMAIL_MAILGUN_DOMAIN"] = bool(
                    app.config.get("EMAIL_MAILGUN_DOMAIN")
                )
                required_email["EMAIL_MAILGUN_REGION"] = app.config.get("EMAIL_MAILGUN_REGION") in {
                    "us",
                    "eu",
                }
        else:
            required_email = {"EMAIL_BACKEND": False}

        required = {
            "SECRET_KEY": app.config.get("SECRET_KEY")
            not in {DEFAULT_SECRET_KEY, "replace-with-a-long-random-value", ""},
            "DATABASE_URL": app.config.get("SQLALCHEMY_DATABASE_URI")
            not in {
                None,
                "",
                "postgresql+psycopg://booking:booking_dev_only@localhost:5433/booking_platform",
            },
            "REDIS_URL": app.config.get("REDIS_URL") not in {None, "", "redis://localhost:6379/0"},
            "RATELIMIT_STORAGE_URI": app.config.get("RATELIMIT_STORAGE_URI")
            not in {None, "", "redis://localhost:6379/1"},
            "SESSION_COOKIE_SECURE": bool(app.config.get("SESSION_COOKIE_SECURE")),
            "PUBLIC_BASE_URL": str(app.config.get("PUBLIC_BASE_URL", "")).startswith("https://"),
            "BOOKING_MANAGE_BASE_URL": str(
                app.config.get("BOOKING_MANAGE_BASE_URL", "")
            ).startswith("https://"),
            "TRUSTED_PROXY_HOPS": int(app.config.get("TRUSTED_PROXY_HOPS", 0)) > 0,
            "PAYFAST_MERCHANT_ID": bool(app.config.get("PAYFAST_MERCHANT_ID")),
            "PAYFAST_MERCHANT_KEY": bool(app.config.get("PAYFAST_MERCHANT_KEY")),
            "PAYFAST_PASSPHRASE": bool(app.config.get("PAYFAST_PASSPHRASE")),
            "PAYFAST_SANDBOX": not bool(app.config.get("PAYFAST_SANDBOX")),
            "DEMO_OWNER_PASSWORD": bool(app.config.get("DEMO_OWNER_PASSWORD"))
            and app.config.get("DEMO_OWNER_PASSWORD") != DEFAULT_DEMO_OWNER_PASSWORD,
        }
        required.update(required_email)
        missing = [name for name, configured in required.items() if not configured]
        if missing:
            raise RuntimeError(
                "Production configuration is missing or unsafe (including PayFast settings): "
                + ", ".join(missing)
            )

    if app.config.get("DEMO_MODE") and not app.config.get("PAYFAST_SANDBOX"):
        raise RuntimeError("DEMO_MODE requires PAYFAST_SANDBOX=true.")

    seed_error = seed_startup_error(
        bool(app.config.get("SEED_DEMO_ON_STARTUP")),
        bool(app.config.get("DEMO_MODE")),
        str(app.config.get("DEMO_OWNER_PASSWORD", "")),
    )
    if seed_error:
        raise RuntimeError(seed_error)

    app.config.setdefault("RATELIMIT_IN_MEMORY_FALLBACK_ENABLED", False)
    app.config.setdefault("RATELIMIT_HEADERS_ENABLED", True)

    db.init_app(app)
    migrate.init_app(app, db, directory="migrations")
    redis_client = Redis.from_url(app.config["REDIS_URL"], decode_responses=True)
    app.extensions["redis"] = redis_client
    app.extensions["rq_redis"] = Redis.from_url(app.config["REDIS_URL"], decode_responses=False)
    rate_redis = Redis.from_url(app.config["RATELIMIT_STORAGE_URI"], decode_responses=True)
    app.extensions["rate_redis"] = rate_redis
    app.session_interface = RedisSessionInterface(
        redis_client,
        key_prefix=app.config.get("SERVER_SESSION_KEY_PREFIX", "booking-platform:session:"),
        ttl_seconds=app.config["SERVER_SESSION_TTL_SECONDS"],
    )
    app.extensions["email_service"] = build_email_service(app.config["EMAIL_BACKEND"], app.config)
    install_csrf_protection(app)

    @app.before_request
    def require_auth_redis():
        if request.path.startswith("/api/auth/"):
            try:
                app.extensions["redis"].ping()
                app.extensions["rate_redis"].ping()
            except RedisError:
                return jsonify(
                    {
                        "error": {
                            "code": "dependency_unavailable",
                            "message": DEPENDENCY_UNAVAILABLE_MESSAGE,
                        }
                    }
                ), 503

    limiter.init_app(app)

    proxy_hops = int(app.config.get("TRUSTED_PROXY_HOPS", 0))
    if proxy_hops:
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=proxy_hops,
            x_proto=proxy_hops,
            x_host=proxy_hops,
            x_port=proxy_hops,
        )

    @app.after_request
    def security_headers(response):
        if request.path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "public, max-age=86400")
        response.headers["Content-Security-Policy"] = content_security_policy_for(request.endpoint)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.path.startswith("/auth/"):
            response.headers["Referrer-Policy"] = "no-referrer"
        response.headers.setdefault("X-Frame-Options", "DENY")
        if app.config.get("APP_ENV") == "production":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    @app.before_request
    def canonical_https_host():
        if app.config.get("APP_ENV") != "production":
            return None
        if request.path.startswith(("/health", "/ready", "/static/")):
            return None
        public = str(app.config.get("PUBLIC_BASE_URL", "")).rstrip("/")
        if not public:
            return None
        from urllib.parse import urlsplit

        from flask import redirect

        configured = urlsplit(public)
        host = request.host.split(":", 1)[0].lower()
        if (
            request.scheme != "https"
            or host.startswith("www.")
            or (configured.hostname and host != configured.hostname.lower())
        ):
            target = public + request.full_path.rstrip("?")
            return redirect(target, code=308)
        return None

    # Import models so Flask-Migrate can discover their metadata.
    from app import models  # noqa: F401

    app.register_blueprint(health_bp)
    from app.blueprints.admin import admin_bp, public_bp
    from app.blueprints.auth import auth_bp
    from app.blueprints.availability import availability_bp
    from app.blueprints.bookings import booking_bp
    from app.blueprints.dev import dev_bp
    from app.blueprints.insights import insights_bp
    from app.blueprints.payments import payments_bp
    from app.blueprints.web import web_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(availability_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(dev_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(insights_bp)
    app.register_blueprint(web_bp)

    @app.get("/api/config")
    def public_config():
        return jsonify({"demo_mode": bool(app.config.get("DEMO_MODE", False))})

    from app.cli import register_cli

    register_cli(app)

    @app.errorhandler(RateLimitExceeded)
    def rate_limit_error(_: RateLimitExceeded):
        return (
            jsonify(
                {
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests. Please try again later.",
                    }
                }
            ),
            429,
        )

    @app.errorhandler(RedisError)
    def redis_error(_: RedisError):
        return jsonify(
            {
                "error": {
                    "code": "dependency_unavailable",
                    "message": DEPENDENCY_UNAVAILABLE_MESSAGE,
                }
            }
        ), 503

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": {"code": "not_found", "message": "Not found."}}), 404
        from flask import render_template

        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": {"code": "internal_error", "message": "Server error."}}), 500
        from flask import render_template

        return render_template("errors/500.html"), 500

    @app.errorhandler(405)
    def method_not_allowed(error):
        if request.path.startswith("/api/"):
            return (
                jsonify(
                    {
                        "error": {
                            "code": "method_not_allowed",
                            "message": "Method not allowed.",
                        }
                    }
                ),
                405,
            )
        return error.get_response()

    return app
