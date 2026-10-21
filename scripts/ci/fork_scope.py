#!/usr/bin/env python3
"""Fail-closed admission of the reviewed Flexpair delta; never waive failed tests."""
import json
import os
import subprocess
import urllib.request
from pathlib import Path

ANCHOR = "20acba0376944d11ee970d6e734afd54bfd8045c"
RUN = 39177780870
REPOSITORY = "NousResearch/hermes-agent"
# Only these successfully executed upstream consumers are reused. E2E and
# advisory/skipped upstream jobs are NOT represented as successful tests.
PROOF_JOBS = {
    "JS & TS checks / JS & TS checks",
    "Python tests / Run tests (1/2)", "Python tests / Run tests (2/2)",
    "OS-specific tests / macOS-only tests (1/2)",
    "OS-specific tests / macOS-only tests (2/2)",
    "OS-specific tests / Windows-only tests",
    "OS-specific tests / Windows-only tests (arm64, 1/2)",
    "OS-specific tests / Windows-only tests (arm64, 2/2)",
    "Rust tests / cargo test (bootstrap installer)",
    "Bootstrap installer / install.sh protocol + small fresh-install E2E",
    "Bootstrap installer / install.ps1 protocol surface",
    "Remote terminal backends / SSH + Docker backends (real sshd, real daemon)",
}
REUSED_LANES = ("python", "python_prod", "desktop_updater", "bootstrap", "rust", "remote_backends", "frontend")


def git(*args):
    return subprocess.check_output(["git", *args], timeout=30)


def admit_paths(paths, allowed):
    unexpected = sorted(set(paths) - set(allowed))
    if unexpected:
        raise ValueError("Unreviewed fork/core delta: " + repr(unexpected))


def verify_proof(run, jobs):
    if (run.get("head_sha") != ANCHOR or run.get("path") != ".github/workflows/ci.yaml"
            or run.get("event") != "push" or run.get("status") != "completed"
            or run.get("conclusion") != "success"
            or run.get("repository", {}).get("full_name") != REPOSITORY):
        raise ValueError("Missing or mismatched successful upstream run")
    successes = {job["name"] for job in jobs if job.get("conclusion") == "success" and job.get("status") == "completed"}
    if not PROOF_JOBS <= successes:
        raise ValueError("Upstream consumer evidence missing/failed: " + repr(sorted(PROOF_JOBS - successes)))


def api(path):
    request = urllib.request.Request("https://api.github.com/repos/" + REPOSITORY + path,
        headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"], "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    # Push, release and dispatch retain the upstream full-suite policy.
    if os.environ.get("GITHUB_REPOSITORY") != "Flexpair/hermes-agent" or os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return
    subprocess.run(["git", "merge-base", "--is-ancestor", ANCHOR, "HEAD"], check=True, timeout=30)
    allowed = json.loads(Path("scripts/ci/fork_scope_paths.json").read_text(encoding="utf-8-sig"))
    paths = git("diff", "--name-only", "-z", ANCHOR, "HEAD").decode().split("\0")
    admit_paths(filter(None, paths), allowed)
    run = api(f"/actions/runs/{RUN}")
    jobs = []
    page = 1
    while True:
        batch = api(f"/actions/runs/{RUN}/jobs?per_page=100&page={page}")["jobs"]
        jobs.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    verify_proof(run, jobs)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.writelines(f"{lane}=false\n" for lane in REUSED_LANES)
        output.write("fork_delta=true\n")
    report = (f"## Upstream proof reused\n{run['html_url']} (`{ANCHOR}`)\n"
              + "\n".join(f"- {job}" for job in sorted(PROOF_JOBS))
              + "\n\n## Executed on fork\nFocused installer patch, skill, catalog synchronization, deletion-hook profile scope, worker CAS receipt recovery, owner-safe worktree cleanup, MCP cost cache invalidation, bundled plugins and Radio integration; Desktop typecheck/build/lint; documentation freshness/build; catalogue supply-chain, attribution and review gates remain active.\n\n"
              "No skipped/failed upstream E2E or advisory checks are claimed as passing.\n")
    print(report)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
        summary.write(report)


if __name__ == "__main__":
    main()
