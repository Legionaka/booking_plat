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
    assert 'class="ambient-light"' in response.text
    assert 'id="glass-depths"' in response.text
    assert 'id="type-scale"' in response.text
    assert 'id="colour-tokens"' in response.text
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
        "js/main.js",
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


def test_payfast_csp_exception_is_exclusive_to_the_handoff_endpoint(app):
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    assert "payments.payfast_handoff" in endpoints
    handoff_policy = content_security_policy_for("payments.payfast_handoff")
    handoff_form_action = handoff_policy.split("form-action ")[1].split(";")[0]
    assert handoff_form_action == (
        "'self' https://sandbox.payfast.co.za https://www.payfast.co.za"
    )
    for endpoint in endpoints - {"payments.payfast_handoff"}:
        assert content_security_policy_for(endpoint) == BASE_CONTENT_SECURITY_POLICY
    assert content_security_policy_for(None) == BASE_CONTENT_SECURITY_POLICY


def test_font_faces_exist_and_cover_stylesheet_weights():
    root = Path(__file__).resolve().parents[2]
    css_files = sorted((root / "static" / "css").glob("*.css"))
    face_css = (root / "static" / "css" / "fonts.css").read_text(encoding="utf-8")
    face_blocks = re.findall(r"@font-face\s*\{([^}]+)\}", face_css, flags=re.IGNORECASE)
    declared_faces: dict[str, set[str]] = {}

    for block in face_blocks:
        family_match = re.search(r"font-family\s*:\s*['\"]?([^;'\"]+)", block)
        weight_match = re.search(r"font-weight\s*:\s*(\d+)", block)
        url_match = re.search(r"url\(\s*['\"]?([^)'\"]+)", block)
        assert family_match and weight_match and url_match, block
        font_path = (root / "static" / "css" / url_match.group(1)).resolve()
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
