"""Behavior tests for the executable supply-chain scanner."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER = REPO_ROOT / "scripts" / "ci" / "scan_supply_chain.py"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _run_required_gate(
    repo: Path, base: str, head: str, findings: Path
) -> subprocess.CompletedProcess[str]:
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
            "--fail-on-findings",
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_scanner_entrypoint_is_executable() -> None:
    assert SCANNER.exists()
    assert SCANNER.stat().st_mode & 0o111


def _commit(repo: Path, message: str) -> str:
    _git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        message,
    )
    return subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()


@pytest.mark.parametrize(
    ("filename", "content", "expected"),
    [
        ("payload.pth", "import site\n", ".pth file added or modified"),
        (
            "module.py",
            "import base64; exec(base64.b64decode('cGF5bG9hZA=='))\n",
            "base64 decode + exec/eval combo",
        ),
        (
            "module.py",
            'import subprocess; subprocess.run(["sh", "-c", chr(99)])\n',
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
    base = _commit(repo, "base")
    target = repo / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(repo, "add", ".")
    head = _commit(repo, "critical")
    findings = tmp_path / "findings.md"
    result = _run_required_gate(repo, base, head, findings)
    assert result.returncode == 1
    assert "found=true" in result.stdout
    assert expected in findings.read_text(encoding="utf-8")


def test_scanner_ignores_lockfiles_and_nested_install_hooks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "module.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    base = _commit(repo, "base")
    (repo / "module.py").write_text("value = 2\n", encoding="utf-8")
    (repo / "uv.lock").write_text(
        "import base64; exec(base64.b64decode('x'))\n", encoding="utf-8"
    )
    nested = repo / "nested" / "setup.py"
    nested.parent.mkdir()
    nested.write_text("from setuptools import setup\n", encoding="utf-8")
    _git(repo, "add", ".")
    head = _commit(repo, "ordinary")
    findings = tmp_path / "findings.md"
    result = _run_required_gate(repo, base, head, findings)
    assert result.returncode == 0
    assert "found=false" in result.stdout
    assert findings.read_text(encoding="utf-8") == ""
