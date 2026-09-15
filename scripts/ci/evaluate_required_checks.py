#!/usr/bin/env python3
"""Evaluate the results of required GitHub Actions jobs.

GitHub exposes the results of jobs listed in ``needs`` as JSON.  Only a
successful job or an intentionally skipped job may pass the fork's aggregate
gate; every other result is a failure.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any


_ALLOWED_RESULTS = frozenset({"success", "skipped"})


def evaluate(needs: dict[str, dict[str, Any]]) -> tuple[dict[str, str], list[str]]:
    """Return compact results and names that must fail the aggregate gate."""
    compact = {
        name: str(info.get("result", "unknown"))
        for name, info in needs.items()
    }
    failed = [
        name for name, result in compact.items() if result not in _ALLOWED_RESULTS
    ]
    return compact, failed


def main() -> int:
    try:
        needs = json.loads(os.environ.get("NEEDS", ""))
    except json.JSONDecodeError as exc:
        print(f"::error::Invalid NEEDS JSON: {exc}")
        return 1
    if not isinstance(needs, dict) or any(
        not isinstance(info, dict) for info in needs.values()
    ):
        print("::error::NEEDS must be a JSON object of job-result objects")
        return 1

    compact, failed = evaluate(needs)
    serialized = json.dumps(compact)
    print(f"needs-json={serialized}")
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(f"needs-json={serialized}\n")

    for name, result in sorted(compact.items()):
        icon = "✅" if result == "success" else (
            "⏭️" if result == "skipped" else "❌"
        )
        print(f"{icon} {name}: {result}")

    if failed:
        print(f"::error::{len(failed)} job(s) failed: {', '.join(failed)}")
        return 1
    print("All checks passed (or were skipped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
