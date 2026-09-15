"""Behavior tests for the executable supply-chain scanner."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


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


def _base64_exec_source() -> str:
    decoder = "base64" + ".b64decode"
    executor = "exec(" + decoder + '("cGF5bG9hZA=="))'
    return "import base64; " + executor + "\n"


def _obfuscated_subprocess_source() -> str:
    process = "subprocess" + ".run"
    obfuscated = "chr" + "(99)"
    return f'{process}(["sh", "-c", {obfuscated}])\n'


@pytest.mark.parametrize(
    ("filename", "content", "expected"),
    [
        ("payload.pth", "import site\n", ".pth file added or modified"),
        ("module.py", _base64_exec_source(), "base64 decode + exec/eval combo"),
        (
            "module.py",
            _obfuscated_subprocess_source(),
            "subprocess with encoded/obfuscated command",
        ),
        ("setup.py", "from setuptools import setup\n", "Install-hook file added or modified"),
    ],
)
def test_scanner_reports_each_critical_detector(
    tmp_path: Path, filename: str, content: str, expected: str
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "module.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "base")
    base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

    target = repo / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "critical")
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

    findings = tmp_path / "findings.md"
    result = _run_scanner(repo, base, head, findings)

    assert result.returncode == 0
    assert "found=true" in result.stdout
    assert expected in findings.read_text(encoding="utf-8")


def test_scanner_ignores_lockfiles_and_nested_install_hooks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "module.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "base")
    base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

    (repo / "module.py").write_text("value = 2\n", encoding="utf-8")
    (repo / "uv.lock").write_text(_base64_exec_source(), encoding="utf-8")
    nested = repo / "nested" / "setup.py"
    nested.parent.mkdir()
    nested.write_text("from setuptools import setup\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "ordinary")
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

    findings = tmp_path / "findings.md"
    result = _run_scanner(repo, base, head, findings)

    assert result.returncode == 0
    assert "found=false" in result.stdout
    assert findings.read_text(encoding="utf-8") == ""
