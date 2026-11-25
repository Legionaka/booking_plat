"""Server-rendered shells for the vanilla JavaScript frontend."""

from urllib.parse import unquote

from flask import (
    Blueprint,
    Response,
    current_app,
    g,
    redirect,
    render_template,
    request,
    session,
)
from sqlalchemy import select

from app.extensions import db
from app.models import Business, Membership
from app.security import _authenticated_user, login_required

web_bp = Blueprint("web", __name__)


def safe_next_path(value: str | None) -> str | None:
    """Accept only a local absolute path; repeatedly decode to catch encoded separators."""
    if not value:
        return None
    decoded = value
    for _ in range(3):
        decoded = unquote(decoded)
    if not decoded.startswith("/") or decoded.startswith("//"):
        return None
    if "\\" in decoded or "\r" in decoded or "\n" in decoded:
        return None
    if ":" in decoded.split("/", 1)[0]:
        return None
    return decoded


def signed_in_home():
    user_id = session.get("_user_id")
    if not isinstance(user_id, int):
        return None
    memberships = (
        db.session.execute(select(Membership).where(Membership.user_id == user_id)).scalars().all()
    )
    if memberships:
        return "/app"
    return "/account"


def page_login_required(view):
    """Redirect protected HTML routes while API routes keep JSON 401 responses."""
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        user_id = session.get("_user_id")
        if not isinstance(user_id, int) or _authenticated_user() is None:
            next_path = safe_next_path(request.full_path if request.query_string else request.path)
            login_url = "/auth/login"
            if next_path:
                login_url += "?next=" + __import__("urllib.parse").parse.quote(next_path, safe="/")
            return redirect(login_url, code=303)
        return view(*args, **kwargs)

    return wrapped


@web_bp.get("/")
def landing_page():
    base_url = str(current_app.config["PUBLIC_BASE_URL"]).rstrip("/")
    return render_template(
        "landing.html",
        public_base_url=base_url,
        demo_mode=bool(current_app.config.get("DEMO_MODE")),
    )


@web_bp.get("/auth/login")
def login_page():
    home = signed_in_home()
    if home:
        return redirect(home, code=303)
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
    home = signed_in_home()
    if home:
        return redirect(home, code=303)
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
@page_login_required
def signed_in_placeholder():
    memberships = (
        db.session.execute(select(Membership).where(Membership.user_id == g.current_user.id))
        .scalars()
        .all()
    )
    if memberships:
        return "Not found", 404
    return redirect("/account/bookings", code=303)


@web_bp.get("/app")
@web_bp.get("/app/onboarding")
@web_bp.get("/app/<int:business_id>/<section>")
@page_login_required
def owner_portal(business_id=None, section="dashboard"):
    if business_id is not None:
        membership = db.session.get(Membership, (g.current_user.id, business_id))
        if membership is None or membership.role not in {"owner", "staff"}:
            return "Not found", 404
    allowed = {
        "dashboard",
        "week",
        "bookings",
        "services",
        "staff",
        "hours",
        "customers",
        "payments",
        "analytics",
        "settings",
        "audit",
    }
    if section not in allowed:
        section = "dashboard"
    onboarding = request.path.endswith("/onboarding")
    return render_template(
        "owner/portal.html",
        business_id=business_id or "",
        section="onboarding" if onboarding else section,
    )


@web_bp.get("/app/<int:business_id>/qr.svg")
@login_required
def booking_qr(business_id):
    membership = db.session.get(Membership, (g.current_user.id, business_id))
    if membership is None or membership.role != "owner":
        return "Not found", 404
    business = db.session.execute(
        select(Business).where(Business.id == business_id)
    ).scalar_one_or_none()
    if business is None:
        return "Not found", 404
    import segno

    public_base_url = str(current_app.config["PUBLIC_BASE_URL"]).rstrip("/")
    qr = segno.make_qr(f"{public_base_url}/b/{business.slug}")
    response = Response(qr.svg_inline(scale=5), mimetype="image/svg+xml")
    response.headers["Cache-Control"] = "private, max-age=300"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@web_bp.get("/offline")
def offline_page():
    return render_template("errors/offline.html")


@web_bp.get("/privacy")
def privacy_notice():
    return render_template("errors/privacy.html")


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
    return render_template("customer/portal.html", view=view, slug=slug, booking_id=booking_id)


@web_bp.get("/account/bookings")
@web_bp.get("/account/bookings/<int:booking_id>")
@web_bp.get("/account/bookings/<int:booking_id>/reschedule")
@web_bp.get("/account/bookings/<int:booking_id>/rescheduled")
@web_bp.get("/account/bookings/<int:booking_id>/cancel")
@web_bp.get("/account/bookings/<int:booking_id>/cancelled")
@page_login_required
def customer_account_page(booking_id=None):
    memberships = (
        db.session.execute(select(Membership).where(Membership.user_id == g.current_user.id))
        .scalars()
        .all()
    )
    if memberships:
        return "Not found", 404
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
    return render_template("customer/portal.html", view=view, booking_id=booking_id)


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


@web_bp.get("/robots.txt")
def robots_txt():
    lines = (
        "User-agent: *",
        "Allow: /",
        "Disallow: /app",
        "Disallow: /account",
        "Disallow: /platform",
        "Disallow: /dev",
        "Disallow: /api",
        "Disallow: /payments",
        f"Sitemap: {str(current_app.config['PUBLIC_BASE_URL']).rstrip('/')}/sitemap.xml",
        "",
    )
    return Response("\n".join(lines), mimetype="text/plain")


@web_bp.get("/sitemap.xml")
def sitemap_xml():
    base_url = str(current_app.config["PUBLIC_BASE_URL"]).rstrip("/")
    routes = (
        "/",
        "/b/fade-lab",
        "/auth/login",
        "/auth/register",
        "/auth/forgot",
        "/auth/verify",
    )
    urls = "".join(f"  <url><loc>{base_url}{route}</loc></url>\n" for route in routes)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}</urlset>\n"
    )
    return Response(body, mimetype="application/xml")


@web_bp.before_app_request
def canonical_trailing_slash():
    if request.path != "/" and request.path.endswith("/"):
        stripped = request.path.rstrip("/")
        if request.query_string:
            stripped += "?" + request.query_string.decode("ascii", "replace")
        return redirect(stripped, code=308)
