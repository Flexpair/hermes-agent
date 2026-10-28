#!/usr/bin/env python3
"""Fail-closed proof that fork additions preserve upstream CI at their anchor.

Run from a checkout whose HEAD is the Flexpair PR head and whose
refs/remotes/upstream/main history is fetched:

    python3 flexpair/ci_proof.py

The allow-list below is intentionally explicit. Add a new fork-owned path here
only when the additive change is reviewed; modifications, renames, deletions,
and unlisted paths are rejected.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

UPSTREAM_REPO = "NousResearch/hermes-agent"
UPSTREAM_BRANCH = "main"
UPSTREAM_REF = "refs/remotes/upstream/main"
UPSTREAM_WORKFLOW_FILE = "ci.yaml"
UPSTREAM_WORKFLOW_PATH = ".github/workflows/ci.yaml"
UPSTREAM_WORKFLOW_NAME = "CI"

# Existing fork-owned additions at the upstream anchor (23 paths).
_ORIGINAL_FORK_ADDITIONS = (
    "FLEXPAIR-DISTRIBUTION.md",
    "apps/desktop/e2e/flexpair-palette-startup.spec.ts",
    "apps/desktop/src/contrib/flexpair-bundled-lifecycle.test.ts",
    "apps/desktop/src/contrib/flexpair-color-palette-startup.test.tsx",
    "apps/desktop/src/contrib/flexpair-color-palette.test.ts",
    "apps/desktop/src/contrib/provider-card-filter.test.ts",
    "apps/desktop/src/plugins/flexpair-color-palette/LICENSE",
    "apps/desktop/src/plugins/flexpair-color-palette/README.md",
    "apps/desktop/src/plugins/flexpair-color-palette/plugin.tsx",
    "apps/desktop/src/plugins/provider-card-filter/LICENSE",
    "apps/desktop/src/plugins/provider-card-filter/README.md",
    "apps/desktop/src/plugins/provider-card-filter/plugin.tsx",
    "contributors/emails/defurniture.noreply@gmail.com",
    "contributors/emails/mail@flexpair.com",
    "flexpair.patch",
    "flexpair/new-branch.sh",
    "flexpair/update-patch.sh",
    "optional-skills/devops/flexpair-hermes-distribution/SKILL.md",
    "optional-skills/devops/flexpair-hermes-distribution/references/commands.md",
    "optional-skills/devops/flexpair-hermes-distribution/references/subtree-setup.md",
    "tests/scripts/install/test_flexpair_distribution.py",
    "tests/skills/test_flexpair_hermes_distribution_skill.py",
    "website/docs/user-guide/skills/optional/devops/devops-flexpair-hermes-distribution.md",
)

# Three reviewed paths for this CI proof: helper, tests, and the additive
# consumer workflow. Keep this manifest exact; it is not a glob/prefix policy.
EXPECTED_FORK_ADDITIONS = _ORIGINAL_FORK_ADDITIONS + (
    ".github/workflows/flexpair-ci.yml",
    "flexpair/ci_proof.py",
    "flexpair/ci_supply_chain.py",
    "tests/ci/test_flexpair_ci_proof.py",
    "tests/ci/test_flexpair_ci_supply_chain.py",
)

REQUIRED_JOB_NAMES = (
    "JS & TS checks / JS & TS checks",
    "Python tests / Run tests (1/2)",
    "Python tests / Run tests (2/2)",
    "All required checks pass (v2)",
)

API_BASE = "https://api.github.com"
API_PAGE_SIZE = 100
MAX_API_PAGES = 10
API_TIMEOUT_SECONDS = 10
MAX_API_RESPONSE_BYTES = 2 * 1024 * 1024
GIT_TIMEOUT_SECONDS = 15


class ProofError(Exception):
    """An upstream proof could not be established safely."""


@dataclass(frozen=True)
class UpstreamProof:
    anchor: str
    run_id: int
    run_url: str
    verified_jobs: tuple[str, ...]


ApiGetJson = Callable[[str, str], object]


def _validate_repo_path(path: str) -> None:
    """Reject non-repository paths before any policy or diagnostic uses them."""
    if (
        not path
        or "\x00" in path
        or "\\" in path
        or path.startswith("/")
        or any(part in ("", ".", "..") for part in path.split("/"))
        or PurePosixPath(path).is_absolute()
    ):
        raise ProofError(f"unsafe repository path in upstream diff: {path!r}")


def parse_name_status(diff_output: bytes) -> list[tuple[str, str]]:
    """Parse `git diff --name-status -z` without ambiguous whitespace splitting."""
    if not isinstance(diff_output, bytes):
        raise ProofError("git diff returned an invalid name-status payload")
    if not diff_output:
        return []
    fields = diff_output.split(b"\0")
    if fields[-1] == b"":
        fields.pop()
    if len(fields) % 2:
        raise ProofError("git diff returned a malformed name-status payload")

    changes: list[tuple[str, str]] = []
    for index in range(0, len(fields), 2):
        try:
            status = fields[index].decode("ascii", errors="strict")
            path = fields[index + 1].decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ProofError("git diff returned a non-UTF-8 path or status") from exc
        changes.append((status, path))
    return changes


def verify_additive_diff(changes: Iterable[tuple[str, str]]) -> None:
    """Require exactly the manifest paths, all newly added and safely rooted."""
    allowed = set(EXPECTED_FORK_ADDITIONS)
    if len(allowed) != len(EXPECTED_FORK_ADDITIONS):
        raise ProofError("fork addition manifest contains duplicate paths")

    seen: set[str] = set()
    for change in changes:
        if not isinstance(change, (tuple, list)) or len(change) != 2:
            raise ProofError("git diff returned an invalid name-status record")
        status, path = change
        if not isinstance(status, str) or not isinstance(path, str):
            raise ProofError("git diff returned an invalid name-status record")
        _validate_repo_path(path)
        if status != "A":
            raise ProofError(f"fork patch is not additive: status {status!r} for {path!r}")
        if path not in allowed:
            raise ProofError(f"fork patch adds an unreviewed path: {path!r}")
        if path in seen:
            raise ProofError(f"fork patch lists an added path more than once: {path!r}")
        seen.add(path)

    missing = sorted(allowed - seen)
    if missing:
        raise ProofError(f"fork patch is missing allow-listed addition(s): {', '.join(missing)}")


def _run_git(repo_root: Path, args: Sequence[str]) -> bytes:
    """Run one fixed-argument, read-only Git command in the resolved checkout."""
    if not isinstance(repo_root, Path) or not repo_root.is_absolute():
        raise ProofError("repository root must be an absolute path")
    if not args or any(not isinstance(arg, str) or "\x00" in arg for arg in args):
        raise ProofError("invalid internal git command arguments")
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            env={**os.environ, "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0"},
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProofError("could not run the required Git command") from exc
    if result.returncode != 0:
        raise ProofError(f"required Git command failed (exit {result.returncode})")
    return result.stdout


def _git_text(repo_root: Path, args: Sequence[str]) -> str:
    output = _run_git(repo_root, args)
    try:
        return output.decode("utf-8", errors="strict").rstrip("\r\n")
    except UnicodeDecodeError as exc:
        raise ProofError("Git returned non-UTF-8 metadata") from exc


def _object_id(value: str, description: str) -> str:
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value):
        raise ProofError(f"{description} is missing or not a full commit object ID")
    return value


def _checkout_root(repo_root: Path) -> Path:
    try:
        root = repo_root.resolve(strict=True)
    except OSError as exc:
        raise ProofError("repository root does not exist") from exc
    if not root.is_dir():
        raise ProofError("repository root is not a directory")
    reported = _git_text(root, ["rev-parse", "--show-toplevel"])
    try:
        reported_root = Path(reported).resolve(strict=True)
    except OSError as exc:
        raise ProofError("Git did not identify a valid repository root") from exc
    if reported_root != root:
        raise ProofError("helper must run from the root of its checkout")
    return root


def find_upstream_anchor(repo_root: Path) -> tuple[Path, str, str]:
    """Resolve one unambiguous merge-base of fetched upstream/main and HEAD."""
    root = _checkout_root(repo_root)
    shallow = _git_text(root, ["rev-parse", "--is-shallow-repository"])
    if shallow != "false":
        raise ProofError("full Git history is required; checkout is shallow or unverifiable")

    upstream = _object_id(
        _git_text(root, ["rev-parse", "--verify", f"{UPSTREAM_REF}^{{commit}}"]),
        "upstream/main ref",
    )
    head = _object_id(
        _git_text(root, ["rev-parse", "--verify", "HEAD^{commit}"]),
        "HEAD",
    )
    merge_bases = _git_text(root, ["merge-base", "--all", upstream, head]).splitlines()
    if len(merge_bases) != 1:
        if not merge_bases:
            raise ProofError("upstream/main and HEAD have no merge-base")
        raise ProofError("upstream/main and HEAD have ambiguous merge-bases")
    anchor = _object_id(merge_bases[0], "merge-base")
    try:
        _run_git(root, ["merge-base", "--is-ancestor", anchor, upstream])
        _run_git(root, ["merge-base", "--is-ancestor", anchor, head])
    except ProofError as exc:
        raise ProofError("selected upstream merge-base is not an ancestor of upstream/main and HEAD") from exc
    _run_git(root, ["cat-file", "-e", f"{anchor}^{{commit}}"])
    return root, anchor, head


def verify_checkout(repo_root: Path) -> tuple[str, str]:
    """Require a clean full checkout and exact additions from anchor to HEAD."""
    root, anchor, head = find_upstream_anchor(repo_root)
    dirty = _run_git(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
    if dirty:
        raise ProofError("checkout is dirty; verify the exact committed PR head")

    diff = _run_git(
        root,
        [
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            "--name-status",
            "-z",
            anchor,
            head,
            "--",
        ],
    )
    verify_additive_diff(parse_name_status(diff))
    return anchor, head


def _api_url(path: str, params: dict[str, str], page: int) -> str:
    if not path.startswith("/repos/NousResearch/hermes-agent/"):
        raise ProofError("refusing an unexpected GitHub API path")
    query = {**params, "per_page": str(API_PAGE_SIZE), "page": str(page)}
    return f"{API_BASE}{path}?{urlencode(query)}"


class _NoRedirect(HTTPRedirectHandler):
    """The bearer token is scoped to api.github.com; never follow redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _github_get_json(url: str, token: str) -> object:
    """Fetch a bounded JSON response from the fixed GitHub API host."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "api.github.com" or parsed.username or parsed.password:
        raise ProofError("refusing a GitHub API URL outside api.github.com")
    if token and (token.strip() != token or "\r" in token or "\n" in token):
        raise ProofError("GITHUB_TOKEN is missing or invalid")

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Flexpair-upstream-ci-proof",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        url,
        headers=headers,
        method="GET",
    )
    opener = build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=API_TIMEOUT_SECONDS) as response:
            if response.status != 200 or urlsplit(response.geturl()).netloc != "api.github.com":
                raise ProofError("GitHub API returned an unexpected response")
            raw = response.read(MAX_API_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise ProofError(f"GitHub API request failed (HTTP {exc.code})") from None
    except (URLError, TimeoutError, OSError):
        raise ProofError("GitHub API request failed or timed out") from None
    if len(raw) > MAX_API_RESPONSE_BYTES:
        raise ProofError("GitHub API response exceeded the size limit")
    try:
        return json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProofError("GitHub API returned invalid JSON") from None


def _paginated_items(
    path: str,
    params: dict[str, str],
    collection_key: str,
    token: str,
    api_get_json: ApiGetJson,
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    expected_count: int | None = None
    page_count: int | None = None

    for page in range(1, MAX_API_PAGES + 1):
        url = _api_url(path, params, page)
        payload = api_get_json(url, token)
        if not isinstance(payload, dict):
            raise ProofError("GitHub API response has an invalid shape")
        count = payload.get("total_count")
        page_items = payload.get(collection_key)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ProofError("GitHub API response has an invalid total_count")
        if not isinstance(page_items, list) or any(not isinstance(item, dict) for item in page_items):
            raise ProofError(f"GitHub API response has an invalid {collection_key} list")
        if expected_count is None:
            expected_count = count
            page_count = max(1, (count + API_PAGE_SIZE - 1) // API_PAGE_SIZE)
            if page_count > MAX_API_PAGES:
                raise ProofError("GitHub API pagination cap exceeded")
        elif count != expected_count:
            raise ProofError("GitHub API result count changed during pagination")
        if page_count is None:
            raise ProofError("GitHub API pagination count was not initialized")
        if page > page_count:
            raise ProofError("GitHub API returned more pages than its total_count")
        items.extend(page_items)
        if page == page_count:
            if len(items) != expected_count:
                raise ProofError("GitHub API pagination returned an incomplete result set")
            return items

    raise ProofError("GitHub API pagination cap exceeded")


def _run_matches(run: dict[str, object], anchor: str) -> bool:
    repository = run.get("repository")
    if not isinstance(repository, dict):
        return False
    run_url = f"https://github.com/{UPSTREAM_REPO}/actions/runs/{run.get('id')}"
    return (
        repository.get("full_name") == UPSTREAM_REPO
        and run.get("head_sha") == anchor
        and run.get("head_branch") == UPSTREAM_BRANCH
        and run.get("event") == "push"
        and run.get("path") == UPSTREAM_WORKFLOW_PATH
        and run.get("name") == UPSTREAM_WORKFLOW_NAME
        and run.get("html_url") == run_url
    )


def _verify_required_jobs(jobs: Sequence[dict[str, object]]) -> None:
    by_name: dict[str, list[dict[str, object]]] = {name: [] for name in REQUIRED_JOB_NAMES}
    for job in jobs:
        name = job.get("name")
        if isinstance(name, str) and name in by_name:
            by_name[name].append(job)

    missing = [name for name, matches in by_name.items() if not matches]
    duplicates = [name for name, matches in by_name.items() if len(matches) > 1]
    if missing:
        raise ProofError(f"upstream run is missing required job(s): {', '.join(missing)}")
    if duplicates:
        raise ProofError(f"upstream run has ambiguous required job(s): {', '.join(duplicates)}")

    failed = [
        name
        for name, matches in by_name.items()
        if matches[0].get("status") != "completed" or matches[0].get("conclusion") != "success"
    ]
    if failed:
        raise ProofError(f"upstream required job(s) did not succeed: {', '.join(failed)}")


def verify_upstream_ci(
    anchor: str,
    token: str,
    *,
    api_get_json: ApiGetJson | None = None,
) -> UpstreamProof:
    """Find a successful exact upstream CI push and verify its required jobs."""
    anchor = _object_id(anchor, "upstream anchor")
    if token and (token.strip() != token or "\r" in token or "\n" in token):
        raise ProofError("GITHUB_TOKEN is missing or invalid")
    get_json = _github_get_json if api_get_json is None else api_get_json
    path = f"/repos/{UPSTREAM_REPO}/actions/workflows/{UPSTREAM_WORKFLOW_FILE}/runs"
    runs = _paginated_items(
        path,
        {"event": "push", "branch": UPSTREAM_BRANCH, "head_sha": anchor},
        "workflow_runs",
        token,
        get_json,
    )

    failures: list[str] = []
    for run in runs:
        if not _run_matches(run, anchor):
            continue
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            continue
        run_id = run.get("id")
        if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id <= 0:
            failures.append("matching upstream CI run has an invalid ID")
            continue
        expected_url = f"https://github.com/{UPSTREAM_REPO}/actions/runs/{run_id}"
        if run.get("html_url") != expected_url:
            failures.append("matching upstream CI run has an invalid URL")
            continue

        jobs_path = f"/repos/{UPSTREAM_REPO}/actions/runs/{run_id}/jobs"
        jobs = _paginated_items(jobs_path, {"filter": "latest"}, "jobs", token, get_json)
        try:
            _verify_required_jobs(jobs)
        except ProofError as exc:
            failures.append(str(exc))
            continue
        return UpstreamProof(anchor, run_id, expected_url, REQUIRED_JOB_NAMES)

    detail = f" ({'; '.join(failures)})" if failures else ""
    raise ProofError(f"no successful exact upstream CI push proved anchor {anchor}{detail}")


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        print("usage: python3 flexpair/ci_proof.py", file=sys.stderr)
        return 2

    token = os.environ.get("GITHUB_TOKEN", "")
    try:
        repo_root = Path(__file__).resolve().parents[1]
        anchor, _head = verify_checkout(repo_root)
        proof = verify_upstream_ci(anchor, token)
    except ProofError as exc:
        print(f"CI proof failed closed: {exc}", file=sys.stderr)
        return 1

    print(f"Verified upstream CI anchor: {proof.anchor}")
    print(f"Upstream run: {proof.run_url}")
    print("Required proof jobs succeeded: " + ", ".join(proof.verified_jobs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
