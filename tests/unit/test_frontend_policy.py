from pathlib import Path

from scripts.check_frontend_policy import scan_files


def test_frontend_policy_scanner_accepts_external_assets_and_dynamic_properties(tmp_path):
    templates = tmp_path / "templates"
    static = tmp_path / "static"
    templates.mkdir()
    static.mkdir()
    (templates / "page.html").write_text(
        '<link rel="stylesheet" href="/static/site.css">'
        '<script src="/static/site.js" defer></script>',
        encoding="utf-8",
    )
    (static / "site.js").write_text(
        'element.style.setProperty("--progress", "50%");', encoding="utf-8"
    )
    (static / "site.css").write_text(".card { color: black; }", encoding="utf-8")

    assert scan_files([templates, static]) == []


def test_frontend_policy_scanner_rejects_inline_styles_scripts_handlers_and_data_uri(
    tmp_path: Path,
):
    templates = tmp_path / "templates"
    static = tmp_path / "static"
    templates.mkdir()
    static.mkdir()
    (templates / "bad.html").write_text(
        '<div style="color:red" onclick="run()"></div>'
        "<style>.x { color: red; }</style><script>run()</script>",
        encoding="utf-8",
    )
    (static / "bad.css").write_text(
        ".x { background-image: url(data:image/svg+xml,abc); }", encoding="utf-8"
    )

    issues = scan_files([templates, static])

    assert any("style attribute" in issue for issue in issues)
    assert any("inline event handler" in issue for issue in issues)
    assert any("inline style block" in issue for issue in issues)
    assert any("inline script" in issue for issue in issues)
    assert any("data: URI" in issue for issue in issues)
