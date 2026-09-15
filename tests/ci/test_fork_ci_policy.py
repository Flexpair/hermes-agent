"""Regression tests for the fork's Linux CI and supply-chain gates."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CI = REPO_ROOT / ".github" / "workflows" / "ci.yaml"
SUPPLY_CHAIN = REPO_ROOT / ".github" / "workflows" / "supply-chain-audit.yml"
LINUX_CONFIG = REPO_ROOT / ".github" / "workflows" / "flexpair-linux-config.yml"


def test_supply_chain_gate_fails_critical_findings_and_uses_explicit_shas() -> None:
    text = SUPPLY_CHAIN.read_text(encoding="utf-8")

    assert "base_sha:" in text
    assert "head_sha:" in text
    assert 'BASE="${{ inputs.base_sha }}"' in text
    assert 'HEAD="${{ inputs.head_sha }}"' in text
    assert "scripts/ci/scan_supply_chain.py" in text
    assert "Fail on critical findings" in text
    assert "if: steps.scan.outputs.found == 'true'" in text
    assert "exit 1" in text
    assert "CI_REVIEWED" not in text


def test_ci_passes_pull_request_and_push_shas_to_supply_chain_workflow() -> None:
    text = CI.read_text(encoding="utf-8")

    assert "base_sha: ${{ github.event.pull_request.base.sha || github.event.before }}" in text
    assert "head_sha: ${{ github.event.pull_request.head.sha || github.sha }}" in text
    assert "review-labels:" not in text
    gate = text[text.index("all-checks-pass:") :]
    assert "      - supply-chain" in gate
    assert "info['result'] not in ('success', 'skipped')" in text


def test_linux_regression_lane_uses_canonical_runner_and_installer_suite() -> None:
    text = LINUX_CONFIG.read_text(encoding="utf-8")

    assert "uv run --no-sync scripts/run_tests.sh" in text
    assert "tests/scripts/install/test_install_sh_*.py" in text
    assert "tests/scripts/install/test_install_diverged_update.py" in text
    assert "python -m pytest" not in text
