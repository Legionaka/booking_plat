def test_components_page_and_frontend_assets_are_served_with_strict_csp(app, monkeypatch):
    monkeypatch.setattr(app.extensions["redis"], "delete", lambda *_args: 0)
    client = app.test_client()

    response = client.get("/dev/components")

    assert response.status_code == 200
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
    assert 'style.setProperty("--mx"' in main_js
    assert 'style.setProperty("--my"' in main_js
