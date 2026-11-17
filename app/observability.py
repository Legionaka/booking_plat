"""Request correlation, privacy-conscious JSON logging, and optional Sentry setup."""

from __future__ import annotations

import contextvars
import json
import logging
import uuid
from datetime import UTC, datetime

from flask import Flask, current_app, g, request

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", None):
            record.request_id = _request_id.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "request_id": getattr(record, "request_id", "-"),
                "message": record.getMessage(),
            },
            ensure_ascii=False,
        )


def configure_observability(app: Flask) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(JsonFormatter())
    app.logger.handlers = [handler]
    app.logger.setLevel(app.config["LOG_LEVEL"])
    app.logger.propagate = False
    if not app.testing:
        root_logger = logging.getLogger()
        root_logger.handlers = [handler]
        root_logger.setLevel(app.config["LOG_LEVEL"])

    if app.config.get("SENTRY_DSN"):
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration

        sentry_sdk.init(
            dsn=app.config["SENTRY_DSN"],
            integrations=[FlaskIntegration()],
            send_default_pii=False,
            before_send=lambda event, _hint: _scrub_sentry_event(event),
        )

    @app.before_request
    def attach_request_id() -> None:
        identifier = str(uuid.uuid4())
        _request_id.set(identifier)
        g.request_id = identifier

    @app.after_request
    def return_request_id(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", _request_id.get())
        current_app.logger.info(
            "http_request method=%s status=%s", request.method, response.status_code
        )
        return response

    @app.teardown_request
    def clear_request_id(_error: BaseException | None) -> None:
        _request_id.set("-")


def _scrub_sentry_event(event: dict) -> dict:
    request_data = event.get("request")
    if isinstance(request_data, dict):
        for key in ("data", "cookies", "headers", "env", "query_string", "url"):
            request_data.pop(key, None)
    event.pop("user", None)
    return event
