"""Authentication business logic."""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Business, Membership, User

PASSWORD_HASHER = PasswordHasher()
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash("not-a-real-account-password")
VERIFY_SALT = "booking-platform.email-verification.v1"
RESET_SALT = "booking-platform.password-reset.v1"


class AuthServiceError(Exception):
    """Expected authentication failure safe to return to a client."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=salt)


def _load_token(token: str, salt: str, max_age: int) -> dict[str, object]:
    try:
        payload = _serializer(salt).loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired) as exc:
        raise AuthServiceError(
            "invalid_token", "This link is invalid or has expired.", 400
        ) from exc
    if not isinstance(payload, dict):
        raise AuthServiceError("invalid_token", "This link is invalid or has expired.", 400)
    return payload


def _email_service():
    return current_app.extensions["email_service"]


def register_user(email: str, password: str, full_name: str) -> User:
    existing = db.session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        raise AuthServiceError("email_in_use", "An account with this email already exists.", 409)

    user = User(email=email, password_hash=PASSWORD_HASHER.hash(password), full_name=full_name)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise AuthServiceError(
            "email_in_use", "An account with this email already exists.", 409
        ) from exc

    token = _serializer(VERIFY_SALT).dumps(
        {"user_id": user.id, "nonce": secrets.token_urlsafe(8)}
    )
    _email_service().send_verification(user, token)
    return user


def verify_email(token: str) -> User:
    payload = _load_token(
        token,
        VERIFY_SALT,
        current_app.config["AUTH_VERIFY_TOKEN_MAX_AGE_SECONDS"],
    )
    try:
        user_id = int(payload["user_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthServiceError(
            "invalid_token", "This link is invalid or has expired.", 400
        ) from exc
    result = db.session.execute(
        update(User)
        .where(User.id == user_id, User.verified_at.is_(None))
        .values(verified_at=func.now())
        .returning(User.id)
        .execution_options(synchronize_session=False)
    )
    consumed_user_id = result.scalar_one_or_none()
    if consumed_user_id is None:
        db.session.rollback()
        raise AuthServiceError("invalid_token", "This link is invalid or has expired.", 400)
    db.session.commit()
    return db.session.get(User, consumed_user_id)


def resend_verification(email: str) -> None:
    user = db.session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or user.verified_at is not None:
        return
    token = _serializer(VERIFY_SALT).dumps(
        {"user_id": user.id, "nonce": secrets.token_urlsafe(8)}
    )
    _email_service().send_verification(user, token)


def authenticate(email: str, password: str) -> User:
    user = db.session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    encoded_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    try:
        valid_password = PASSWORD_HASHER.verify(encoded_hash, password)
    except VerificationError:
        valid_password = False
    if user is None or not valid_password:
        raise AuthServiceError("invalid_credentials", "Email or password is incorrect.", 401)
    if user.verified_at is None:
        raise AuthServiceError("email_not_verified", "Verify your email before signing in.", 403)
    return user


def request_password_reset(email: str) -> None:
    user = db.session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        return
    token = _serializer(RESET_SALT).dumps({"user_id": user.id, "password_hash": user.password_hash})
    _email_service().send_password_reset(user, token)


def reset_password(token: str, new_password: str) -> None:
    payload = _load_token(
        token,
        RESET_SALT,
        current_app.config["AUTH_RESET_TOKEN_MAX_AGE_SECONDS"],
    )
    try:
        user_id = int(payload["user_id"])
        token_password_hash = str(payload["password_hash"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthServiceError(
            "invalid_token", "This link is invalid or has expired.", 400
        ) from exc
    updated_hash = PASSWORD_HASHER.hash(new_password)
    result = db.session.execute(
        update(User)
        .where(User.id == user_id, User.password_hash == token_password_hash)
        .values(password_hash=updated_hash)
        .returning(User.id)
        .execution_options(synchronize_session=False)
    )
    if result.scalar_one_or_none() is None:
        db.session.rollback()
        raise AuthServiceError("invalid_token", "This link is invalid or has expired.", 400)
    db.session.commit()


def user_payload(user: User) -> dict[str, object]:
    memberships = db.session.execute(
        select(Membership, Business)
        .join(Business, Business.id == Membership.business_id)
        .where(Membership.user_id == user.id)
        .order_by(Business.id)
    ).all()
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "verified": user.verified_at is not None,
        "memberships": [
            {
                "business_id": membership.business_id,
                "business_name": business.name,
                "business_slug": business.slug,
                "role": membership.role,
            }
            for membership, business in memberships
        ],
    }
