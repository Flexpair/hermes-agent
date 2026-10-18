"""Validate skill data and execute its direct-fork command recipe offline."""

import re
import subprocess
from pathlib import Path

import os
import hermes_yaml as yaml


REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "optional-skills/devops/flexpair-hermes-distribution"


def test_skill_frontmatter_and_sections():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    frontmatter, body = text[4:].split("\n---\n", 1)
    fields = yaml.safe_load(frontmatter)
    assert fields["name"] == SKILL.name
    assert len(fields["description"]) <= 60
    assert fields["description"].endswith(".")
    assert fields["author"].startswith("Jens Fielenbach")
    assert fields["platforms"] == ["linux", "macos"]
    headings = re.findall(r"^## (.+)$", body, re.MULTILINE)
    assert headings == [
        "When to Use", "Prerequisites", "How to Run", "Quick Reference",
        "Procedure", "Pitfalls", "Verification",
    ]


def test_linked_references_are_present_and_contained():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    references = re.findall(r"\]\((references/[^)]+)\)", text)
    assert references
    for reference in references:
        target = (SKILL / reference).resolve()
        assert target.is_relative_to(SKILL.resolve())
        assert target.is_file()
        assert target.read_text(encoding="utf-8").strip()


def test_command_examples_have_valid_bash_syntax():
    text = (SKILL / "references/commands.md").read_text(encoding="utf-8")
    examples = re.findall(r"```bash\n(.*?)\n```", text, re.DOTALL)
    assert examples
    for example in examples:
        subprocess.run(["bash", "-n", "-c", example], check=True, capture_output=True)


def _git(path, *arguments):
    result = subprocess.run(
        ["git", "-C", str(path), *arguments], check=True,
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def _init(path):
    path.mkdir()
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "Offline Skill Test")
    _git(path, "config", "user.email", "test@example.invalid")


def _commit(path, message):
    _git(path, "add", "--all")
    _git(path, "commit", "-m", message)
    return _git(path, "rev-parse", "HEAD")


def test_direct_fork_recipe_preserves_main_and_installs_selected_head(tmp_path):
    """Execute the documented Git blocks with local repositories; no network."""
    fork = tmp_path / "fork"
    _init(fork)
    installer = fork / "installer-fixture.txt"
    installer.write_text("original\n", encoding="utf-8")
    (fork / "core-fixture.txt").write_text("unchanged\n", encoding="utf-8")
    upstream = _commit(fork, "fixture: upstream")
    installer.write_text("patched\n", encoding="utf-8")
    patch = _git(fork, "diff", "--", installer.name) + "\n"
    installer.write_text("original\n", encoding="utf-8")
    (fork / "flexpair.patch").write_text(patch, encoding="utf-8")
    identities = ("flexpair-color-palette", "provider-card-filter")
    for identity in identities:
        directory = fork / "apps/desktop/src/plugins" / identity
        directory.mkdir(parents=True)
        (directory / "fixture.txt").write_text("direct-v1\n", encoding="utf-8")
    _commit(fork, "fixture: directly maintained plugin assets and unapplied patch")
    for identity in identities:
        (fork / "apps/desktop/src/plugins" / identity / "fixture.txt").write_text(
            "direct-v2\n", encoding="utf-8",
        )
    main = _commit(fork, "fixture: maintain plugins directly on main")
    remote = tmp_path / "remote.git"
    _git(fork, "clone", "--bare", str(fork), str(remote))
    worktree = tmp_path / "deployment"
    branch = "2026-10-18"
    env = dict(os.environ, BASE_MAIN=main, UPSTREAM_SHA=upstream,
               FORK_REMOTE=str(remote), PATCH_BRANCH=branch, WORKTREE=str(worktree))
    text = (SKILL / "references/commands.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```bash\n(.*?)\n```", text, re.DOTALL)
    # Execute inspection, exact-name worktree creation, then deployment-only apply.
    for cwd, block in ((fork, blocks[0]), (fork, blocks[1]), (worktree, blocks[2])):
        subprocess.run(["bash", "-c", block], cwd=cwd, env=env,
                       check=True, capture_output=True, text=True)
    _git(worktree, "commit", "-m", "fixture: deployment-only installer patch")
    assert _git(fork, "rev-parse", "main") == main
    assert _git(fork, "show", "main:installer-fixture.txt") == "original"
    assert installer.read_text(encoding="utf-8") == "original\n"
    assert (worktree / installer.name).read_text(encoding="utf-8") == "patched\n"
    assert _git(worktree, "branch", "--show-current") == branch
    assert not _git(worktree, "diff", upstream, "HEAD", "--", "core-fixture.txt")
    assert not _git(worktree, "status", "--porcelain")
    clone = tmp_path / "selected-head"
    _git(fork, "clone", "--branch", branch, "--single-branch", str(fork), str(clone))
    assert _git(clone, "rev-parse", "HEAD") == _git(worktree, "rev-parse", branch)
    for identity in identities:
        assert (clone / "apps/desktop/src/plugins" / identity / "fixture.txt").read_text(
            encoding="utf-8",
        ) == "direct-v2\n"
    # Application must fail closed when a documented installer patch conflicts.
    conflict = tmp_path / "conflict"
    _git(fork, "worktree", "add", "--detach", str(conflict), main)
    (conflict / installer.name).write_text("incompatible\n", encoding="utf-8")
    result = subprocess.run(["bash", "-c", blocks[2]], cwd=conflict,
                            env=env, check=False, capture_output=True, text=True)
    assert result.returncode != 0
    assert (conflict / installer.name).read_text(encoding="utf-8") == "incompatible\n"
    assert not _git(conflict, "diff", "--cached", "--name-only")
