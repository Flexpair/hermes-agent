"""Flexpair repository recovery and branch safety against local Git repositories."""

import os
from pathlib import Path
import shlex
import subprocess

import pytest

pytestmark = pytest.mark.platforms("posix")
INSTALLER = Path(__file__).resolve().parents[3] / "scripts" / "install.sh"
BRANCH = "2026-11-08-patched"


def _env():
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        GIT_ALLOW_PROTOCOL="file",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_COUNT="0",
        GIT_TERMINAL_PROMPT="0",
    )
    return env


def _git(repo: Path, *args: str, stdin: str | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *args],
        env=_env(), input=stdin, capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def _origin(tmp_path: Path) -> Path:
    repo = tmp_path / "origin"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "file").write_text("base")
    _git(repo, "add", "file")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "checkout", "-qb", BRANCH)
    (repo / "file").write_text("deploy")
    _git(repo, "commit", "-qam", "deploy")
    _git(repo, "checkout", "-q", "main")
    return repo


def _stage(tmp_path: Path, origin: Path, prelude: str = "") -> subprocess.CompletedProcess:
    env = _env()
    env.update(
        HOME=str(tmp_path),
        HERMES_HOME=str(tmp_path / "home"),
        HERMES_INSTALL_DIR=str(tmp_path / "install"),
        HERMES_REPO_URL=str(origin),
        HERMES_INSTALL_CHANNEL="",
    )
    command = f"source {shlex.quote(str(INSTALLER))} --manifest --branch {shlex.quote(BRANCH)}\n{prelude}\nstage_repository"
    return subprocess.run(["bash", "-c", command], env=env, capture_output=True, text=True, check=False, timeout=60)


def _partial_checkout(tmp_path: Path, origin: Path, linked: bool, clone_filter: str = "blob:none"):
    install = tmp_path / "install"
    if linked:
        main_checkout = tmp_path / "main-checkout"
        _git(tmp_path, "clone", "-q", str(origin), str(main_checkout))
        _git(main_checkout, "worktree", "add", "-q", "-b", BRANCH, str(install), f"origin/{BRANCH}")
    else:
        _git(tmp_path, "clone", "-q", "--single-branch", "--branch", BRANCH, str(origin), str(install))

    _git(install, "config", "gc.auto", "0")
    _git(install, "config", "maintenance.auto", "false")
    _git(install, "repack", "-adq")
    common_dir = Path(_git(install, "rev-parse", "--git-common-dir"))
    if not common_dir.is_absolute():
        common_dir = install / common_dir
    pack_dir = common_dir / "objects" / "pack"
    [pack] = pack_dir.glob("pack-*.pack")
    unmarked = pack.with_suffix(".promisor")

    # A second real pack has a nonempty marker, which must not be truncated.
    tip = _git(install, "rev-parse", "HEAD")
    pack_hash = _git(install, "pack-objects", "--no-reuse-delta", str(pack_dir / "pack"), stdin=f"{tip}\n")
    existing = pack_dir / f"pack-{pack_hash}.promisor"
    assert existing != unmarked
    existing.write_text(f"{tip} refs/heads/{BRANCH}\n")
    _git(install, "config", "remote.origin.promisor", "true")
    _git(install, "config", "remote.origin.partialclonefilter", clone_filter)
    assert not unmarked.exists()
    return install, common_dir, unmarked, existing


def _guard_fetch(marker: Path, witness: Path) -> str:
    # Simulate Git rejecting an unmarked pack while leaving the real local fetch intact.
    return (
        'git() { local arg; for arg in "$@"; do if [ "$arg" = fetch ]; then '
        f"printf 'fetch\\n' >> {shlex.quote(str(witness))}; "
        f"[ -e {shlex.quote(str(marker))} ] || {{ echo 'unmarked pack before fetch' >&2; return 128; }}; "
        'break; fi; done; command git "$@"; }'
    )


@pytest.mark.parametrize("damage", ["commitless", "lost_head", "dangling_gitdir"])
def test_damaged_checkout_is_backed_up_and_recloned(tmp_path, damage):
    origin = _origin(tmp_path)
    install = tmp_path / "install"
    install.mkdir()
    if damage == "dangling_gitdir":
        (install / ".git").write_text(f"gitdir: {tmp_path / 'missing'}\n")
    else:
        _git(install, "init", "-q")
        if damage == "lost_head":
            (install / ".git" / "HEAD").unlink()
    (install / "keep").write_text("user data")

    result = _stage(tmp_path, origin)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _git(install, "branch", "--show-current") == BRANCH
    assert _git(install, "rev-parse", "HEAD") == _git(origin, "rev-parse", BRANCH)
    assert (install / "file").read_text() == "deploy"
    [backup] = tmp_path.glob("install.broken-*")
    assert (backup / "keep").read_text() == "user data"
    assert (backup / ".git").exists()
    if damage == "dangling_gitdir":
        assert (backup / ".git").read_text() == f"gitdir: {tmp_path / 'missing'}\n"


