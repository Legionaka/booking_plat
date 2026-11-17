"""Gunicorn logger that keeps access/error output in the application's JSON format."""

import logging
import sys

from gunicorn import glogging

from app.observability import JsonFormatter, RequestIdFilter


class JsonGunicornLogger(glogging.Logger):
    def setup(self, cfg) -> None:
        super().setup(cfg)
        for logger in (self.error_log, self.access_log):
            handler = logging.StreamHandler(sys.stdout)
            handler.addFilter(RequestIdFilter())
            handler.setFormatter(JsonFormatter())
            logger.handlers = [handler]
            logger.propagate = False

    def access(self, resp, req, environ, request_time) -> None:
        response_headers = dict(resp.headers)
        self.access_log.info(
            "http_request method=%s status=%s",
            req.method,
            resp.status,
            extra={"request_id": response_headers.get("X-Request-ID", "-")},
        )
