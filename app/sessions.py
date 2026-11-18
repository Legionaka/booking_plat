"""Opaque server-side sessions stored in Redis."""

import json
import secrets
from collections.abc import MutableMapping
from typing import Any

from flask import Flask, Response, request
from flask.sessions import SessionInterface, SessionMixin
from redis import Redis
from redis.exceptions import RedisError
from werkzeug.datastructures import CallbackDict
from werkzeug.exceptions import MethodNotAllowed, NotFound

DEPENDENCY_UNAVAILABLE_MESSAGE = (
    "Authentication services are temporarily unavailable. "
    "Please try again."
)


class ServerSideSession(CallbackDict[str, Any], SessionMixin):
    """Mutable Flask session carrying an opaque Redis key."""

    def __init__(
        self,
        initial: MutableMapping[str, Any] | None = None,
        sid: str | None = None,
        new: bool = False,
        storage_unavailable: bool = False,
        storage_bypassed: bool = False,
    ) -> None:
        def on_update(_: MutableMapping[str, Any]) -> None:
            self.modified = True

        super().__init__(initial, on_update)
        self.sid = sid or secrets.token_urlsafe(32)
        self.new = new
        self.modified = False
        self.storage_unavailable = storage_unavailable
        self.storage_bypassed = storage_bypassed


class RedisSessionInterface(SessionInterface):
    """Store session data in Redis; the browser only receives a random session ID."""

    session_class = ServerSideSession

    def __init__(self, redis_client: Redis, key_prefix: str, ttl_seconds: int) -> None:
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.ttl_seconds = ttl_seconds

    def _key(self, sid: str) -> str:
        return f"{self.key_prefix}{sid}"

    def open_session(self, app: Flask, request: request) -> ServerSideSession:
        if self._does_not_use_sessions(app, request):
            return self.session_class(new=True, storage_bypassed=True)
        sid = request.cookies.get(self.get_cookie_name(app))
        if sid and sid.isascii() and len(sid) <= 128:
            try:
                stored = self.redis.get(self._key(sid))
            except RedisError:
                return self.session_class(new=True, storage_unavailable=True)
            if stored:
                try:
                    data = json.loads(stored)
                except (TypeError, ValueError):
                    try:
                        self.redis.delete(self._key(sid))
                    except RedisError:
                        return self.session_class(new=True, storage_unavailable=True)
                else:
                    if isinstance(data, dict):
                        return self.session_class(data, sid=sid)
        return self.session_class(new=True)

    def save_session(self, app: Flask, session: ServerSideSession, response: Response) -> None:
        if session.storage_bypassed:
            return
        if session.storage_unavailable:
            self._set_unavailable(response)
            return
        name = self.get_cookie_name(app)
        try:
            if not session:
                self.redis.delete(self._key(session.sid))
                response.delete_cookie(
                    name,
                    domain=self.get_cookie_domain(app),
                    path=self.get_cookie_path(app),
                    secure=self.get_cookie_secure(app),
                    httponly=self.get_cookie_httponly(app),
                    samesite=self.get_cookie_samesite(app),
                )
                return

            if session.modified or session.new:
                self.redis.set(
                    self._key(session.sid),
                    json.dumps(dict(session), separators=(",", ":")),
                    ex=self.ttl_seconds,
                )
            response.set_cookie(
                name,
                session.sid,
                expires=self.get_expiration_time(app, session),
                httponly=self.get_cookie_httponly(app),
                domain=self.get_cookie_domain(app),
                path=self.get_cookie_path(app),
                secure=self.get_cookie_secure(app),
                partitioned=self.get_cookie_partitioned(app),
                samesite=self.get_cookie_samesite(app),
            )
        except RedisError:
            self._set_unavailable(response)

    def regenerate(self, session: ServerSideSession) -> None:
        """Rotate the session identifier to prevent session fixation."""
        try:
            self.redis.delete(self._key(session.sid))
        except RedisError:
            session.storage_unavailable = True
        session.sid = secrets.token_urlsafe(32)
        session.new = True
        session.modified = True

    @staticmethod
    def _does_not_use_sessions(app: Flask, request: request) -> bool:
        path = request.path
        if path in {"/health", "/ready", "/api/config"}:
            return True
        if path == "/static" or path.startswith("/static/"):
            return True
        if path.startswith("/api/"):
            try:
                app.url_map.bind_to_environ(request.environ).match()
            except (MethodNotAllowed, NotFound):
                return True
        return False

    @staticmethod
    def _set_unavailable(response: Response) -> None:
        response.status_code = 503
        response.content_type = "application/json"
        response.set_data(
            json.dumps(
                {
                    "error": {
                        "code": "dependency_unavailable",
                        "message": DEPENDENCY_UNAVAILABLE_MESSAGE,
                    }
                }
            )
        )
