"""Behavior tests for the additive upstream CI proof used by Flexpair's fork workflow."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "flexpair" / "ci_proof.py"
_SPEC = importlib.util.spec_from_file_location("flexpair_ci_proof", SCRIPT)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("Failed to load flexpair/ci_proof.py")
proof = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = proof
_SPEC.loader.exec_module(proof)


def _added_records():
    return [("A", path) for path in proof.EXPECTED_FORK_ADDITIONS]


def _run(**overrides):
    run = {
        "id": 123456,
        "name": "CI",
        "path": ".github/workflows/ci.yaml",
        "head_sha": "a" * 40,
        "head_branch": "main",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "html_url": "https://github.com/NousResearch/hermes-agent/actions/runs/123456",
        "repository": {"full_name": "NousResearch/hermes-agent"},
    }
    return {**run, **overrides}


def _jobs(**overrides):
    jobs = [
        {"name": "JS & TS checks / JS & TS checks", "status": "completed", "conclusion": "success"},
        {"name": "Python tests / Run tests (1/2)", "status": "completed", "conclusion": "success"},
        {"name": "Python tests / Run tests (2/2)", "status": "completed", "conclusion": "success"},
        {"name": "All required checks pass (v2)", "status": "completed", "conclusion": "success"},
    ]
    for job in jobs:
        if job["name"] in overrides:
            job.update(overrides[job["name"]])
    return jobs


def _api_payloads(run=None, jobs=None, expected_token="test-token"):
    run = _run() if run is None else run
    jobs = _jobs() if jobs is None else jobs

    def fetch(url, token):
        assert token == expected_token
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        if parsed.path.endswith("/actions/workflows/ci.yaml/runs"):
            assert query["event"] == ["push"]
            assert query["head_sha"] == ["a" * 40]
            assert query["branch"] == ["main"]
            return {"total_count": 1, "workflow_runs": [run]}
        if parsed.path.endswith("/actions/runs/123456/jobs"):
            return {"total_count": len(jobs), "jobs": jobs}
        raise AssertionError(f"Unexpected GitHub API URL: {url}")

    return fetch


def test_manifest_accepts_reviewed_paths_including_ci_proof_additions():
    newly_requested = {
        ".github/workflows/flexpair-ci.yml",
        "flexpair/ci_proof.py",
        "tests/ci/test_flexpair_ci_proof.py",
        "flexpair/ci_supply_chain.py",
        "tests/ci/test_flexpair_ci_supply_chain.py",
    }
    assert newly_requested <= set(proof.EXPECTED_FORK_ADDITIONS)
    proof.verify_additive_diff(_added_records())


def _git(repo, env, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, env=env, check=True,
        capture_output=True, timeout=10,
    ).stdout.decode("utf-8").strip()


@pytest.fixture
def upstream_checkout(tmp_path, monkeypatch):
    git = shutil.which("git")
    if git is None:
        pytest.skip("git not installed")
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    env = os.environ.copy()
    _git(repo, env, "init", "-q")
    _git(repo, env, "config", "user.email", "ci-proof@example.invalid")
    _git(repo, env, "config", "user.name", "CI proof test")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, env, "add", "base.txt")
    _git(repo, env, "commit", "-qm", "upstream base")
    base = _git(repo, env, "rev-parse", "HEAD")
    _git(repo, env, "update-ref", "refs/remotes/upstream/main", base)
    return repo, env, base


def _commit_file(repo, env, name, content):
    (repo / name).write_text(content, encoding="utf-8")
    _git(repo, env, "add", name)
    _git(repo, env, "commit", "-qm", f"add {name}")
    return _git(repo, env, "rev-parse", "HEAD")


def test_merge_base_tracks_new_upstream_commit_when_candidate_contains_it(upstream_checkout):
    repo, env, base = upstream_checkout
    _git(repo, env, "checkout", "-q", "-b", "candidate-before-upstream")
    _commit_file(repo, env, "candidate.txt", "candidate\n")
    _git(repo, env, "checkout", "-q", "-b", "upstream-next", base)
    upstream = _commit_file(repo, env, "upstream.txt", "upstream\n")
    _git(repo, env, "update-ref", "refs/remotes/upstream/main", upstream)
    _git(repo, env, "checkout", "-q", "-b", "candidate-on-upstream", upstream)
    candidate = _commit_file(repo, env, "fork.txt", "fork\n")
    assert proof.find_upstream_anchor(repo)[1:] == (upstream, candidate)


def test_advanced_upstream_not_in_candidate_uses_its_actual_merge_base(upstream_checkout):
    repo, env, base = upstream_checkout
    _git(repo, env, "checkout", "-q", "-b", "fork-candidate")
    candidate = _commit_file(repo, env, "fork-only.txt", "fork\n")
    _git(repo, env, "checkout", "-q", "-b", "upstream-next", base)
    upstream = _commit_file(repo, env, "upstream.txt", "upstream\n")
    _git(repo, env, "update-ref", "refs/remotes/upstream/main", upstream)
    _git(repo, env, "checkout", "-q", "fork-candidate")
    assert proof.find_upstream_anchor(repo)[1:] == (base, candidate)


@pytest.mark.parametrize(
    "changes",
    [
        [("M", "apps/desktop/src/plugins/flexpair-color-palette/plugin.tsx")],
        [("D", "apps/desktop/src/plugins/flexpair-color-palette/plugin.tsx"),
         ("A", "apps/desktop/src/plugins/flexpair-color-palette/renamed-plugin.tsx")],
        _added_records() + [("A", "unreviewed.py")],
        _added_records()[:-1],
        _added_records() + [("A", "../outside-repository")],
        _added_records() + [("R100", "old-name\0new-name")],
    ],
    ids=["modification", "rename", "unknown-addition", "missing-expected-addition", "path-escape", "rename-status"],
)
def test_additive_path_policy_rejects_every_non_exact_patch(changes):
    with pytest.raises(proof.ProofError):
        proof.verify_additive_diff(changes)


def test_success_requires_the_exact_upstream_push_run_and_named_jobs():
    result = proof.verify_upstream_ci("a" * 40, "test-token", api_get_json=_api_payloads())
    assert result.anchor == "a" * 40
    assert result.run_id == 123456
    assert result.run_url == "https://github.com/NousResearch/hermes-agent/actions/runs/123456"
    assert result.verified_jobs == proof.REQUIRED_JOB_NAMES


@pytest.mark.parametrize(
    "overrides",
    [
        {"head_sha": "b" * 40},
        {"repository": {"full_name": "Flexpair/hermes-agent"}},
        {"path": ".github/workflows/tests.yml"},
        {"event": "pull_request"},
        {"head_branch": "feature"},
        {"status": "in_progress"},
        {"conclusion": "failure"},
        {"name": "Other workflow"},
        {"html_url": "https://evil.example/actions/runs/123456"},
    ],
    ids=["wrong-sha", "wrong-repository", "wrong-workflow", "wrong-event", "wrong-branch", "incomplete", "failed", "wrong-name", "unsafe-run-url"],
)
def test_wrong_or_incomplete_run_identity_fails_closed(overrides):
    with pytest.raises(proof.ProofError):
        proof.verify_upstream_ci("a" * 40, "test-token", api_get_json=_api_payloads(run=_run(**overrides)))


def test_missing_required_job_fails_closed():
    jobs = _jobs()[:-1]
    with pytest.raises(proof.ProofError, match="All required checks pass"):
        proof.verify_upstream_ci("a" * 40, "test-token", api_get_json=_api_payloads(jobs=jobs))


@pytest.mark.parametrize("status,conclusion", [("queued", None), ("completed", "skipped"), ("completed", "failure")])
def test_non_successful_required_job_fails_closed(status, conclusion):
    jobs = _jobs(**{"Python tests / Run tests (1/2)": {"status": status, "conclusion": conclusion}})
    with pytest.raises(proof.ProofError, match=r"Run tests \(1/2\)"):
        proof.verify_upstream_ci("a" * 40, "test-token", api_get_json=_api_payloads(jobs=jobs))


def test_anonymous_public_upstream_proof_needs_no_token():
    result = proof.verify_upstream_ci("a" * 40, "", api_get_json=_api_payloads(expected_token=""))
    assert result.run_id == 123456


def test_run_pagination_finds_anchor_after_more_than_one_hundred_results():
    run_pages = []
    job_pages = []
    irrelevant = [
        _run(path=".github/workflows/other.yml", id=i + 10,
             html_url=f"https://github.com/NousResearch/hermes-agent/actions/runs/{i + 10}")
        for i in range(100)
    ]
    pages = {1: irrelevant, 2: [_run()]}

    def fetch(url, token):
        assert token == "test-token"
        query = parse_qs(urlsplit(url).query)
        page = int(query["page"][0])
        if urlsplit(url).path.endswith("/actions/runs/123456/jobs"):
            job_pages.append(page)
            return {"total_count": 4, "jobs": _jobs()}
        run_pages.append(page)
        return {"total_count": 101, "workflow_runs": pages[page]}

    result = proof.verify_upstream_ci("a" * 40, "test-token", api_get_json=fetch)
    assert result.run_id == 123456
    assert run_pages == [1, 2]
    assert job_pages == [1]


def test_pagination_cap_fails_closed_before_unbounded_requests():
    calls = []

    def fetch(url, _token):
        calls.append(url)
        return {"total_count": proof.MAX_API_PAGES * proof.API_PAGE_SIZE + 1, "workflow_runs": []}

    with pytest.raises(proof.ProofError, match="pagination cap"):
        proof.verify_upstream_ci("a" * 40, "test-token", api_get_json=fetch)
    assert len(calls) == 1
