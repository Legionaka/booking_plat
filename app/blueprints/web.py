"""Server-rendered shells for the vanilla JavaScript frontend."""

from flask import Blueprint, render_template, request
from sqlalchemy import select

from app.extensions import db
from app.models import Business

web_bp = Blueprint("web", __name__)


def safe_next_path(value: str | None) -> str | None:
    """Accept only local absolute paths with one leading slash."""
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return None
    if value.startswith("/\\") or "\r" in value or "\n" in value:
        return None
    return value


@web_bp.get("/auth/login")
def login_page():
    slug = request.args.get("business", "")
    business = None
    if slug and len(slug) <= 100:
        business = db.session.execute(
            select(Business.name, Business.slug).where(Business.slug == slug)
        ).first()
    return render_template(
        "auth/login.html",
        business_name=business.name if business else None,
        business_slug=business.slug if business else None,
        portal=request.args.get("portal") == "business",
        next_path=safe_next_path(request.args.get("next")),
    )


@web_bp.get("/auth/register")
def register_page():
    return render_template("auth/register.html")


@web_bp.get("/auth/verify")
def verify_page():
    return render_template("auth/verify.html")


@web_bp.get("/auth/forgot")
def forgot_page():
    return render_template("auth/forgot.html")


@web_bp.get("/auth/forgot/sent")
def forgot_sent_page():
    return render_template("auth/forgot_sent.html")


@web_bp.get("/auth/reset")
def reset_page():
    return render_template("auth/reset.html")


@web_bp.get("/account")
@web_bp.get("/app")
def signed_in_placeholder():
    return render_template("auth/placeholder.html")
