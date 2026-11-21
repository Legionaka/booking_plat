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


@web_bp.get("/offline")
def offline_page():
    return render_template("errors/offline.html")


@web_bp.get("/b/<slug>")
@web_bp.get("/b/<slug>/book")
@web_bp.get("/b/<slug>/book/time")
@web_bp.get("/b/<slug>/book/review")
@web_bp.get("/b/<slug>/book/confirmed/<int:booking_id>")
def customer_booking_page(slug, booking_id=None):
    view = "landing"
    if request.path.endswith("/book"):
        view = "services"
    elif request.path.endswith("/book/time"):
        view = "time"
    elif request.path.endswith("/book/review"):
        view = "review"
    elif booking_id is not None:
        view = "confirmed"
    return render_template(
        "customer/portal.html", view=view, slug=slug, booking_id=booking_id
    )


@web_bp.get("/account/bookings")
@web_bp.get("/account/bookings/<int:booking_id>")
@web_bp.get("/account/bookings/<int:booking_id>/reschedule")
@web_bp.get("/account/bookings/<int:booking_id>/rescheduled")
@web_bp.get("/account/bookings/<int:booking_id>/cancel")
@web_bp.get("/account/bookings/<int:booking_id>/cancelled")
def customer_account_page(booking_id=None):
    view = "bookings"
    if request.path.endswith("/rescheduled"):
        view = "rescheduled"
    elif request.path.endswith("/cancelled"):
        view = "cancelled"
    elif request.path.endswith("/reschedule"):
        view = "reschedule"
    elif request.path.endswith("/cancel"):
        view = "cancel"
    elif booking_id is not None:
        view = "detail"
    return render_template(
        "customer/portal.html", view=view, booking_id=booking_id
    )


@web_bp.get("/payments/return")
@web_bp.get("/payments/cancel")
def customer_payment_return():
    cancelled = request.path.endswith("/cancel")
    booking_id = request.args.get("booking_id", "")
    return render_template(
        "customer/portal.html",
        view="payment_cancelled" if cancelled else "payment_return",
        booking_id=booking_id if booking_id.isdecimal() else "",
    )
