"""Flexpair branch-HEAD installation against disposable local Git fixtures."""
import os
import re
from pathlib import Path
import shlex
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.platforms("posix")
ROOT = Path(__file__).resolve().parents[3]
# The deployed branch name is whatever the checked-out installer carries.
BRANCH = re.search(r'^BRANCH="([^"]+)"', (ROOT / "scripts/install.sh").read_text(), re.MULTILINE).group(1)


@pytest.fixture(autouse=True)
def patched_installer(tmp_path):
    """Setup keeps the patch unapplied; exercise only a disposable deployment artifact."""
    repo = tmp_path / "installer-artifact"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    # Match Git's canonical LF blobs even when checkout attributes give PowerShell CRLF.
    for name in ("install.sh", "install.ps1"):
        target = scripts / name
        shutil.copy2(ROOT / "scripts" / name, target)
        target.write_bytes(target.read_bytes().replace(b"\r\n", b"\n"))
    git(repo, "init", "-q", "-b", "main")
    # flexpair.patch is a template (@BRANCH@); render it for this branch. On a patched
    # checkout the scripts already carry it, so restore the upstream form first.
    patch = tmp_path / "flexpair.rendered.patch"
    patch.write_text((ROOT / "flexpair.patch").read_text().replace("@BRANCH@", BRANCH))
    patch = str(patch)
    only = ("--include=scripts/install.sh", "--include=scripts/install.ps1")  # the patch also carries core repairs
    if subprocess.run(["git", "-C", str(repo), "apply", *only, "--reverse", "--check", patch], capture_output=True, check=False).returncode == 0:
        git(repo, "apply", *only, "--reverse", patch)
    git(repo, "apply", *only, "--check", patch)
    git(repo, "apply", *only, patch)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *args], check=True, capture_output=True, text=True).stdout.strip()


def origin(tmp_path):
    repo = tmp_path / "origin"
    repo.mkdir()
    git(repo, "init", "-q", "-b", BRANCH)
    (repo / "file").write_text("first")
    git(repo, "add", "file")
    git(repo, "commit", "-qm", "first")
    return repo


def stage(tmp_path, repo, prelude=""):
    env = dict(os.environ, HOME=str(tmp_path), HERMES_HOME=str(tmp_path / "home"), HERMES_INSTALL_DIR=str(tmp_path / "install"), HERMES_REPO_URL=str(repo))
    script = tmp_path / "installer-artifact/scripts/install.sh"
    body = f"source {shlex.quote(str(script))} --manifest\n{prelude}\nstage_repository"
    return subprocess.run(["bash", "-c", body], env=env, capture_output=True, text=True, check=False, timeout=30)


def test_fresh_installs_selected_branch_head(tmp_path):
    repo = origin(tmp_path)
    result = stage(tmp_path, repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert git(tmp_path / "install", "branch", "--show-current") == BRANCH
    assert git(tmp_path / "install", "rev-parse", "HEAD") == git(repo, "rev-parse", "HEAD")


def test_existing_branch_fast_forwards(tmp_path):
    repo = origin(tmp_path)
    assert stage(tmp_path, repo).returncode == 0
    (repo / "file").write_text("second")
    git(repo, "commit", "-qam", "second")
    result = stage(tmp_path, repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert git(tmp_path / "install", "rev-parse", "HEAD") == git(repo, "rev-parse", "HEAD")
    assert git(tmp_path / "install", "branch", "--show-current") == BRANCH


@pytest.mark.parametrize("failure", ["fetch", "checkout", "merge"])
def test_git_failure_stops(tmp_path, failure):
    repo = origin(tmp_path)
    assert stage(tmp_path, repo).returncode == 0
    before = git(tmp_path / "install", "rev-parse", "HEAD")
    prelude = f'git() {{ [ "${{3:-}}" = {failure} ] && return 1; command git "$@"; }}'
    assert stage(tmp_path, repo, prelude).returncode != 0
    assert git(tmp_path / "install", "rev-parse", "HEAD") == before


@pytest.mark.parametrize("kind", ["dirty", "wrong_repo", "ahead", "pin"])
def test_refusal_preserves_checkout(tmp_path, kind):
    repo = origin(tmp_path)
    assert stage(tmp_path, repo).returncode == 0
    install = tmp_path / "install"
    prelude = ""
    if kind == "dirty":
        (install / "file").write_text("local work")
    elif kind == "wrong_repo":
        git(install, "remote", "set-url", "origin", "https://example.invalid/other.git")
    elif kind == "ahead":
        (install / "file").write_text("local work")
        git(install, "commit", "-qam", "local")
    else:
        prelude = "INSTALL_COMMIT=HEAD"
    before = git(install, "rev-parse", "HEAD")
    result = stage(tmp_path, repo, prelude)
    assert result.returncode != 0
    assert git(install, "rev-parse", "HEAD") == before
    assert git(install, "stash", "list") == ""
    if kind in ("dirty", "ahead"):
        assert (install / "file").read_text() == "local work"
