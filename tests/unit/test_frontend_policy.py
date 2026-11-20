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


def test_frontend_policy_scanner_rejects_gradients_masks_and_gradient_text(tmp_path: Path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "bad.css").write_text(
        ".a{background:linear-gradient(red,blue)}"
        ".b{background:repeating-radial-gradient(red,blue)}"
        ".c{mask-image:linear-gradient(transparent,black)}"
        ".d{-webkit-mask:linear-gradient(transparent,black)}"
        ".e{background-clip:text}",
        encoding="utf-8",
    )
    (static / "bad.svg").write_text(
        '<svg><linearGradient id="a"/><radialGradient id="b"/></svg>',
        encoding="utf-8",
    )

    issues = scan_files([static])

    assert len(issues) == 2
    assert all("gradient or mask fade" in issue for issue in issues)
