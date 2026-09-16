"""Structural policy tests for the Linux fork's GitHub Actions workflows."""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def _workflow(name: str) -> dict:
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    return data


def test_fork_orchestrator_keeps_linux_lane_and_supply_chain_gate() -> None:
    ci = _workflow("ci.yaml")
    jobs = ci["jobs"]

    assert jobs["tests"]["uses"] == "./.github/workflows/flexpair-linux-config.yml"
    assert jobs["supply-chain"]["uses"] == "./.github/workflows/supply-chain-audit.yml"
    assert "review-labels" not in jobs
    gate = jobs["all-checks-pass"]
    assert "supply-chain" in gate["needs"]
    assert "osv-scanner" not in gate["needs"]
    assert gate["steps"][0]["uses"].startswith("actions/checkout@")


def test_supply_chain_receives_explicit_pr_and_push_shas() -> None:
    with_sha = _workflow("ci.yaml")["jobs"]["supply-chain"]["with"]
    assert with_sha["base_sha"] == "${{ github.event.pull_request.base.sha || github.event.before }}"
    assert with_sha["head_sha"] == "${{ github.event.pull_request.head.sha || github.sha }}"


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
    assert "report_linux_test_scope.py" in commands
    report_step = next(step for step in run if step.get("name") == "Report Linux test scope")
    assert report_step["continue-on-error"] is True


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


def test_supply_chain_workflow_has_direct_critical_failure() -> None:
    supply = _workflow("supply-chain-audit.yml")
    scan_steps = supply["jobs"]["scan"]["steps"]
    failure_steps = [step for step in scan_steps if step.get("name") == "Fail on critical findings"]
    assert len(failure_steps) == 1
    assert failure_steps[0]["if"] == "steps.scan.outputs.found == 'true'"
    assert "exit 1" in failure_steps[0]["run"]
