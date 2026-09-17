"""Behavior tests for the inline supply-chain scanner workflow step.

The scanner intentionally remains in the reusable workflow so the required
job can fail in the same shell that computes its output. These tests execute
that exact step against temporary Git histories instead of reimplementing its
patterns in Python.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "supply-chain-audit.yml"


def _scan_script() -> str:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["scan"]["steps"]
    return next(step["run"] for step in steps if step.get("id") == "scan")


def _run_scan(*, critical: bool) -> str:
    with TemporaryDirectory() as tmp:
        repo = Path(tmp)
        git_env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        }

        def git(*args: str) -> None:
            subprocess.run(
                ["git", *args],
                cwd=repo,
                env=git_env,
                check=True,
                stdout=subprocess.DEVNULL,
            )

        git("init", "-q")
        (repo / "safe.txt").write_text("base\n", encoding="utf-8")
        git("add", "safe.txt")
        git("commit", "-qm", "base")
        base = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip()

        if critical:
            (repo / "payload.pth").write_text("import payload\n", encoding="utf-8")
            git("add", "payload.pth")
        else:
            (repo / "safe.txt").write_text("changed\n", encoding="utf-8")
            git("add", "safe.txt")
        git("commit", "-qm", "change")
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip()

        output = repo / "github-output"
        output.touch()
        script = (
            _scan_script()
            .replace("${{ github.event.pull_request.base.sha }}", base)
            .replace("${{ github.event.pull_request.head.sha }}", head)
        )
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=repo,
            env={**git_env, "GITHUB_OUTPUT": str(output), "GH_TOKEN": ""},
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return output.read_text(encoding="utf-8")


def test_clean_diff_is_not_reported_as_critical() -> None:
    assert "found=false" in _run_scan(critical=False)


def test_pth_addition_is_reported_as_critical() -> None:
    assert "found=true" in _run_scan(critical=True)
