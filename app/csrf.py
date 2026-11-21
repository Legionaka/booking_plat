"""Synchronizer-token CSRF protection for cookie-authenticated mutations."""

import hmac

from flask import Flask, jsonify, request, session


def install_csrf_protection(app: Flask) -> None:
    @app.before_request
    def protect_cookie_authenticated_mutations():
        if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
            return None
        if request.path == "/api/payments/payfast/itn":
            return None
        public_auth_cookie_routes = {"/api/auth/register", "/api/auth/login"}
        has_session_cookie = app.config["SESSION_COOKIE_NAME"] in request.cookies
        if not has_session_cookie and request.path not in public_auth_cookie_routes:
            return None

        expected = session.get("_csrf_token")
        supplied = request.headers.get("X-CSRF-Token", "")
        if request.path.startswith("/payments/handoff/") and request.method == "POST":
            supplied = supplied or request.form.get("csrf_token", "")
        if not expected or not hmac.compare_digest(str(expected), supplied):
            return (
                jsonify(
                    {
                        "error": {
                            "code": "csrf_failed",
                            "message": "The CSRF token is missing or invalid.",
                        }
                    }
                ),
                400,
            )
        return None
