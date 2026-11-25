import re
from pathlib import Path

from app import BASE_CONTENT_SECURITY_POLICY, content_security_policy_for


def test_components_page_and_frontend_assets_are_served_with_strict_csp(
    app, monkeypatch, assert_rendered_page_contract
):
    monkeypatch.setattr(app.extensions["redis"], "delete", lambda *_args: 0)
    client = app.test_client()

    response = client.get("/dev/components")

    assert response.status_code == 200
    assert_rendered_page_contract(response.get_data(as_text=True), "/dev/components")
    assert 'class="ambient-light"' not in response.text
    assert 'id="glass-depths"' in response.text
    assert 'id="type-scale"' in response.text
    assert 'id="colour-tokens"' in response.text
    for label in (
        "Buttons and slots",
        "Status badges",
        "Input, select and textarea",
        "Toast and empty state",
        "Modal, drawer and command palette",
        "Tabs and dropdown",
        "Table and pagination",
        "KPI and chart card",
        "Skeleton, avatar and stepper",
        "Navigation shells",
    ):
        assert label in response.text
    assert "Bricolage Grotesque" in response.text
    assert "Instrument Sans" in response.text
    policy = response.headers["Content-Security-Policy"]
    assert "script-src 'self'" in policy
    assert "style-src 'self';" in policy
    assert "style-src-attr 'none'" in policy
    assert "font-src 'self'" in policy
    assert "form-action 'self'" in policy

    assets = (
        "css/fonts.css",
        "css/tokens.css",
        "css/base.css",
        "css/glass.css",
        "css/typography.css",
        "css/layout.css",
        "css/components/system.css",
        "js/main.js",
        "js/components/surfaces.js",
        "fonts/bricolage-grotesque-v9-latin-regular.woff2",
        "fonts/instrument-sans-v4-latin-regular.woff2",
    )
    for asset in assets:
        asset_response = client.get(f"/static/{asset}")
        assert asset_response.status_code == 200, asset

    main_js = client.get("/static/js/main.js").text
    assert "pointermove" not in main_js
    assert "--mx" not in main_js
    assert "--my" not in main_js


def test_flat_error_pages_are_rendered(app, monkeypatch, assert_rendered_page_contract):
    monkeypatch.setattr(app.extensions["redis"], "delete", lambda *_args: 0)
    client = app.test_client()
    missing = client.get("/page-does-not-exist")
    offline = client.get("/offline")
    assert missing.status_code == 404
    assert offline.status_code == 200
    assert_rendered_page_contract(missing.text, "/404")
    assert_rendered_page_contract(offline.text, "/offline")
    assert "We can’t find that page." in missing.text
    assert "You’re offline right now." in offline.text


def test_customer_portal_routes_render_responsive_flow_shell(
    app, monkeypatch, assert_rendered_page_contract
):
    monkeypatch.setattr(app.extensions["redis"], "delete", lambda *_args: 0)
    client = app.test_client()
    paths = (
        ("/b/fade-lab", "landing"),
        ("/b/fade-lab/book", "services"),
        ("/b/fade-lab/book/time", "time"),
        ("/b/fade-lab/book/review", "review"),
        ("/b/fade-lab/book/confirmed/42", "confirmed"),
        ("/account/bookings", "bookings"),
        ("/account/bookings/42", "detail"),
        ("/account/bookings/42/reschedule", "reschedule"),
        ("/account/bookings/42/rescheduled", "rescheduled"),
        ("/account/bookings/42/cancel", "cancel"),
        ("/account/bookings/42/cancelled", "cancelled"),
        ("/payments/return?booking_id=42", "payment_return"),
        ("/payments/cancel?booking_id=42", "payment_cancelled"),
    )
    for path, view in paths:
        response = client.get(path)
        assert response.status_code == 200, path
        assert f'data-view="{view}"' in response.text
        assert_rendered_page_contract(response.text, path)
        assert "data-demo-banner" in response.text
        assert "data-page-state" in response.text
    assert client.get("/payments/return?booking_id=bad").status_code == 200


def test_owner_portal_routes_render_external_script_shell(
    app, monkeypatch, assert_rendered_page_contract
):
    monkeypatch.setattr(app.extensions["redis"], "delete", lambda *_args: 0)
    client = app.test_client()
    paths = (
        ("/app", "dashboard"),
        ("/app/onboarding", "onboarding"),
        ("/app/42/dashboard", "dashboard"),
        ("/app/42/week", "week"),
        ("/app/42/bookings", "bookings"),
        ("/app/42/services", "services"),
        ("/app/42/staff", "staff"),
        ("/app/42/hours", "hours"),
        ("/app/42/customers", "customers"),
        ("/app/42/payments", "payments"),
        ("/app/42/analytics", "analytics"),
        ("/app/42/settings", "settings"),
        ("/app/42/audit", "audit"),
    )
    for path, section in paths:
        response = client.get(path)
        assert response.status_code == 200, path
        assert f'data-section="{section}"' in response.text
        assert 'style="' not in response.text
        assert_rendered_page_contract(response.text, path)
        assert 'src="/static/js/pages/owner.js"' in response.text
    assert client.get("/app/42/qr.svg").status_code == 401


