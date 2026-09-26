"""Update-channel fork origin, cache and prefetch regressions for source_check.py."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from hermes_cli import source_check, source_releases
from hermes_cli.update_cmd_git import _is_fork

SHA_A = "a" * 40
SHA_B = "b" * 40


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "hermes-agent"
    root.mkdir()
    (root / ".git").mkdir()
    home = tmp_path / "home"
    home.mkdir()
    (home / "hermes-agent").mkdir()
    (home / "hermes-agent" / ".git").mkdir()
    (root / "install-stamp.json").write_text('{"updateMechanism":"self"}', encoding="utf-8")
    (home / "config.yaml").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr("hermes_cli.config.get_project_root", lambda: root)
    monkeypatch.setattr("hermes_cli.config.detect_install_method", lambda _root: "git")
    return root


def _stub_checkout(monkeypatch, root: Path, *, head: str = SHA_A, origin: str):
    repository_match = source_check._GITHUB_ORIGIN.fullmatch(origin)
    assert repository_match is not None
    co = source_check._Checkout(
        root=root, git="git", embedded=None, head=head, current_branch="main",
        origin=origin, repository=repository_match[1], dirty=False,
    )
    monkeypatch.setattr(source_check, "_read_checkout", lambda *_args, **_kwargs: co)
    monkeypatch.setattr(source_check, "_branch_tip", lambda repository, branch, *_args: (SHA_B, False, None))
    monkeypatch.setattr(
        source_check, "_github_compare",
        lambda current, target, repository: {"ahead_by": 61, "commits": []},
    )


@pytest.mark.parametrize("origin", [
    "https://github.com/Flexpair/hermes-agent.git",
    "git@github.com:Flexpair/hermes-agent.git",
    "https://github.com/flexpair/hermes-agent.git",
])
def test_flexpair_origin_is_a_supported_distribution_not_a_user_fork(origin):
    assert _is_fork(origin) is False


def test_flexpair_origin_uses_its_own_repository_for_compare_cache(checkout, monkeypatch):
    origin = "https://github.com/Flexpair/hermes-agent.git"
    _stub_checkout(monkeypatch, checkout, origin=origin)
    monkeypatch.setattr(source_check, "_github_compare", lambda cur, target, repository: {
        "ahead_by": 61 if repository.lower() == "flexpair/hermes-agent" else 7, "commits": [],
    })
    result = source_check.check_for_updates(force=True)
    assert result["behind"] == 61
    assert result["branch"] == "main"
    cache = json.loads(next((Path(checkout.parents[0]) / "home" / "source-checks").glob("*.json")).read_text())
    assert cache["identity"]["origin"] == origin


def test_compare_api_cache_is_scoped_to_repository(monkeypatch):
    seen = []

    def compare(_current, _target, repository):
        seen.append(repository)
        return {"ahead_by": 61 if repository.lower() == "flexpair/hermes-agent" else 7, "commits": []}

    monkeypatch.setattr(source_check, "_github_compare", compare)
    assert source_check._github_compare_behind(SHA_A, SHA_B, "Flexpair/hermes-agent") == 61
    assert source_check._github_compare_behind(SHA_A, SHA_B, "NousResearch/hermes-agent") == 7
    assert seen == ["Flexpair/hermes-agent", "NousResearch/hermes-agent"]


def test_cache_is_daily_but_invalidated_when_head_moves(checkout, monkeypatch):
    now = [100_000.0]
    _stub_checkout(monkeypatch, checkout, origin="https://github.com/Flexpair/hermes-agent.git")
    monkeypatch.setattr(source_check.time, "time", lambda: now[0])
    monkeypatch.setattr(source_check, "_branch_tip", lambda *_args: (SHA_B, False, None))
    calls = []
    monkeypatch.setattr(source_check, "_github_compare", lambda current, target, repo: (
        calls.append((current, target, repo)) or {"ahead_by": 3, "commits": []}
    ))
    cache = Path(checkout.parent) / "cache.json"
    first = source_check.check_for_updates(install_root=checkout, cache_path=cache, force=True)
    assert first["behind"] == 3
    assert len(calls) == 1

    second = source_check.check_for_updates(install_root=checkout, cache_path=cache)
    assert second["behind"] == 3
    assert len(calls) == 1

    now[0] += source_check._UPDATE_CHECK_CACHE_SECONDS + 1
    source_check.check_for_updates(install_root=checkout, cache_path=cache)
    assert len(calls) == 2


def test_cache_invalidates_when_head_moves(checkout, monkeypatch):
    heads = [SHA_A]
    monkeypatch.setattr(source_check, "_read_checkout", lambda *_args, **_kwargs: source_check._Checkout(
        root=checkout, git="git", embedded=None, head=heads[0], current_branch="main",
        origin="https://github.com/Flexpair/hermes-agent.git", repository="Flexpair/hermes-agent", dirty=False,
    ))
    monkeypatch.setattr(source_check, "_branch_tip", lambda *_args: (SHA_B, False, None))
    calls = []
    monkeypatch.setattr(source_check, "_github_compare", lambda cur, target, repo: (
        calls.append(cur) or {"ahead_by": 3, "commits": []}
    ))
    cache = Path(checkout.parent) / "cache.json"
    assert source_check.check_for_updates(install_root=checkout, cache_path=cache)["behind"] == 3
    heads[0] = "c" * 40
    assert source_check.check_for_updates(install_root=checkout, cache_path=cache)["behind"] == 3
    assert calls == [SHA_A, "c" * 40]


def test_prefetch_is_noop_under_pytest(monkeypatch):
    from hermes_cli import banner

    monkeypatch.setattr(banner, "_update_result", None)
    monkeypatch.setattr(banner, "_update_check_done", threading.Event())
    before = {thread.ident for thread in threading.enumerate()}
    check = MagicMock()
    monkeypatch.setattr(source_check, "check_for_updates", check)
    banner.prefetch_update_check()
    assert banner._update_check_done.is_set()
    check.assert_not_called()
    assert {thread.ident for thread in threading.enumerate()} <= before


def test_prefetch_update_check_remains_non_blocking(monkeypatch):
    from hermes_cli import banner

    monkeypatch.setattr(banner, "_update_result", None)
    done = threading.Event()
    monkeypatch.setattr(banner, "_update_check_done", done)
    monkeypatch.setattr(banner, "_skip_background_prefetch", lambda: False)
    check = MagicMock(return_value={"behind": 5})
    monkeypatch.setattr(source_check, "check_for_updates", check)

    start = time.monotonic()
    banner.prefetch_update_check()

    assert time.monotonic() - start < 1.0
    assert done.wait(timeout=5)
    assert banner._update_result == 5
    check.assert_called_once_with(passive=True)


def test_banner_data_prefetch_is_noop_under_pytest(monkeypatch):
    from hermes_cli import banner

    monkeypatch.setattr(banner, "_banner_data_prefetch_started", False)
    warms = [MagicMock() for _ in range(3)]
    monkeypatch.setattr(banner, "get_git_banner_state", warms[0])
    monkeypatch.setattr(banner, "get_latest_release_tag", warms[1])
    monkeypatch.setattr(banner, "get_available_skills", warms[2])

    banner.prefetch_banner_data()

    assert banner._banner_data_prefetch_started is True
    for warm in warms:
        warm.assert_not_called()


def test_prefetch_banner_data_warms_each_input_on_a_daemon(monkeypatch):
    from hermes_cli import banner

    monkeypatch.setattr(banner, "_banner_data_prefetch_started", False)
    monkeypatch.setattr(banner, "_skip_background_prefetch", lambda: False)
    warms = [MagicMock() for _ in range(3)]
    for name, warm in zip(("get_git_banner_state", "get_latest_release_tag", "get_available_skills"), warms):
        monkeypatch.setattr(banner, name, warm)

    before = {thread.ident for thread in threading.enumerate()}
    banner.prefetch_banner_data()

    deadline = time.monotonic() + 5
    while not all(warm.called for warm in warms) and time.monotonic() < deadline:
        time.sleep(0.005)
    assert banner._banner_data_prefetch_started is True
    assert all(warm.called for warm in warms)
    for warm in warms:
        warm.assert_called_once_with()


def test_flexpair_manual_check_fetches_its_origin_not_upstream(checkout, monkeypatch, capsys):
    from hermes_cli import update_cmd, update_cmd_check

    calls = []
    monkeypatch.setattr(update_cmd, "_m", lambda: SimpleNamespace(PROJECT_ROOT=checkout))
    monkeypatch.setattr(update_cmd, "_get_origin_url", lambda *_: "https://github.com/Flexpair/hermes-agent.git")
    monkeypatch.setattr(update_cmd, "_is_fork", _is_fork)
    monkeypatch.setattr(update_cmd, "_base_git_cmd", lambda: ["git"])
    monkeypatch.setattr(update_cmd_check, "clear_git_debris", lambda _root: None)
    monkeypatch.setattr(update_cmd, "_source_update_channel", lambda **_kwargs: "main")
    monkeypatch.setattr(update_cmd_check, "is_shallow_repository", lambda *_: False)
    monkeypatch.setattr(update_cmd_check, "_fetch", lambda _git, _root, _depth, remote, branch: (
        calls.append((remote, branch)) or SimpleNamespace(returncode=0, stderr="")
    ))
    monkeypatch.setattr(update_cmd_check, "compare_ref_exists", lambda *_: True)
    monkeypatch.setattr(update_cmd_check, "report_rev_list_verdict", lambda *_: None)
    update_cmd._cmd_update_check()
    assert calls == [("origin", "main")]
    capsys.readouterr()


def test_official_ssh_main_fallback_disables_git_prompts(monkeypatch):
    completed = subprocess.CompletedProcess([], 1, stdout="", stderr="auth required")
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return completed

    monkeypatch.setattr(source_check, "_request", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")))
    monkeypatch.setattr(source_check.subprocess, "run", run)
    sha, missing, _failure = source_check._branch_tip(
        "NousResearch/hermes-agent", "main", Path("."), "git", "https://github.com/NousResearch/hermes-agent.git"
    )

    assert sha is None and missing is False
    args, kwargs = next((args, kwargs) for args, kwargs in calls if "ls-remote" in args)
    assert args == ["git", "ls-remote", "--exit-code", "--heads",
                    "https://github.com/NousResearch/hermes-agent.git", "refs/heads/main"]
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert kwargs["env"]["GCM_INTERACTIVE"] == "Never"
