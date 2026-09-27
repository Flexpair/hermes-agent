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
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import hermes_cli.main as cli_main
from hermes_cli import source_check, update_cmd


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


def _count(monkeypatch, *, api):
    consulted = []

    def fake_compare(head_sha, target_sha, repository=None):
        consulted.append((head_sha, target_sha))
        return api

    monkeypatch.setattr(source_check, "_github_compare_behind", fake_compare)
    plan = update_cmd._prepare_checkout_for_update(
        ["git"], "main", "main", is_fork=False, assume_yes=True, gateway_mode=False,
        gw_input_fn=input, switch_branch=False, _windows_gateway_resume=None)
    return plan.commit_count, consulted


def test_full_clone_keeps_exact_count_without_the_api(tmp_path, origin, monkeypatch):
    _checkout_behind(tmp_path, origin, monkeypatch, shallow=False)
    count, consulted = _count(monkeypatch, api=999)
    assert count == 2
    assert consulted == []


def test_shallow_count_is_recovered_via_compare_api(tmp_path, origin, monkeypatch):
    """FAIL-BEFORE: the shallow rev-list number was reported as the commit count."""
    clone = _checkout_behind(tmp_path, origin, monkeypatch, shallow=True)
    count, consulted = _count(monkeypatch, api=12)
    assert count == 12
    head = subprocess.run(["git", "rev-parse", "HEAD", "origin/main"], cwd=clone,
                          check=True, capture_output=True, text=True).stdout.split()
    assert consulted == [tuple(head)]


def test_shallow_count_offline_is_unknown_not_bogus(tmp_path, origin, monkeypatch):
    _checkout_behind(tmp_path, origin, monkeypatch, shallow=True)
    count, _ = _count(monkeypatch, api=None)
    assert count == -1


def test_shallow_local_ahead_is_up_to_date(tmp_path, origin, monkeypatch):
    """compare says 0 behind (local is ahead): the apply path takes the up-to-date branch."""
    _checkout_behind(tmp_path, origin, monkeypatch, shallow=True)
    count, _ = _count(monkeypatch, api=0)
    assert count == 0



SHA_A = "a" * 40
SHA_B = "b" * 40


def _run_count_block(
    *,
    shallow: bool,
    raw_count: str,
    api_count: int | None,
    origin: str = "https://github.com/NousResearch/hermes-agent.git",
) -> tuple[int, MagicMock]:
    """Call the production preparation function with Git and API boundaries mocked."""
    def fake_git(
        _git_cmd, args, cwd=None, *, check=False, network=False
    ) -> MagicMock:
        if args[:2] == ["rev-list", "HEAD..origin/main"]:
            return MagicMock(returncode=0, stdout=f"{raw_count}\n", stderr="")
        if args == ["rev-parse", "--is-shallow-repository"]:
            return MagicMock(
                returncode=0, stdout=("true\n" if shallow else "false\n"), stderr=""
            )
        if args == ["rev-parse", "HEAD"]:
            return MagicMock(returncode=0, stdout=f"{SHA_A}\n", stderr="")
        if args == ["rev-parse", "origin/main"]:
            return MagicMock(returncode=0, stdout=f"{SHA_B}\n", stderr="")
        raise AssertionError(f"unexpected git call: {args}")

    main = SimpleNamespace(
        PROJECT_ROOT=Path.cwd(),
        _get_origin_url=MagicMock(return_value=origin),
        _stash_local_changes_if_needed=MagicMock(return_value=None),
    )
    with patch.object(update_cmd, "_git_run", side_effect=fake_git), patch.object(
        update_cmd,
        "_apply_parked_branch_guard",
        return_value=(False, False, None),
    ), patch.object(update_cmd, "_m", return_value=main), patch(
        "hermes_cli.source_check._github_compare_behind", return_value=api_count
    ) as compare:
        plan = update_cmd._prepare_checkout_for_update(
            ["git"],
            "main",
            "main",
            is_fork=False,
            assume_yes=True,
            gateway_mode=False,
            gw_input_fn=None,
            switch_branch=False,
            _windows_gateway_resume=None,
        )
    return plan.commit_count, compare


def test_full_clone_keeps_exact_count() -> None:
    count, _ = _run_count_block(shallow=False, raw_count="7", api_count=None)
    assert count == 7


def test_shallow_bogus_count_recovers_via_compare_api() -> None:
    """FAIL-BEFORE: reported the bogus 9980 as 'Found 9980 new commit(s)'."""
    count, _ = _run_count_block(shallow=True, raw_count="9980", api_count=12)
    assert count == 12


def test_shallow_flexpair_uses_flexpair_compare_api() -> None:
    count, compare = _run_count_block(
        shallow=True,
        raw_count="9980",
        api_count=12,
        origin="https://github.com/Flexpair/hermes-agent.git",
    )
    assert count == 12
    compare.assert_called_once_with(SHA_A, SHA_B, "flexpair/hermes-agent")


def test_shallow_bogus_count_offline_reports_unknown() -> None:
    count, _ = _run_count_block(shallow=True, raw_count="9980", api_count=None)
    assert count == -1


def test_shallow_local_ahead_treated_as_up_to_date() -> None:
    count, _ = _run_count_block(shallow=True, raw_count="3", api_count=0)
    assert count == 0


def test_shallow_zero_count_short_circuits_without_api() -> None:
    got, compare = _run_count_block(shallow=True, raw_count="0", api_count=None)
    # The block only consults the API when count > 0; a 0 count is trustworthy
    # (HEAD == origin tip counts 0 even on shallow graphs).
    assert got == 0
    compare.assert_not_called()
