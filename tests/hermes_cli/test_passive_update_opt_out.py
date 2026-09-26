"""Passive opt-out disables background notices without blocking explicit checks."""

import subprocess
from unittest.mock import patch

from hermes_constants import get_hermes_home


def test_passive_check_obeys_config_before_using_cached_notice(tmp_path, monkeypatch):
    from hermes_cli import source_check

    root = tmp_path / "checkout"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "install-stamp.json").write_text('{"updateMechanism":"self"}', encoding="utf-8")
    home = get_hermes_home()
    (home / "config.yaml").write_text("updates:\n  check: false\n", encoding="utf-8")
    monkeypatch.setattr("hermes_cli.config.get_project_root", lambda: root)
    monkeypatch.setattr("hermes_cli.config.detect_install_method", lambda _root: "git")
    monkeypatch.setattr(source_check, "_unsupported_reason", lambda *a, **kw: None)

    with patch.object(source_check, "_read_checkout") as read_checkout:
        assert source_check.check_for_updates(home=home, passive=True)["reason"] == "disabled"
        read_checkout.assert_not_called()


def test_explicit_check_fetches_local_origin_despite_passive_opt_out(tmp_path, monkeypatch, capsys):
    from hermes_cli.update_cmd import _cmd_update_check

    remote = tmp_path / "remote"
    local = tmp_path / "checkout"

    def git(*args):
        return subprocess.run(["git", *map(str, args)], check=True, capture_output=True, text=True)

    git("init", "-b", "main", remote)
    git("-C", remote, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-m", "initial")
    git("clone", remote, local)
    git("-C", remote, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-m", "next")
    home = get_hermes_home()
    (home / "config.yaml").write_text("updates:\n  check: false\n", encoding="utf-8")
    monkeypatch.setattr("hermes_cli.update_owning_install.owning_install_root", lambda _root: None)
    monkeypatch.setattr("hermes_cli.update_contract.evaluate_update_admission", lambda _root: None)
    monkeypatch.setattr("hermes_cli.update_cmd._m", lambda: type("Project", (), {"PROJECT_ROOT": local})())
    _cmd_update_check()
    output = capsys.readouterr().out
    assert "Fetching from origin" in output
    assert "1 commit" in output