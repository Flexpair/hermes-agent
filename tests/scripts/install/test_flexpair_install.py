"""Fork bootstrap checks; run with scripts/run_tests.sh tests/scripts/install/test_flexpair_install.py."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class FlexpairInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), HERMES_HOME=str(self.home / "home"),
                        TMPDIR=str(self.home), PATH=f"{self.bin}:{os.environ['PATH']}")

    def executable(self, name, text):
        path = self.bin / name
        path.write_text("#!/usr/bin/env bash\nset -eu\n" + text, encoding="utf-8")
        path.chmod(0o755)

    def bootstrap(self, *args):
        return subprocess.run(["bash", str(ROOT / "scripts/flexpair-install.sh"), *args],
                              env=self.env, capture_output=True, text=True, encoding="utf-8")

    def test_latest_dated_branch_and_forwarded_arguments(self):
        self.executable("git", 'printf "abc\\trefs/heads/2026-09-01-patched\\ndef\\trefs/heads/2026-10-16-patched\\nghi\\trefs/heads/not-patched\\n"\n')
        self.executable("curl", 'printf "%s\\n" "$*"\nwhile [ "$1" != -o ]; do shift; done\nprintf \'printf "%%s\\\\n" "$HERMES_REPO_URL" "$*"\\n\' > "$2"\n')
        result = self.bootstrap("--non-interactive", "--dir", str(self.home / "with spaces"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/2026-10-16-patched/scripts/install.sh", result.stdout)
        self.assertIn("https://github.com/Flexpair/hermes-agent.git", result.stdout)
        self.assertIn("--non-interactive --dir", result.stdout)
        self.assertFalse(list(self.home.glob("flexpair-install.*")))

    def test_explicit_branch_does_not_discover(self):
        self.executable("git", "exit 99\n")
        self.executable("curl", 'printf "%s\\n" "$*"\nwhile [ "$1" != -o ]; do shift; done\nprintf \'exit 0\\n\' > "$2"\n')
        result = self.bootstrap("--branch", "test-branch")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/test-branch/scripts/install.sh", result.stdout)

    def test_no_branch_fails_without_download(self):
        self.executable("git", "exit 0\n")
        self.executable("curl", "exit 99\n")
        result = self.bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No dated", result.stderr)

    def test_slash_separated_branch_is_forwarded(self):
        self.executable("git", "exit 99\n")
        self.executable("curl", 'printf "%s\\n" "$*"\nwhile [ "$1" != -o ]; do shift; done\nprintf \'exit 0\\n\' > "$2"\n')
        result = self.bootstrap("--branch", "feat/minimal-flexpair-patch")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/feat/minimal-flexpair-patch/scripts/install.sh", result.stdout)

    def test_discovery_failure_propagates(self):
        self.executable("git", "exit 19\n")
        self.assertEqual(self.bootstrap().returncode, 19)


    def test_download_error_propagates_and_cleans_up(self):
        self.executable("curl", "exit 22\n")
        result = self.bootstrap("--branch", "test-branch")
        self.assertEqual(result.returncode, 22)
        self.assertFalse(list(self.home.glob("flexpair-install.*")))

    def test_invalid_branch_is_rejected(self):
        for branch in ("../main", "feat/../main", "feat//main", "/main", "main?x=1"):
            with self.subTest(branch=branch):
                self.assertEqual(self.bootstrap("--branch", branch).returncode, 2)
        self.assertEqual(self.bootstrap("--branch").returncode, 2)

    def test_product_stage_installs_pinned_plugin_and_propagates_failure(self):
        # Main stays upstream-shaped; exercise the installer produced by the patch.
        scripts = self.home / "scripts"
        scripts.mkdir()
        installer = scripts / "install.sh"
        installer.write_bytes((ROOT / "scripts/install.sh").read_bytes())
        installer.chmod(0o755)
        for relative in ("apps/desktop/src/contrib/runtime-loader.ts",
                         "apps/desktop/src/contrib/runtime-loader.test.ts"):
            target = self.home / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / relative).read_bytes())
        subprocess.run(["git", "apply", str(ROOT / "flexpair.patch")],
                       cwd=self.home, check=True)
        for failure in (0, 19):
            hermes = self.home / ".hermes/bin/hermes"
            hermes.parent.mkdir(parents=True, exist_ok=True)
            hermes.write_text(f'''#!/usr/bin/env bash
printf "%s\\n" "$*"
if [[ "$*" == "plugins install "* ]]; then
    if [[ -f "$0.installed" && " $* " != *" --force "* ]]; then
        exit 23
    fi
    touch "$0.installed"
fi
exit {failure}
''', encoding="utf-8")
            hermes.chmod(0o755)
            body = f'''source "{installer}" --manifest
INSTALL_DIR="{self.home}"
bootstrap_python() {{ boot_py=true; }}
wire_shell_path() {{ :; }}
run_stage products
run_stage products
'''
            result = subprocess.run(["bash", "-c", body], env=self.env, capture_output=True, text=True, encoding="utf-8")
            if failure:
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("palette installation failed", result.stderr)
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--ref bbff250954d28f992668e227cdb59301befe8717 --enable", result.stdout)
                self.assertIn("plugins enable flexpair-color-palette", result.stdout)
                self.assertEqual(result.stdout.count("plugins enable flexpair-color-palette"), 2)


if __name__ == "__main__":
    unittest.main()
