"""Shallow-checkout guard on the `hermes update` apply path (#53479).

`rev-list --count HEAD..origin/<branch>` on a shallow install can enumerate
the entire remote ancestry ("Found 9980 new commit(s)" on a depth-1 clone).
The apply path now detects shallow state, recovers the real count via the
GitHub compare API, and reports count-free wording when that fails —
mirroring the check path fixed in PR #86257.

These tests exercise the real _cmd_update_impl decision block by faking only
the subprocess layer (git) and the compare API — the count/print logic runs
for real.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import hermes_cli.update_cmd as update_cmd

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
        "hermes_cli.banner._github_compare_behind", return_value=api_count
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
