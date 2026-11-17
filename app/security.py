"""Session authentication and business membership authorization helpers."""

from collections.abc import Callable, Iterable
from functools import wraps
from typing import Any

from flask import g, jsonify, session
from sqlalchemy import select

from app.extensions import db
from app.models import Membership, User

BusinessId = int | Callable[..., int]


def _error(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


def _authenticated_user() -> User | None:
    user_id = session.get("_user_id")
    if not isinstance(user_id, int):
        return None
    user = db.session.get(User, user_id)
    if user is None or session.get("_auth_version") != user.password_hash:
        session.clear()
        return None
    g.current_user = user
    return user


def login_required(view: Callable[..., Any]) -> Callable[..., Any]:
    """Require a valid server-side login session."""

    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        if _authenticated_user() is None:
            return _error("authentication_required", "Sign in to continue.", 401)
        return view(*args, **kwargs)

    return wrapped


def role_required(business_id: int | Callable[..., int], roles: Iterable[str]):
    """Require one of the specified membership roles for a business."""
    allowed_roles = frozenset(roles)

    def decorate(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        @login_required
        def wrapped(*args: Any, **kwargs: Any):
            user: User = g.current_user
            resolved_business_id = (
                business_id(*args, **kwargs) if callable(business_id) else business_id
            )
            membership = db.session.execute(
                select(Membership).where(
                    Membership.user_id == user.id,
                    Membership.business_id == resolved_business_id,
                )
            ).scalar_one_or_none()
            if membership is None or membership.role not in allowed_roles:
                return _error("forbidden", "You do not have access to this business.", 403)
            return view(*args, **kwargs)

        return wrapped

    return decorate
