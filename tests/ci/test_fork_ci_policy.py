"""Structural policy tests for the Linux fork's GitHub Actions workflows."""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def _workflow(name: str) -> dict:
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    return data


def test_fork_orchestrator_keeps_linux_lane() -> None:
    ci = _workflow("ci.yaml")
    jobs = ci["jobs"]

    assert jobs["tests"]["uses"] == "./.github/workflows/flexpair-linux-config.yml"
    assert jobs["tests"]["if"] == "needs.detect.outputs.python == 'true'"


def test_change_detection_allows_for_slow_repository_checkout() -> None:
    detect = _workflow("ci.yaml")["jobs"]["detect"]

    assert detect["timeout-minutes"] >= 5


def test_fork_does_not_require_manual_ci_review_label() -> None:
    jobs = _workflow("ci.yaml")["jobs"]

    assert "review-labels" not in jobs
    assert "review-labels" not in jobs["all-checks-pass"]["needs"]


def test_linux_lane_runs_focused_fork_regressions() -> None:
    job = _workflow("flexpair-linux-config.yml")["jobs"]["test"]
    run = job["steps"]
    commands = "\n".join(step.get("run", "") for step in run)

    assert job["name"] == "Config, installer, and CI tests"
    assert "scripts/run_tests.sh" in commands
    assert "test_*config*.py" in commands
    assert "test_*validation*.py" in commands
    assert "No CLI configuration tests found" in commands
    assert "tests/scripts/install" in commands
    assert "tests/ci" in commands



def test_full_linux_suite_is_weekly_manual_and_four_way_sliced() -> None:
    workflow_path = WORKFLOWS / "flexpair-linux-full.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = _workflow("flexpair-linux-full.yml")
    job = workflow["jobs"]["test"]

    assert "workflow_dispatch:" in workflow_text
    assert "schedule:" in workflow_text
    assert job["strategy"]["matrix"]["slice"] == [1, 2, 3, 4]
    assert job["runs-on"] == "ubuntu-latest"
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert "scripts/run_tests.sh" in commands
    assert job["env"]["HERMES_TEST_SLICE"] == "${{ matrix.slice }}/4"
