"""A Flexpair checkout cannot be advanced by the bundled update surfaces."""

from pathlib import Path
from types import SimpleNamespace
import os
import subprocess

import pytest

from hermes_cli import banner, main
from hermes_cli.update_contract import evaluate_update_admission


def test_update_gate_refuses_every_checkout(tmp_path):
    refusal = evaluate_update_admission(tmp_path)
    assert refusal is not None
    assert refusal.code == "updates-disabled"
    assert refusal.update_command == "disabled"


def test_cli_update_exits_before_update_preflight(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(main, "_update_preflight_handled", lambda _: pytest.fail("preflight ran"))
    with pytest.raises(SystemExit) as error:
        main.cmd_update(SimpleNamespace(check=False))
    assert error.value.code == 2


def test_passive_update_check_does_not_contact_network(monkeypatch):
    monkeypatch.setattr(banner, "_github_branch_tip", lambda *a, **kw: pytest.fail("network probed"))
    assert banner.check_for_updates() is None


def test_desktop_update_script_refuses_before_touching_install(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/desktop-update/posix.sh"
    install_root = tmp_path / "hermes-agent"
    install_root.mkdir()
    sentinel = install_root / "unchanged"
    sentinel.write_text("fixed")
    before = sorted(path.name for path in tmp_path.iterdir())
    result = subprocess.run(
        ["bash", str(script), "--install-root", str(install_root), "--self-test-gate"],
        capture_output=True, text=True, timeout=5,
    )
    assert result.returncode == 2
    assert "Updates are disabled" in result.stderr
    assert sentinel.read_text() == "fixed"
    assert sorted(path.name for path in install_root.iterdir()) == ["unchanged"]
    assert sorted(path.name for path in tmp_path.iterdir()) == before


@pytest.mark.parametrize("script", ["scripts/install.sh", "setup-hermes.sh"])
@pytest.mark.parametrize("host,termux", [("Darwin", False), ("MINGW64_NT", False), ("Linux", True)])
def test_installer_refuses_non_linux_before_setup(script, host, termux, tmp_path):
    repo = Path(__file__).resolve().parents[2]
    fake_uname = tmp_path / "uname"
    fake_uname.write_text(f"#!/bin/sh\nprintf '%s\\n' '{host}'\n")
    fake_uname.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"
    env["HERMES_HOME"] = str(tmp_path / "hermes-home")
    if termux:
        env["TERMUX_VERSION"] = "1"
    else:
        env.pop("TERMUX_VERSION", None)
        env.pop("PREFIX", None)
    result = subprocess.run(["bash", str(repo / script), "--help"], cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert "requires Linux" in result.stderr
    assert not (tmp_path / "hermes-home").exists()


def test_setup_script_rejects_existing_venv_before_deleting_it(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    script = repo / "setup-hermes.sh"
    script.write_bytes((Path(__file__).resolve().parents[2] / "setup-hermes.sh").read_bytes())
    venv = repo / "venv"
    venv.mkdir()
    sentinel = venv / "do-not-delete"
    sentinel.write_text("unchanged")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uname = fake_bin / "uname"
    uname.write_text("#!/bin/sh\nprintf 'Linux\\n'\n")
    uname.chmod(0o755)
    result = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        timeout=10,
    )
    assert result.returncode == 1
    assert "Updates are disabled" in result.stderr
    assert sentinel.read_text() == "unchanged"