def test_single_branch_checkout_creates_and_updates_deploy_branch(tmp_path):
    origin = _origin(tmp_path)
    install = tmp_path / "install"
    _git(tmp_path, "clone", "-q", "--single-branch", "--branch", "main", str(origin), str(install))
    assert _git(install, "config", "--get", "remote.origin.fetch") == "+refs/heads/main:refs/remotes/origin/main"
    assert not _git(install, "branch", "--list", BRANCH)
    main_tip = _git(install, "rev-parse", "main")

    result = _stage(tmp_path, origin)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _git(install, "branch", "--show-current") == BRANCH
    assert _git(install, "rev-parse", "HEAD") == _git(origin, "rev-parse", BRANCH)
    assert _git(install, "rev-parse", "main") == main_tip

    _git(origin, "checkout", "-q", BRANCH)
    (origin / "file").write_text("new deploy")
    _git(origin, "commit", "-qam", "new deploy")
    result = _stage(tmp_path, origin)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _git(install, "rev-parse", "HEAD") == _git(origin, "rev-parse", BRANCH)


@pytest.mark.parametrize("linked", [False, True], ids=["checkout", "linked-worktree"])
@pytest.mark.parametrize("clone_filter", ["blob:none", "tree:0"])
def test_partial_clone_is_repaired_before_fetch(tmp_path, linked, clone_filter):
    origin = _origin(tmp_path)
    _git(origin, "config", "uploadpack.allowFilter", "true")
    install, _, unmarked, existing = _partial_checkout(tmp_path, origin, linked, clone_filter)
    original_marker = existing.read_bytes()
    _git(origin, "checkout", "-q", BRANCH)
    (origin / "file").write_text("new deploy")
    _git(origin, "commit", "-qam", "new deploy")
    witness = tmp_path / "fetches"

    result = _stage(tmp_path, origin, prelude=_guard_fetch(unmarked, witness))

    assert result.returncode == 0, result.stdout + result.stderr
    assert witness.read_text().splitlines()
    assert unmarked.exists()
    assert existing.read_bytes() == original_marker
    assert _git(install, "config", "--get", "remote.origin.partialclonefilter") == "blob:none"
    for setting in ("maintenance.commit-graph.enabled", "gc.writeCommitGraph", "fetch.writeCommitGraph"):
        assert _git(install, "config", "--bool", "--get", setting) == "false"
    assert _git(install, "rev-parse", "HEAD") == _git(origin, "rev-parse", BRANCH)
    assert (install / "file").read_text() == "new deploy"


@pytest.mark.parametrize("state", ["ahead", "diverged"])
def test_existing_local_branch_is_not_reset(tmp_path, state):
    origin = _origin(tmp_path)
    install = tmp_path / "install"
    _git(tmp_path, "clone", "-q", "--single-branch", "--branch", BRANCH, str(origin), str(install))
    (install / "file").write_text("local commit")
    _git(install, "commit", "-qam", "local")
    local_tip = _git(install, "rev-parse", BRANCH)
    _git(install, "checkout", "-qb", "other")
    if state == "diverged":
        _git(origin, "checkout", "-q", BRANCH)
        (origin / "file").write_text("remote commit")
        _git(origin, "commit", "-qam", "remote")

    result = _stage(tmp_path, origin)

    assert result.returncode != 0
    assert _git(install, "rev-parse", BRANCH) == local_tip
    assert (install / "file").read_text() == "local commit"
    assert not _git(install, "stash", "list")


@pytest.mark.parametrize("linked", [False, True], ids=["checkout", "linked-worktree"])
@pytest.mark.parametrize("state", ["dirty", "wrong_origin"])
def test_refusal_preserves_existing_checkout(tmp_path, state, linked):
    origin = _origin(tmp_path)
    install, common_dir, unmarked, existing = _partial_checkout(tmp_path, origin, linked)
    tip = _git(install, "rev-parse", "HEAD")
    if state == "dirty":
        (install / "file").write_text("local edit")
    else:
        _git(install, "remote", "set-url", "origin", str(tmp_path / "different-origin"))
    status = _git(install, "status", "--porcelain")
    config = (common_dir / "config").read_bytes()
    original_marker = existing.read_bytes()
    witness = tmp_path / "fetches"

    result = _stage(tmp_path, origin, prelude=_guard_fetch(unmarked, witness))

    assert result.returncode != 0
    assert ("local changes" if state == "dirty" else "different repository") in result.stderr
    assert not witness.exists()
    assert not unmarked.exists()
    assert existing.read_bytes() == original_marker
    assert (common_dir / "config").read_bytes() == config
    assert _git(install, "rev-parse", "HEAD") == tip
    assert _git(install, "status", "--porcelain") == status
    assert not _git(install, "stash", "list")
    assert (install / "file").read_text() == ("local edit" if state == "dirty" else "deploy")


