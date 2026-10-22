"""Execute the catalog admission step across trusted-sync and submission boundaries."""

import os

import pytest

from tests.ci.test_plugin_catalog_ci_confinement import (
    _commit, _git, _run, _step, _write,
)


@pytest.mark.parametrize("scenario, accepted", [
    ("sync", True),
    ("new-entry", False),
    ("repin", False),
    ("policy-edit", False),
    ("same-tree-without-ancestry", False),
    ("missing-source", False),
])
def test_upstream_catalog_identity(tmp_path, scenario, accepted):
    repo = tmp_path / "pr"
    _write(repo, {"plugin-catalog/old.yaml": "name: old\nsha: a\n"})
    _git(repo, "init", "-qb", "main")
    base = _commit(repo, "fork base")
    _git(repo, "checkout", "-qb", "upstream")
    _write(repo, {"plugin-catalog/inherited.yaml": "name: inherited\nsha: b\n"})
    trusted = _commit(repo, "reviewed upstream catalog")
    _git(repo, "checkout", "-qb", "pr")
    if scenario == "same-tree-without-ancestry":
        _git(repo, "reset", "--soft", base)
    _write(repo, {"scripts/tool.py": "x = 2\n"})
    if scenario == "new-entry":
        _write(repo, {"plugin-catalog/new.yaml": "name: new\n"})
    elif scenario == "repin":
        _write(repo, {"plugin-catalog/inherited.yaml": "name: inherited\nsha: c\n"})
    elif scenario == "policy-edit":
        _write(repo, {"plugin-catalog/README.md": "changed rules\n"})
    _commit(repo, "fork distribution")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "-m", "PR merge", "pr")
    output = tmp_path / "output"
    output.touch()
    # Substitute only the immutable authority, never the ancestry/tree checks.
    source = "0" * 40 if scenario == "missing-source" else trusted
    script = _step("Find changed catalog").replace(
        "20acba0376944d11ee970d6e734afd54bfd8045c", source)
    result = _run(script, tmp_path, repo, {**os.environ, "GITHUB_OUTPUT": str(output)})
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr
    if accepted:
        # Inherited entries still reach pinned-source validation, not a skip.
        assert "plugin-catalog/inherited.yaml" in output.read_text(encoding="utf-8")
    else:
        assert "catalog entry PRs may only touch" in result.stdout
        assert output.read_text(encoding="utf-8") == ""
