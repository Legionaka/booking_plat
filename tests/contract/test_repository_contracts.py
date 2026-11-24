"""Repository documentation and configuration consistency contracts."""

import json
import re
from pathlib import Path

from app import create_app

ROOT = Path(__file__).resolve().parents[2]


def test_readme_project_structure_paths_exist():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Project structure", 1)[1].split("\n## ", 1)[0]
    tree = section.split("```text", 1)[1].split("```", 1)[0]
    paths: list[str] = []
    parents: list[tuple[int, str]] = []
    for line in tree.splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        while parents and parents[-1][0] >= indent:
            parents.pop()
        part = line.strip().removesuffix("/")
        path = "/".join([*(parent for _, parent in parents), part])
        paths.append(path)
        if line.strip().endswith("/"):
            parents.append((indent, part))

    missing = [path for path in paths if not (ROOT / path).exists()]

    assert not missing, f"README project structure paths do not exist: {missing}"


def test_readme_and_docs_internal_markdown_links_resolve():
    markdown_files = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    link_pattern = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
    broken: list[str] = []
    for source in markdown_files:
        content = source.read_text(encoding="utf-8", errors="replace")
        for target in link_pattern.findall(content):
            target = target.strip().split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            path = target.split("#", 1)[0]
            if path and not (source.parent / path).resolve().exists():
                broken.append(f"{source.relative_to(ROOT)} -> {target}")

    assert not broken, "Broken internal Markdown links: " + "; ".join(broken)


def test_registered_api_routes_are_documented():
    application = create_app({"TESTING": True})
    documented = (ROOT / "docs/api.md").read_text(encoding="utf-8").replace("...", "")
    missing = []
    for rule in application.url_map.iter_rules():
        if not rule.rule.startswith("/api/"):
            continue
        path = re.sub(r"<(?:(?:int|float|path|string|uuid):)?[^>]+>", "{}", rule.rule)
        compatible = re.escape(path).replace(r"\{\}", "[^/]+")
        if not re.search(compatible, documented):
            missing.append(f"{','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))} {rule.rule}")

    assert not missing, "Undocumented API routes: " + "; ".join(missing)


def test_openapi_paths_and_methods_match_registered_api_routes():
    spec = json.loads((ROOT / "docs/openapi.yaml").read_text(encoding="utf-8"))
    documented = {
        (path, method.upper())
        for path, operations in spec["paths"].items()
        for method in operations
    }
    registered = set()
    for rule in create_app({"TESTING": True}).url_map.iter_rules():
        if not rule.rule.startswith("/api/"):
            continue
        path = re.sub(
            r"<(?:(?:int|float|path|string|uuid):)?([^>]+)>", r"{\1}", rule.rule
        )
        registered.update((path, method) for method in rule.methods - {"HEAD", "OPTIONS"})

    assert documented == registered, (
        f"OpenAPI drift; missing={sorted(registered - documented)}, "
        f"stale={sorted(documented - registered)}"
    )


def test_render_blueprint_has_expected_services_and_runtime_commands():
    source = (ROOT / "render.yaml").read_text(encoding="utf-8")
    required = (
        "name: booking-platform-web",
        "name: booking-platform-worker",
        "name: booking-platform-scheduler",
        "runtime: docker",
        "preDeployCommand: flask --app app:create_app db upgrade",
        "healthCheckPath: /ready",
        "name: booking-platform-production",
        "key: APP_ENV",
        "key: EMAIL_BACKEND",
        "key: EMAIL_PROVIDER",
        "key: EMAIL_API_KEY",
        "key: PAYFAST_SANDBOX",
    )
    missing = [value for value in required if value not in source]
    assert not missing, f"Render blueprint is missing required configuration: {missing}"
    assert source.count("runtime: docker") == 3
    assert source.count("fromService:") >= 6
    assert "fromDatabase:" in source


def test_environment_variables_read_in_code_are_documented():
    files = [
        *(ROOT / "app").rglob("*.py"),
        *(ROOT / "scripts").glob("*.py"),
        *(ROOT / "tests").rglob("*.py"),
    ]
    env_read = re.compile(
        r"(?:os\.getenv|os\.environ\.get)\(\s*['\"]([A-Z][A-Z0-9_]*)['\"]"
        r"|os\.environ\[['\"]([A-Z][A-Z0-9_]*)['\"]\]"
    )
    variables = {
        next(group for group in match.groups() if group)
        for path in files
        for match in env_read.finditer(path.read_text(encoding="utf-8", errors="ignore"))
    }
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    environment = (ROOT / "docs/environment.md").read_text(encoding="utf-8")
    missing = sorted(name for name in variables if name not in example or name not in environment)

    assert not missing, (
        "Environment variables missing from .env.example or docs/environment.md: "
        f"{missing}"
    )
