"""Fork scope must fail closed rather than convert failures into successes."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("fork_scope", ROOT / "scripts/ci/fork_scope.py")
assert spec is not None and spec.loader is not None
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)
spec_gate = importlib.util.spec_from_file_location("gate", ROOT / "scripts/ci/required_results.py")
assert spec_gate is not None and spec_gate.loader is not None
gate = importlib.util.module_from_spec(spec_gate)
spec_gate.loader.exec_module(gate)


class ForkScopeTests(unittest.TestCase):
    def setUp(self):
        self.proof_run = dict(head_sha=scope.ANCHOR, path=".github/workflows/ci.yaml", event="push", status="completed", conclusion="success", repository=dict(full_name=scope.REPOSITORY))
        self.jobs = [dict(name=name, status="completed", conclusion="success") for name in scope.PROOF_JOBS]

    def test_successful_proof(self):
        scope.verify_proof(self.proof_run, self.jobs)

    def test_missing_failed_cancelled_or_skipped_consumer(self):
        for result in ("failure", "skipped", "cancelled", None):
            self.jobs[0]["conclusion"] = result
            with self.assertRaises(ValueError):
                scope.verify_proof(self.proof_run, self.jobs)
        with self.assertRaises(ValueError):
            scope.verify_proof(self.proof_run, [])

    def test_wrong_sha_event_repository_or_result(self):
        for key, value in (("head_sha", "0" * 40), ("event", "pull_request"), ("repository", {}), ("conclusion", "failure"), ("path", "other.yml")):
            with self.assertRaises(ValueError):
                scope.verify_proof(dict(self.proof_run, **{key: value}), self.jobs)

    def test_core_dependency_installer_and_unknown_changes_rejected(self):
        allowed = json.loads((ROOT / "scripts/ci/fork_scope_paths.json").read_text())
        for path in ("agent/turn.py", "run_agent.py", "install.sh", "install.ps1", "package-lock.json", "pyproject.toml", "plugin-catalog/new.yaml", "apps/desktop/src/new-core.ts"):
            with self.assertRaises(ValueError):
                scope.admit_paths([path], allowed)

    def test_authorized_palette_and_radio_test_allowed(self):
        allowed = json.loads((ROOT / "scripts/ci/fork_scope_paths.json").read_text())
        scope.admit_paths(["apps/desktop/src/plugins/flexpair-color-palette/plugin.tsx", "apps/desktop/src/contrib/radio-plugin.test.ts", "tests/scripts/install/test_flexpair_distribution.py"], allowed)

    def test_reviewed_deletion_scope_fix_has_focused_coverage(self):
        allowed = json.loads((ROOT / "scripts/ci/fork_scope_paths.json").read_text())
        tests = ["tests/hermes_state/test_session_delete_profile_scope.py", "tests/hermes_state/test_session_delete_hook.py"]
        scope.admit_paths(["hermes_state_common.py", *tests], allowed)
        workflow = (ROOT / ".github/workflows/fork-delta.yml").read_text()
        for path in tests:
            self.assertIn(path, workflow)
        with self.assertRaises(ValueError):
            scope.admit_paths(["hermes_state_worker_operations.py"], allowed)

    def test_reviewed_core_repairs_have_focused_coverage(self):
        allowed = json.loads((ROOT / "scripts/ci/fork_scope_paths.json").read_text())
        tests = ["tests/hermes_state/test_runtime_worker_archive_staleness.py",
                 "tests/hermes_cli/test_worktree_exit_owner_work.py",
                 "tests/gateway/test_tui_session_reads.py"]
        scope.admit_paths(["agent/runtime_session_compression.py",
                           "cli.py",
                           "hermes_state_worker_compression.py",
                           "hermes_cli/cli_tui_runtime_mixin.py",
                           "hermes_cli/main_tui_launch.py",
                           "gateway/session_tui_reads.py", *tests], allowed)
        workflow = (ROOT / ".github/workflows/fork-delta.yml").read_text()
        for path in tests:
            self.assertIn(path, workflow)
        with self.assertRaises(ValueError):
            scope.admit_paths(["agent/micro_compaction.py"], allowed)

    def test_non_pr_and_non_fork_keep_full_routing(self):
        from unittest.mock import patch
        for repository, event in (("NousResearch/hermes-agent", "pull_request"), ("Flexpair/hermes-agent", "push"), ("Flexpair/hermes-agent", "workflow_dispatch")):
            with patch.dict(scope.os.environ, GITHUB_REPOSITORY=repository, GITHUB_EVENT_NAME=event), patch.object(scope, "api") as api:
                scope.main()
                api.assert_not_called()

    def test_non_ancestral_tree_equivalence_and_core_deltas(self):
        import os
        import subprocess
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)

            def git(*args):
                return subprocess.check_output(["git", *args], cwd=repo, stderr=subprocess.PIPE)

            git("init", "-q")
            git("config", "user.email", "test@example.invalid")
            git("config", "user.name", "Test")
            (repo / "core.txt").write_text("proven core\n")
            git("add", ".")
            git("commit", "-qm", "proven upstream")
            anchor = git("rev-parse", "HEAD").decode().strip()
            git("checkout", "--orphan", "fork")
            (repo / "fork.txt").write_text("reviewed delta\n")
            git("add", ".")
            git("commit", "-qm", "squashed fork")
            self.assertEqual(subprocess.run(
                ["git", "merge-base", "--is-ancestor", anchor, "HEAD"], cwd=repo, check=False,
            ).returncode, 1)
            manifest = repo / "scripts/ci/fork_scope_paths.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps(["fork.txt"]))
            output, summary = repo / "output", repo / "summary"
            proof = dict(self.proof_run, head_sha=anchor, html_url="https://example.invalid/proof")

            def api(path):
                return {"jobs": self.jobs} if "/jobs?" in path else proof

            previous = Path.cwd()
            try:
                os.chdir(repo)
                with patch.dict(scope.os.environ, GITHUB_REPOSITORY="Flexpair/hermes-agent",
                                GITHUB_EVENT_NAME="pull_request", GITHUB_OUTPUT=str(output),
                                GITHUB_STEP_SUMMARY=str(summary)), patch.object(scope, "ANCHOR", anchor), patch.object(scope, "api", side_effect=api) as evidence:
                    scope.main()
                    self.assertIn("fork_delta=true", output.read_text())
                    self.assertIn(f"`{anchor}`", summary.read_text())
                    for lane in scope.REUSED_LANES:
                        self.assertIn(f"{lane}=false", output.read_text())
                    output.unlink()
                    summary.unlink()
                    for change in ("modify", "delete", "add", "rename"):
                        with self.subTest(change=change):
                            git("reset", "--hard", "-q", "HEAD")
                            if change == "modify":
                                (repo / "core.txt").write_text("unproven core\n")
                            elif change == "delete":
                                (repo / "core.txt").unlink()
                            elif change == "rename":
                                (repo / "fork.txt").unlink()
                                (repo / "core.txt").rename(repo / "fork.txt")
                            else:
                                (repo / "new-core.txt").write_text("unreviewed\n")
                            git("add", "-u")
                            if change == "add":
                                git("add", "new-core.txt")
                            git("commit", "-qm", change)
                            evidence.reset_mock()
                            with self.assertRaisesRegex(ValueError, "Unreviewed fork/core delta"):
                                scope.main()
                            evidence.assert_not_called()
                            self.assertFalse(output.exists())
                            self.assertFalse(summary.exists())
                            git("reset", "--hard", "-q", "HEAD~1")
            finally:
                os.chdir(previous)

    def test_missing_anchor_or_failed_diff_fails_closed(self):
        from unittest.mock import patch
        import subprocess
        with patch.dict(scope.os.environ, GITHUB_REPOSITORY="Flexpair/hermes-agent", GITHUB_EVENT_NAME="pull_request"), patch.object(scope, "git", side_effect=subprocess.CalledProcessError(128, "git diff")), patch.object(scope, "api") as evidence:
            with self.assertRaises(subprocess.CalledProcessError):
                scope.main()
            evidence.assert_not_called()

    def test_missing_network_proof_fails_closed(self):
        from unittest.mock import patch
        with patch.dict(scope.os.environ, GITHUB_REPOSITORY="Flexpair/hermes-agent", GITHUB_EVENT_NAME="pull_request"), patch.object(scope.subprocess, "run"), patch.object(scope, "git", return_value=b""), patch.object(scope, "api", side_effect=OSError("unavailable")):
            with self.assertRaises(OSError):
                scope.main()

    def test_selected_fork_consumer_must_succeed(self):
        entries = {"detect": {"result": "success", "outputs": {"fork_delta": "true"}}}
        self.assertFalse(gate.evaluate_gate(entries)["ok"])
        for result in ("skipped", "failure", "cancelled"):
            self.assertFalse(gate.evaluate_gate(dict(entries, **{"fork-delta": {"result": result}}))["ok"])
        self.assertTrue(gate.evaluate_gate(dict(entries, **{"fork-delta": {"result": "success"}}))["ok"])


if __name__ == "__main__":
    unittest.main()