@pytest.mark.parametrize("operation", ["checkout_existing", "checkout_new", "merge"])
def test_ignored_collision_is_not_overwritten(tmp_path, operation):
    origin = _origin(tmp_path)
    install = tmp_path / "install"
    branch = BRANCH if operation == "merge" else "main"
    _git(tmp_path, "clone", "-q", "--single-branch", "--branch", branch, str(origin), str(install))
    _git(origin, "checkout", "-q", BRANCH)
    (origin / "collision").write_text("remote data")
    _git(origin, "add", "collision")
    _git(origin, "commit", "-qm", "add collision")
    if operation == "checkout_existing":
        _git(install, "fetch", "-q", "origin", f"refs/heads/{BRANCH}:refs/heads/{BRANCH}")
    (install / ".git" / "info" / "exclude").write_text("collision\n")
    (install / "collision").write_text("local data")
    tip = _git(install, "rev-parse", "HEAD")
    assert not _git(install, "status", "--porcelain")

    result = _stage(tmp_path, origin)

    assert result.returncode != 0
    assert (install / "collision").read_text() == "local data"
    assert _git(install, "rev-parse", "HEAD") == tip
    assert _git(install, "branch", "--show-current") == branch
    assert not _git(install, "stash", "list")


def test_detached_unreferenced_commit_is_not_abandoned(tmp_path):
    origin = _origin(tmp_path)
    install = tmp_path / "install"
    _git(tmp_path, "clone", "-q", "--single-branch", "--branch", BRANCH, str(origin), str(install))
    branch_tip = _git(install, "rev-parse", BRANCH)
    _git(install, "checkout", "-q", "--detach")
    (install / "file").write_text("detached work")
    _git(install, "commit", "-qam", "detached work")
    detached_tip = _git(install, "rev-parse", "HEAD")
    assert not _git(install, "for-each-ref", "--contains", "HEAD")

    result = _stage(tmp_path, origin)

    assert result.returncode != 0
    assert _git(install, "rev-parse", "HEAD") == detached_tip
    assert not _git(install, "branch", "--show-current")
    assert _git(install, "rev-parse", BRANCH) == branch_tip
    assert (install / "file").read_text() == "detached work"
    assert not _git(install, "stash", "list")


def test_detached_commit_reachable_only_from_stash_is_not_abandoned(tmp_path):
    origin = _origin(tmp_path)
    install = tmp_path / "install"
    _git(tmp_path, "clone", "-q", "--single-branch", "--branch", BRANCH, str(origin), str(install))
    branch_tip = _git(install, "rev-parse", BRANCH)
    _git(install, "checkout", "-q", "--detach")
    (install / "file").write_text("detached work")
    _git(install, "commit", "-qam", "detached work")
    detached_tip = _git(install, "rev-parse", "HEAD")
    (install / "file").write_text("stashed work")
    _git(install, "stash", "push", "-qm", "saved from detached HEAD")
    stash_tip = _git(install, "rev-parse", "refs/stash")
    assert _git(install, "for-each-ref", "--format=%(refname)", "--contains", "HEAD") == "refs/stash"
    assert not _git(install, "status", "--porcelain")

    result = _stage(tmp_path, origin)

    assert result.returncode != 0
    assert "save detached HEAD on a branch or tag before updating" in result.stderr
    assert _git(install, "rev-parse", "HEAD") == detached_tip
    assert not _git(install, "branch", "--show-current")
    assert _git(install, "rev-parse", BRANCH) == branch_tip
    assert (install / "file").read_text() == "detached work"
    assert not _git(install, "status", "--porcelain")
    assert _git(install, "rev-parse", "refs/stash") == stash_tip
    assert _git(install, "show", "refs/stash:file") == "stashed work"


@pytest.mark.parametrize("reference", ["ancestor", "saved_branch"])
def test_referenced_detached_commit_can_switch(tmp_path, reference):
    origin = _origin(tmp_path)
    install = tmp_path / "install"
    _git(tmp_path, "clone", "-q", "--single-branch", "--branch", BRANCH, str(origin), str(install))
    _git(install, "checkout", "-q", "--detach", "HEAD^" if reference == "ancestor" else "HEAD")
    if reference == "saved_branch":
        (install / "file").write_text("saved work")
        _git(install, "commit", "-qam", "saved work")
        _git(install, "branch", "saved-work")
    detached_tip = _git(install, "rev-parse", "HEAD")

    result = _stage(tmp_path, origin)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _git(install, "branch", "--show-current") == BRANCH
    assert _git(install, "rev-parse", "HEAD") == _git(origin, "rev-parse", BRANCH)
    if reference == "saved_branch":
        assert _git(install, "rev-parse", "saved-work") == detached_tip
