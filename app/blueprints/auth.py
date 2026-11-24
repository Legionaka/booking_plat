"""JSON authentication routes; request schemas and services hold the details."""

import hashlib
import secrets
from functools import wraps
from typing import Any, cast

from flask import Blueprint, current_app, g, jsonify, request, session
from flask_limiter.util import get_remote_address
from pydantic import BaseModel, ValidationError

from app.extensions import limiter
from app.schemas.auth import (
    ForgotRequest,
    LoginRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetRequest,
    VerifyRequest,
)
from app.security import login_required
from app.services import auth
from app.services.auth import AuthServiceError

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _email_rate_key() -> str:
    body = request.get_json(silent=True)
    identity = body.get("email", "") if isinstance(body, dict) else ""
    if not identity and isinstance(body, dict) and isinstance(body.get("token"), str):
        identity = hashlib.sha256(body["token"].encode()).hexdigest()
    return f"{get_remote_address()}:{str(identity).strip().lower()}"


def _limit_by_ip(config_key: str):
    def decorate(view):
        return limiter.limit(lambda: current_app.config[config_key], key_func=get_remote_address)(
            view
        )

    return decorate


def _limit_by_ip_and_identity(identity_key: str, ip_key: str):
    def decorate(view):
        limited_by_ip = limiter.limit(
            lambda: current_app.config[ip_key], key_func=get_remote_address
        )(view)
        return limiter.limit(lambda: current_app.config[identity_key], key_func=_email_rate_key)(
            limited_by_ip
        )

    return decorate


def _validated[ModelT: BaseModel](model: type[ModelT]) -> ModelT:
    try:
        return model.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        raise AuthServiceError("validation_error", "Request body is invalid.", 422) from exc


def _handle_errors(view):
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        try:
            return view(*args, **kwargs)
        except AuthServiceError as exc:
            return jsonify({"error": {"code": exc.code, "message": exc.message}}), exc.status_code

    return wrapped


@auth_bp.get("/csrf")
def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return jsonify({"data": {"csrf_token": token}})


@auth_bp.post("/register")
@_limit_by_ip("AUTH_REGISTER_RATE_LIMIT")
@_handle_errors
def register():
    payload = _validated(RegisterRequest)
    auth.register_user(payload.email, payload.password, payload.full_name)
    return jsonify({"data": {"message": "Verification email sent."}}), 201


@auth_bp.post("/verify")
@_handle_errors
def verify():
    payload = _validated(VerifyRequest)
    auth.verify_email(payload.token)
    return jsonify({"data": {"message": "Email verified."}})


@auth_bp.post("/resend-verification")
@_limit_by_ip_and_identity(
    "AUTH_RESEND_VERIFICATION_EMAIL_RATE_LIMIT", "AUTH_RESEND_VERIFICATION_IP_RATE_LIMIT"
)
@_handle_errors
def resend_verification():
    payload = _validated(ResendVerificationRequest)
    auth.resend_verification(payload.email)
    response = jsonify(
        {"data": {"message": "If the account needs verification, a new email was sent."}}
    )
    response.headers["Retry-After"] = str(
        current_app.config["AUTH_RESEND_VERIFICATION_COOLDOWN_SECONDS"]
    )
    return response


@auth_bp.post("/login")
@_limit_by_ip_and_identity("AUTH_LOGIN_EMAIL_RATE_LIMIT", "AUTH_LOGIN_IP_RATE_LIMIT")
@_handle_errors
def login():
    payload = _validated(LoginRequest)
    user = auth.authenticate(payload.email, payload.password)
    session.clear()
    cast(Any, current_app.session_interface).regenerate(session)
    session["_user_id"] = user.id
    session["_auth_version"] = user.password_hash
    session["_csrf_token"] = secrets.token_urlsafe(32)
        
    payload = auth.user_payload(user)
    memberships = cast(list[dict[str, Any]], payload["memberships"])
    is_owner = any(m["role"] == "owner" for m in memberships)
    redirect_url = "/app" if is_owner else "/account"

    return jsonify({"data": {"user": payload, "redirect": redirect_url}}), 201




@auth_bp.post("/logout")
@_handle_errors
@login_required
def logout():
    session.clear()
    return jsonify({"data": {"message": "Signed out."}})


@auth_bp.post("/forgot")
@_limit_by_ip_and_identity("AUTH_FORGOT_EMAIL_RATE_LIMIT", "AUTH_FORGOT_IP_RATE_LIMIT")
@_handle_errors
def forgot():
    payload = _validated(ForgotRequest)
    auth.request_password_reset(payload.email)
    return jsonify(
        {"data": {"message": "If an account exists for that email, reset instructions were sent."}}
    )


@auth_bp.post("/reset")
@_limit_by_ip_and_identity("AUTH_RESET_TOKEN_RATE_LIMIT", "AUTH_RESET_IP_RATE_LIMIT")
@_handle_errors
def reset():
    payload = _validated(ResetRequest)
    auth.reset_password(payload.token, payload.new_password)
    return jsonify({"data": {"message": "Password reset."}})


@auth_bp.get("/me")
@login_required
def me():
    return jsonify({"data": {"user": auth.user_payload(g.current_user)}})
