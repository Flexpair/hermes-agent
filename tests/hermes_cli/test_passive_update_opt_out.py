"""Fixed Flexpair builds do not check for updates, even when explicitly requested."""
import json
import subprocess
import time

import pytest

from hermes_constants import get_hermes_home


def test_passive_check_obeys_config_before_using_cached_notice(monkeypatch):
    from hermes_cli import __version__, banner

    home = get_hermes_home()
    # The cache is keyed on the checkout's HEAD (an update moving HEAD invalidates it).
    repo_dir = banner._resolve_repo_dir()
    head = banner._git_stdout(["rev-parse", "HEAD"], cwd=repo_dir) if repo_dir else None
    origin = (
        banner._git_stdout(["remote", "get-url", "origin"], cwd=repo_dir)
        if repo_dir
        else None
    )
    canonical = banner._canonical_github_remote(origin)
    repo_slug = (
        canonical.removeprefix("github.com/")
        if canonical.startswith("github.com/")
        else "nousresearch/hermes-agent"
    )
    (home / ".update_check").write_text(
        json.dumps(
            {
                "ts": time.time(),
                "behind": 17,
                "rev": None,
                "ver": __version__,
                "head": head,
                "repo": repo_slug,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("HERMES_REVISION", raising=False)
    config = home / "config.yaml"
    config.write_text("updates:\n  check: true\n", encoding="utf-8")
    assert banner.check_for_updates(passive=True) is None
    config.write_text("updates:\n  check: false\n", encoding="utf-8")
    assert banner.check_for_updates(passive=True) is None
    assert banner.check_for_updates() is None


def test_explicit_check_fetches_local_origin_despite_passive_opt_out(tmp_path, monkeypatch, capsys):
    from hermes_cli import main
    from hermes_cli.update_cmd import _cmd_update_check

    remote = tmp_path / "remote"
    local = tmp_path / "checkout"
    def git(*args):
        return subprocess.run(["git", *map(str, args)], check=True, capture_output=True, text=True)
    git("init", "-b", "main", remote)
    git("-C", remote, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-m", "initial")
    git("clone", remote, local)
    git("-C", remote, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-m", "next")
    monkeypatch.setattr(main, "PROJECT_ROOT", local)
    (get_hermes_home() / "config.yaml").write_text("updates:\n  check: false\n", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        _cmd_update_check()
    assert error.value.code == 2
    output = capsys.readouterr().out
    assert "Updates are disabled" in output
    assert "Fetching from origin" not in output
