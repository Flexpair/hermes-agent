"""Behavior tests for the executable supply-chain scanner."""

from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER = REPO_ROOT / "scripts" / "ci" / "scan_supply_chain.py"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _run_scanner(repo: Path, base: str, head: str, findings: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(SCANNER),
            "--repo",
            str(repo),
            "--base",
            base,
            "--head",
            head,
            "--findings-file",
            str(findings),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_scanner_reports_critical_patterns_from_added_lines(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "module.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "base")
    base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

    # Build the representative payload from pieces so this test itself does
    # not match the scanner's added-line heuristic in the parent repository.
    decoder = "base64" + ".b64decode"
    executor = "exec(" + decoder + '("cGF5bG9hZA=="))'
    (repo / "module.py").write_text(
        "import base64; " + executor + "\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "critical")
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

    findings = tmp_path / "findings.md"
    result = _run_scanner(repo, base, head, findings)

    assert result.returncode == 0
    assert "found=true" in result.stdout
    assert "base64 decode + exec/eval combo" in findings.read_text(encoding="utf-8")


def test_scanner_ignores_unrelated_added_code(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "module.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "base")
    base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

    (repo / "module.py").write_text("value = 2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "ordinary")
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

    findings = tmp_path / "findings.md"
    result = _run_scanner(repo, base, head, findings)

    assert result.returncode == 0
    assert "found=false" in result.stdout
    assert findings.read_text(encoding="utf-8") == ""
