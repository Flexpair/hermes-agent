"""Shallow-checkout guard on the ``hermes update`` apply path (#53479, mirroring #86257).

``rev-list --count HEAD..origin/<branch>`` on a shallow install can enumerate
the entire remote ancestry ("Found 9980 new commit(s)" on a depth-1 clone).
The apply path detects shallow state, recovers the real count via the GitHub
compare API, and reports the count as unknown (-1) when that fails.

These run ``_prepare_checkout_for_update`` against real git checkouts (a
depth-1 clone and a full clone of a local origin); only the GitHub compare
API — the network boundary — is faked.
"""

from __future__ import annotations

import subprocess

import pytest

import hermes_cli.main as cli_main
from hermes_cli import update_cmd


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _commit(repo, n):
    (repo / "f.txt").write_text(f"{n}\n", encoding="utf-8")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-q", "-m", f"c{n}")


@pytest.fixture
def origin(tmp_path, monkeypatch):
    for key, value in {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
        "GIT_CONFIG_NOSYSTEM": "1",
    }.items():
        monkeypatch.setenv(key, value)
    repo = tmp_path / "origin"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    for n in range(1, 4):
        _commit(repo, n)
    return repo


def _checkout_behind(tmp_path, origin, monkeypatch, *, shallow):
    """Clone *origin*, then land two new upstream commits and fetch them."""
    clone = tmp_path / ("shallow" if shallow else "full")
    depth = ["--depth", "1"] if shallow else []
    _git(tmp_path, "clone", "-q", *depth, origin.as_uri(), str(clone))
    for n in (4, 5):
        _commit(origin, n)
    _git(clone, "fetch", "-q", *depth, "origin", "main")
    monkeypatch.setattr(cli_main, "PROJECT_ROOT", clone)
    return clone


def _count(monkeypatch, *, api, origin_url="https://github.com/NousResearch/hermes-agent.git"):
    clone = cli_main.PROJECT_ROOT
    subprocess.run(["git", "remote", "set-url", "origin", origin_url], cwd=clone,
                   check=True, capture_output=True, text=True)
    consulted = []
    monkeypatch.setattr(update_cmd, "_get_origin_url", lambda *_args: origin_url)

    def fake_compare(head_sha, target_sha, repository=None):
        consulted.append((head_sha, target_sha, repository))
        return api

    monkeypatch.setattr("hermes_cli.source_check._github_compare_behind", fake_compare)
    plan = update_cmd._prepare_checkout_for_update(
        ["git"], "main", "main", is_fork=False, assume_yes=True, gateway_mode=False,
        gw_input_fn=input, switch_branch=False, _windows_gateway_resume=None)
    return plan.commit_count, consulted


def test_full_clone_keeps_exact_count_without_the_api(tmp_path, origin, monkeypatch):
    _checkout_behind(tmp_path, origin, monkeypatch, shallow=False)
    monkeypatch.setattr("hermes_cli.update_cmd._is_shallow_checkout", lambda _git_cmd: False)
    count, consulted = _count(monkeypatch, api=999)
    assert count == 2
    assert consulted == []


def test_explicit_flexpair_check_does_not_redirect_main_to_upstream(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from hermes_cli import update_cmd_check, update_cmd_git

    calls = []

    def fake_git(git_cmd, root, args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(update_cmd_check, "_git", fake_git)
    monkeypatch.setattr(
        update_cmd_check,
        "_uc",
        lambda: SimpleNamespace(
            _get_origin_url=lambda *_: "https://github.com/Flexpair/hermes-agent.git",
            _is_fork=update_cmd_git._is_fork,
            _no_prompt_git_kwargs=lambda: {},
        ),
    )

    result, compare_ref = update_cmd_check.fetch_compare_branch(["git"], tmp_path, "main", [])

    assert result.returncode == 0
    assert compare_ref == "origin/main"
    assert calls == [["fetch", "origin", "main"]]


def test_shallow_compare_uses_the_remote_repository_for_its_ref(tmp_path, monkeypatch):
    from hermes_cli import source_check
    from hermes_cli import update_cmd_check

    calls = []

    def fake_git(_git_cmd, _root, args, **_kwargs):
        calls.append(args)
        output = {
            ("rev-parse", "HEAD"): "a" * 40,
            ("rev-parse", "origin/main"): "b" * 40,
            ("remote", "get-url", "origin"): "https://github.com/Flexpair/hermes-agent.git",
        }.get(tuple(args), "")
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")

    monkeypatch.setattr(update_cmd_check, "_git", fake_git)
    monkeypatch.setattr(source_check, "_github_compare_behind", lambda *_args, **_kwargs: 12)

    assert update_cmd_check.compare_shallow_revisions(["git"], tmp_path, "origin/main") == 12
    assert ["remote", "get-url", "origin"] in calls


def test_shallow_count_is_recovered_via_compare_api(tmp_path, origin, monkeypatch):
    """FAIL-BEFORE: the shallow rev-list number was reported as the commit count."""
    clone = _checkout_behind(tmp_path, origin, monkeypatch, shallow=True)
    count, consulted = _count(monkeypatch, api=12)
    assert count == 12
    head = subprocess.run(["git", "rev-parse", "HEAD", "origin/main"], cwd=clone,
                          check=True, capture_output=True, text=True).stdout.split()
    assert consulted == [(head[0], head[1], "nousresearch/hermes-agent")]


def test_shallow_flexpair_count_uses_own_compare_repository(tmp_path, origin, monkeypatch):
    clone = _checkout_behind(tmp_path, origin, monkeypatch, shallow=True)
    count, consulted = _count(
        monkeypatch, api=12, origin_url="https://github.com/Flexpair/hermes-agent.git"
    )
    assert count == 12
    assert consulted == [(
        subprocess.run(["git", "rev-parse", "HEAD"], cwd=clone, check=True, capture_output=True, text=True).stdout.strip(),
        subprocess.run(["git", "rev-parse", "origin/main"], cwd=clone, check=True, capture_output=True, text=True).stdout.strip(),
        "flexpair/hermes-agent",
    )]


def test_shallow_count_offline_is_unknown_not_bogus(tmp_path, origin, monkeypatch):
    _checkout_behind(tmp_path, origin, monkeypatch, shallow=True)
    count, _ = _count(monkeypatch, api=None)
    assert count == -1


def test_shallow_local_ahead_is_up_to_date(tmp_path, origin, monkeypatch):
    """compare says 0 behind (local is ahead): the apply path takes the up-to-date branch."""
    _checkout_behind(tmp_path, origin, monkeypatch, shallow=True)
    count, _ = _count(monkeypatch, api=0)
    assert count == 0
