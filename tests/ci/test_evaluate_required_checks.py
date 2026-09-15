"""Behavior tests for the fail-closed required-check evaluator."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
EVALUATOR = REPO_ROOT / "scripts" / "ci" / "evaluate_required_checks.py"
_spec = importlib.util.spec_from_file_location("evaluate_required_checks", EVALUATOR)
if _spec is None or _spec.loader is None:
    raise ImportError("Failed to load evaluate_required_checks.py")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


@pytest.mark.parametrize(
    ("results", "failed"),
    [
        ({"tests": {"result": "success"}}, []),
        ({"tests": {"result": "skipped"}}, []),
        ({"tests": {"result": "failure"}}, ["tests"]),
        ({"tests": {"result": "cancelled"}}, ["tests"]),
        ({"tests": {"result": "timed_out"}}, ["tests"]),
        ({"tests": {"result": "neutral"}}, ["tests"]),
        ({"tests": {"result": "unexpected"}}, ["tests"]),
        ({"tests": {}}, ["tests"]),
    ],
)
def test_evaluate_allows_only_success_or_skipped(results, failed) -> None:
    compact, actual_failed = _module.evaluate(results)
    assert compact == {"tests": results["tests"].get("result", "unknown")}
    assert actual_failed == failed