def test_owner_chart_modules_are_external_flat_and_accessible():
    root = Path(__file__).resolve().parents[2] / "app" / "static" / "js" / "charts"
    expected = {
        "sparkline.js": "BookingCharts.sparkline",
        "area.js": "BookingCharts.area",
        "donut.js": "BookingCharts.donut",
        "heatmap.js": "BookingCharts.heatmap",
        "ring.js": "BookingCharts.ring",
    }
    for filename, function in expected.items():
        source = (root / filename).read_text(encoding="utf-8")
        assert function in source
        assert "gradient" not in source.lower()
    source = (root / "svg.js").read_text(encoding="utf-8")
    assert 'role: "img"' in source
    assert '"aria-label": label' in source


def test_payfast_csp_exception_is_exclusive_to_the_handoff_endpoint(app):
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    assert "payments.payfast_handoff" in endpoints
    handoff_policy = content_security_policy_for("payments.payfast_handoff")
    handoff_form_action = handoff_policy.split("form-action ")[1].split(";")[0]
    assert handoff_form_action == ("'self' https://sandbox.payfast.co.za https://www.payfast.co.za")
    for endpoint in endpoints - {"payments.payfast_handoff"}:
        assert content_security_policy_for(endpoint) == BASE_CONTENT_SECURITY_POLICY
    assert content_security_policy_for(None) == BASE_CONTENT_SECURITY_POLICY


def test_font_faces_exist_and_cover_stylesheet_weights():
    root = Path(__file__).resolve().parents[2]
    css_files = sorted((root / "app" / "static" / "css").glob("*.css"))
    face_css = (root / "app" / "static" / "css" / "fonts.css").read_text(encoding="utf-8")
    face_blocks = re.findall(r"@font-face\s*\{([^}]+)\}", face_css, flags=re.IGNORECASE)
    declared_faces: dict[str, set[str]] = {}

    for block in face_blocks:
        family_match = re.search(r"font-family\s*:\s*['\"]?([^;'\"]+)", block)
        weight_match = re.search(r"font-weight\s*:\s*(\d+)", block)
        url_match = re.search(r"url\(\s*['\"]?([^)'\"]+)", block)
        assert family_match and weight_match and url_match, block
        font_path = (root / "app" / "static" / "css" / url_match.group(1)).resolve()
        assert font_path.is_file(), f"@font-face points to missing font: {font_path}"
        declared_faces.setdefault(family_match.group(1).strip(), set()).add(weight_match.group(1))

    used_weights: set[str] = set()
    for css_file in css_files:
        content = css_file.read_text(encoding="utf-8")
        content = re.sub(r"@font-face\s*\{[^}]+\}", "", content, flags=re.IGNORECASE)
        used_weights.update(re.findall(r"font-weight\s*:\s*(\d+)", content))

    assert declared_faces
    # Every explicit stylesheet weight is available for every self-hosted family,
    # and normal body text has a real 400 face rather than browser synthesis.
    for family, weights in declared_faces.items():
        assert "400" in weights, family
        missing = used_weights - weights
        assert not missing, f"{family} lacks stylesheet weights: {missing}"


def test_components_page_requires_development_or_demo_mode(app, monkeypatch):
    monkeypatch.setattr(app.extensions["redis"], "delete", lambda *_args: 0)
    client = app.test_client()
    original_env = app.config["APP_ENV"]
    original_demo_mode = app.config["DEMO_MODE"]
    try:
        app.config.update(APP_ENV="production", DEMO_MODE=False)
        hidden = client.get("/dev/components")
        assert hidden.status_code == 404

        app.config["DEMO_MODE"] = True
        visible = client.get("/dev/components")
        assert visible.status_code == 200
    finally:
        app.config.update(APP_ENV=original_env, DEMO_MODE=original_demo_mode)


def test_public_landing_page_is_rendered(app, monkeypatch, assert_rendered_page_contract):
    monkeypatch.setattr(app.extensions["redis"], "delete", lambda *_args: 0)
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert_rendered_page_contract(response.text, "/")
    assert "data-landing-page" in response.text
    assert "Bookings that never double up." in response.text
    assert 'href="/b/fade-lab"' in response.text
    assert 'href="/auth/register"' in response.text
    assert 'href="/auth/login?portal=business"' in response.text

    css = client.get("/static/css/components/landing.css")
    assert css.status_code == 200
    js = client.get("/static/js/pages/landing.js")
    assert js.status_code == 200
    assert '<html lang="en">' in response.text
    assert response.text.lower().count("<h1") == 1
    assert "@" not in response.text
    assert "<style" not in response.text
    assert "data:" not in response.text.lower()
    assert 'style="' not in response.text
    assert "gradient" not in response.text.lower()

    app.config["DEMO_MODE"] = False
    demo_off = client.get("/")
    assert "Live demo: sandbox payments only." not in demo_off.text
    app.config["DEMO_MODE"] = True
    demo_on = client.get("/")
    assert "Live demo: sandbox payments only." in demo_on.text

    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Disallow: /app" in robots.text
    assert "Disallow: /account" in robots.text
    assert "Disallow: /platform" in robots.text
    assert "Disallow: /dev" in robots.text

    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "/app" not in sitemap.text
    assert "/account" not in sitemap.text
    assert "/platform" not in sitemap.text
    assert "/dev" not in sitemap.text
