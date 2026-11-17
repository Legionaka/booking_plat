"""Reject frontend patterns that violate the strict CSP and styling rules."""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (ROOT / "app" / "templates", ROOT / "static")
IGNORED_SUFFIXES = {".woff", ".woff2", ".ttf", ".otf", ".eot"}
DATA_URI = re.compile(r"\bdata:[a-z][a-z0-9.+-]*/", re.IGNORECASE)
STYLE_MUTATION = re.compile(r"setAttribute\s*\(\s*['\"]style['\"]", re.IGNORECASE)


class _TemplatePolicyParser(HTMLParser):
    def __init__(self, path: Path):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.issues: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if "style" in attributes:
            self.issues.append(f"{self.path}: style attribute")
        if any(name.lower().startswith("on") for name, _ in attrs):
            self.issues.append(f"{self.path}: inline event handler")
        if tag.lower() == "style":
            self.issues.append(f"{self.path}: inline style block")
        if tag.lower() == "script" and "src" not in attributes:
            self.issues.append(f"{self.path}: inline script")


def scan_files(paths: tuple[Path, ...] | list[Path]) -> list[str]:
    issues: list[str] = []
    for root in paths:
        if not root.exists():
            continue
        files = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in files:
            if not path.is_file() or path.suffix.lower() in IGNORED_SUFFIXES:
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            if DATA_URI.search(content):
                issues.append(f"{path}: data: URI")
            if STYLE_MUTATION.search(content):
                issues.append(f"{path}: setAttribute('style', ...) mutation")
            if path.suffix.lower() in {".html", ".htm", ".jinja", ".jinja2"}:
                parser = _TemplatePolicyParser(path)
                parser.feed(content)
                issues.extend(parser.issues)
    return issues


def main() -> int:
    issues = scan_files(SCAN_ROOTS)
    if issues:
        print("Frontend policy violations:", file=sys.stderr)
        print("\n".join(f"- {issue}" for issue in issues), file=sys.stderr)
        return 1
    print("Frontend policy scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
