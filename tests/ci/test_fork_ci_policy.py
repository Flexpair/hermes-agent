"""Workflow policy tests for the Linux fork's GitHub Actions workflows."""

from __future__ import annotations

from pathlib import Path

import json


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def _workflow(name: str) -> dict:
    path = WORKFLOWS / name
    if name == "ci.yaml":
        text = path.read_text(encoding="utf-8").replace("on:", '"on":', 1)
        text = text.replace("${{", "__GH_EXPR_OPEN__").replace("}}", "__GH_EXPR_CLOSE__")
        import subprocess
        return json.loads(subprocess.run(
            ["ruby", "-e", "require 'yaml'; require 'json'; require 'date'; puts JSON.generate(YAML.safe_load(STDIN.read, permitted_classes: [Date], aliases: true))"],
            input=text, capture_output=True, text=True, check=True,
        ).stdout)
    import hermes_yaml as yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_fork_orchestrator_keeps_linux_lane() -> None:
    ci = _workflow("ci.yaml")
    jobs = ci["jobs"]

    assert jobs["tests"]["uses"] == "./.github/workflows/flexpair-linux-config.yml"
    assert jobs["tests"]["if"] == "needs.detect.outputs.python == 'true'"


def test_change_detection_allows_for_slow_repository_checkout() -> None:
    detect = _workflow("ci.yaml")["jobs"]["detect"]

    assert detect["timeout-minutes"] >= 5


def test_bootstrap_installer_is_gated_on_classified_changes() -> None:
    job = _workflow("ci.yaml")["jobs"]["bootstrap-installer"]

    assert job["uses"] == "./.github/workflows/bootstrap-installer.yml"
    assert job["if"] == "inputs.release == true || needs.detect.outputs.bootstrap == 'true'"
    assert "bootstrap-installer" in _workflow("ci.yaml")["jobs"]["all-checks-pass"]["needs"]


def test_fork_does_not_require_manual_ci_review_label() -> None:
    jobs = _workflow("ci.yaml")["jobs"]

    assert "review-labels" not in jobs
    assert "review-labels" not in jobs["all-checks-pass"]["needs"]


def test_fork_does_not_run_duplicate_js_autofix() -> None:
    assert not (WORKFLOWS / "js-autofix.yml").exists()


def test_fork_keeps_expensive_docker_advisory_off_pull_requests() -> None:
    workflow = _workflow("docker.yml")
    triggers = workflow.get(True, workflow.get("on", {}))

    assert "pull_request" not in triggers
    assert "release" not in triggers
    assert "push" in triggers
    assert "workflow_call" in triggers


def test_supply_chain_findings_fail_directly() -> None:
    scan = _workflow("supply-chain-audit.yml")["jobs"]["scan"]
    fail_step = next(
        step
        for step in scan["steps"]
        if step["name"] == "Fail on scanner findings or errors"
    )

    assert fail_step["if"] == (
        "always() && (steps.scan.outputs.found == 'true' || "
        "steps.scan.outputs.scan_rc != '0')"
    )
    assert "exit 1" in fail_step["run"]
    assert 'git fetch --no-tags origin "$HEAD"' in scan["steps"][1]["run"]
    assert 'git rev-parse FETCH_HEAD' in scan["steps"][1]["run"]

    bounds = _workflow("supply-chain-audit.yml")["jobs"]["dep-bounds"]
    bounds_run = next(
        step["run"] for step in bounds["steps"] if step.get("id") == "bounds"
    )
    assert "in_hunk = False" in bounds_run


def test_supply_chain_behavior_tests_are_in_required_lane() -> None:
    job = _workflow("flexpair-linux-config.yml")["jobs"]["test"]
    commands = "\n".join(step.get("run", "") for step in job["steps"])

    assert "tests/ci/test_supply_chain_scanner.py" in commands


def test_linux_lane_runs_focused_fork_regressions() -> None:
    job = _workflow("flexpair-linux-config.yml")["jobs"]["test"]
    run = job["steps"]
    commands = "\n".join(step.get("run", "") for step in run)

    assert job["name"] == "Config, installer, and CI tests"
    assert "scripts/run_tests.sh" in commands
    assert "test_*config*.py" in commands
    assert "test_*validation*.py" in commands
    assert "No CLI configuration tests found" in commands
    assert "tests/hermes_cli/test_source_check.py" in commands
    assert "tests/hermes_cli/test_update_apply_shallow_count.py" in commands
    assert "tests/hermes_cli/test_update_behind_count_recovery.py" in commands
    assert "tests/hermes_cli/test_passive_update_opt_out.py" in commands
    assert "tests/scripts/install" in commands
    assert "tests/ci" in commands



def test_full_linux_suite_is_weekly_manual_and_four_way_sliced() -> None:
    workflow = _workflow("flexpair-linux-full.yml")
    triggers = workflow[True]
    job = workflow["jobs"]["test"]

    assert "workflow_dispatch" in triggers
    assert "schedule" in triggers
    assert job["strategy"]["matrix"]["slice"] == [1, 2, 3, 4]
    assert job["runs-on"] == "ubuntu-latest"
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert "scripts/run_tests.sh" in commands
    assert job["env"]["HERMES_TEST_SLICE"] == "${{ matrix.slice }}/4"
