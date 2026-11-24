"""Fail when service-package coverage falls below its independent threshold."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    report_path = Path(sys.argv[1] if len(sys.argv) > 1 else "coverage.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    files = report["files"]
    service_files = [
        details
        for name, details in files.items()
        if name.replace("\\", "/").startswith("app/services/")
    ]
    if not service_files:
        print("No app/services files found in coverage report", file=sys.stderr)
        return 1
    covered = sum(item["summary"]["covered_lines"] for item in service_files)
    statements = sum(item["summary"]["num_statements"] for item in service_files)
    percent = covered * 100 / statements if statements else 100.0
    print(f"app/services coverage: {percent:.2f}% ({covered}/{statements} lines); required 85%")
    return 0 if percent >= 85 else 1


if __name__ == "__main__":
    raise SystemExit(main())
