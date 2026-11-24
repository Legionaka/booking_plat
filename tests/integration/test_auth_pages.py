"""Frontend auth route, response-header, and strict-CSP integration coverage."""

import re

from app.extensions import db
from app.models import Business
from app.services.email import SMTPEmailService


def test_auth_pages_render_with_csp_and_no_inline_assets(client):
    pages = [
        ("/auth/login", b'data-page="login"'),
        ("/auth/register", b'data-page="register"'),
        ("/auth/verify", b'data-page="verify"'),
        ("/auth/forgot", b'data-page="forgot"'),
        ("/auth/forgot/sent", b'data-page="forgot-sent"'),
        ("/auth/reset", b'data-page="reset"'),
        ("/app", b'data-section="dashboard"'),
        ("/account", b'data-page="placeholder"'),
    ]
    for path, marker in pages:
        response = client.get(path)
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert marker in response.data
        assert "Content-Security-Policy" in response.headers
        assert "style-src 'self'" in response.headers["Content-Security-Policy"]
        assert "style-src-attr 'none'" in response.headers["Content-Security-Policy"]
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html, re.IGNORECASE)
        assert not re.search(r"<style\b|\sstyle\s*=", html, re.IGNORECASE)
        assert "data:" not in html.lower()
    for path, _marker in pages[:6]:
        assert client.get(path).headers["Referrer-Policy"] == "no-referrer"


def test_all_server_rendered_page_routes_obey_template_contract(
    app, client, assert_rendered_page_contract
):
    page_rules = [
        rule
        for rule in app.url_map.iter_rules()
        if rule.endpoint.startswith(("web.", "dev."))
        and "GET" in rule.methods
        and "<" not in rule.rule
    ]
    assert page_rules
    for rule in page_rules:
        response = client.get(rule.rule)
        assert response.status_code == 200, rule.rule
        assert_rendered_page_contract(response.get_data(as_text=True), rule.rule)


def test_business_branded_login_uses_public_name_and_safe_unknown_fallback(client, app):
    with app.app_context():
        db.session.add(Business(slug="fade-lab", name="Fade Lab Barbers"))
        db.session.commit()

    valid = client.get("/auth/login?business=fade-lab")
    unknown = client.get("/auth/login?business=not-a-real-business")

    assert valid.status_code == unknown.status_code == 200
    assert b"Sign in to Fade Lab Barbers" in valid.data
    assert b"not-a-real-business" not in unknown.data
    assert b"Sign in to Fade Lab Barbers" in unknown.data


def test_public_business_endpoint_returns_only_public_safe_fields(client, app):
    with app.app_context():
        db.session.add(Business(slug="public-shop", name="Public Shop"))
        db.session.commit()

    response = client.get("/api/b/public-shop")
    missing = client.get("/api/b/missing-shop")

    assert response.status_code == 200
    assert response.json["data"] == {
        "name": "Public Shop",
        "slug": "public-shop",
        "timezone": "Africa/Johannesburg",
    }
    assert missing.status_code == 404


def test_login_next_path_rejects_open_redirect_forms():
    from app.blueprints.web import safe_next_path

    assert safe_next_path("/account/bookings") == "/account/bookings"
    unsafe_values = (
        None,
        "https://attacker.example",
        "//attacker.example",
        "/\\attacker",
        "/account\\evil",
        "javascript:alert(1)",
    )
    for value in unsafe_values:
        assert safe_next_path(value) is None


def test_auth_email_links_target_frontend_routes(app, monkeypatch):
    messages = []
    user = type("User", (), {"email": "person@example.test"})()
    app.config["PUBLIC_BASE_URL"] = "https://booking.example/"
    monkeypatch.setattr(
        SMTPEmailService,
        "_send",
        staticmethod(lambda _user, _subject, text, _html=None: messages.append(text)),
    )
    with app.app_context():
        service = SMTPEmailService()
        service.send_verification(user, "verify/a+b")
        service.send_password_reset(user, "reset/c+d")

    assert "https://booking.example/auth/verify?token=verify%2Fa%2Bb" in messages[0]
    assert "https://booking.example/auth/reset?token=reset%2Fc%2Bd" in messages[1]
