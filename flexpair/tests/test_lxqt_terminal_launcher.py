"""Integration tests for Flexpair's isolated LXQt CLI launcher helper."""

import base64
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HELPER_RELATIVE_PATH = Path("flexpair/install-lxqt-terminal-launcher.sh")
DOCKER_IMAGE = "ubuntu:22.04"


class TestLXQTHermesLauncher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("docker") is None:
            raise RuntimeError("Docker is required to exercise the helper as a non-root Linux user")
        image_check = subprocess.run(
            ["docker", "image", "inspect", DOCKER_IMAGE],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if image_check.returncode != 0:
            raise RuntimeError("ubuntu:22.04 must already be available locally; tests do not pull images")
        cls.scratch = tempfile.TemporaryDirectory(
            prefix=".lxqt-launcher-tests-", dir=str(REPOSITORY_ROOT)
        )
        cls.scratch_path = Path(cls.scratch.name)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "scratch"):
            cls.scratch.cleanup()

    def run_in_ubuntu(self, script, checkout=REPOSITORY_ROOT, home="/home/launcher", user="1000:1000", mounts=()):
        uid, gid = user.split(":", 1)
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--platform=linux/amd64",
            "--user",
            user,
            "--mount",
            f"type=bind,source={checkout},target=/workspace,readonly",
            "--tmpfs",
            f"/home:rw,exec,uid={uid},gid={gid},mode=755",
            "--workdir",
            "/workspace",
            "--env",
            f"HOME={home}",
        ]
        for source, target in mounts:
            command.extend(
                ["--mount", f"type=bind,source={source},target={target},readonly"]
            )
        command.extend([DOCKER_IMAGE, "bash", "-c", script])
        return subprocess.run(command, capture_output=True, text=True, timeout=90)

    @staticmethod
    def user_home_setup():
        return r"""
set -euo pipefail
mkdir -p -- "$HOME/.hermes" "$HOME/.local/bin"
ln -s -- /workspace "$HOME/.hermes/hermes-agent"
cp -- /usr/bin/true "$HOME/.local/bin/hermes"
chmod 755 -- "$HOME/.local/bin/hermes"
"""

    def test_linux_install_is_idempotent_copies_repo_icon_and_owns_outputs(self):
        script = self.user_home_setup() + r"""
launcher="$HOME/.hermes/hermes-agent/flexpair/install-lxqt-terminal-launcher.sh"
bash "$launcher"
icon="$HOME/.local/share/icons/hermes-agent.png"
desktop="$HOME/.local/share/applications/hermes.desktop"
icon_inode_first=$(stat -c '%i' -- "$icon")
desktop_inode_first=$(stat -c '%i' -- "$desktop")
bash "$launcher"
printf 'ICON_MATCH=%s\n' "$(cmp -s -- "$icon" /workspace/apps/desktop/assets/icon.png && printf yes || printf no)"
printf 'ICON_STAT=%s\n' "$(stat -c '%u:%g:%a:%s' -- "$icon")"
printf 'DESKTOP_STAT=%s\n' "$(stat -c '%u:%g:%a:%s' -- "$desktop")"
printf 'ICON_INODE_STABLE=%s\n' "$(test "$icon_inode_first" = "$(stat -c '%i' -- "$icon")" && printf yes || printf no)"
printf 'DESKTOP_INODE_STABLE=%s\n' "$(test "$desktop_inode_first" = "$(stat -c '%i' -- "$desktop")" && printf yes || printf no)"
printf 'DESKTOP_B64='
base64 -w 0 -- "$desktop"
printf '\nTEMP_FILES=%s\n' "$(find "$HOME/.local/share" -type f -name '.hermes-agent-*' -print -quit)"
"""
        result = self.run_in_ubuntu(script, home="/home/launcher")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("ICON_MATCH=yes", result.stdout)
        self.assertIn("ICON_STAT=1000:1000:644:", result.stdout)
        self.assertIn("DESKTOP_STAT=1000:1000:644:", result.stdout)
        self.assertIn("ICON_INODE_STABLE=yes", result.stdout)
        self.assertIn("DESKTOP_INODE_STABLE=yes", result.stdout)
        self.assertIn("TEMP_FILES=\n", result.stdout)

        encoded_desktop = next(
            line.removeprefix("DESKTOP_B64=")
            for line in result.stdout.splitlines()
            if line.startswith("DESKTOP_B64=")
        )
        desktop_contents = base64.b64decode(encoded_desktop).decode("utf-8")
        self.assertEqual(
            desktop_contents,
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Hermes Agent\n"
            'Exec=/usr/bin/qterminal -e "/home/launcher/.local/bin/hermes"\n'
            "Icon=/home/launcher/.local/share/icons/hermes-agent.png\n"
            "Terminal=false\n"
            "Categories=Development;\n",
        )

    def test_exec_quotes_home_path_with_spaces(self):
        script = self.user_home_setup() + r"""
rm -- "$HOME/.local/bin/hermes"
ln -s -- /usr/bin/true "$HOME/.local/bin/hermes"
bash "$HOME/.hermes/hermes-agent/flexpair/install-lxqt-terminal-launcher.sh"
desktop="$HOME/.local/share/applications/hermes.desktop"
printf 'DESKTOP_B64='
base64 -w 0 -- "$desktop"
printf '\n'
"""
        result = self.run_in_ubuntu(script, home="/home/alice smith")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        encoded_desktop = next(
            line.removeprefix("DESKTOP_B64=")
            for line in result.stdout.splitlines()
            if line.startswith("DESKTOP_B64=")
        )
        desktop_contents = base64.b64decode(encoded_desktop).decode("utf-8")
        self.assertIn(
            'Exec=/usr/bin/qterminal -e "/home/alice smith/.local/bin/hermes"\n',
            desktop_contents,
        )
        self.assertIn(
            "Icon=/home/alice smith/.local/share/icons/hermes-agent.png\n",
            desktop_contents,
        )

    def test_exec_quotes_reserved_home_characters(self):
        script = self.user_home_setup() + r"""
bash "$HOME/.hermes/hermes-agent/flexpair/install-lxqt-terminal-launcher.sh"
printf 'DESKTOP_B64='
base64 -w 0 -- "$HOME/.local/share/applications/hermes.desktop"
printf '\n'
"""
        home = "/home/joe&tim;name"
        result = self.run_in_ubuntu(script, home=home)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        encoded = next(line.removeprefix("DESKTOP_B64=") for line in result.stdout.splitlines()
                       if line.startswith("DESKTOP_B64="))
        desktop = base64.b64decode(encoded).decode("utf-8")
        self.assertIn(f'Exec=/usr/bin/qterminal -e "{home}/.local/bin/hermes"\n', desktop)

    def test_exec_escapes_reserved_characters_through_desktop_parser(self):
        script = self.user_home_setup() + r"""
bash "$HOME/.hermes/hermes-agent/flexpair/install-lxqt-terminal-launcher.sh"
printf 'DESKTOP_B64='
base64 -w 0 -- "$HOME/.local/share/applications/hermes.desktop"
printf '\n'
"""
        home = '/home/a\\b$c`d"e%f'
        result = self.run_in_ubuntu(script, home=home)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        encoded = next(line.removeprefix("DESKTOP_B64=") for line in result.stdout.splitlines()
                       if line.startswith("DESKTOP_B64="))
        desktop = base64.b64decode(encoded).decode("utf-8")
        self.assertIn('Exec=/usr/bin/qterminal -e "/home/a\\\\\\\\b\\\\$c\\\\`d\\\\"e%%f/.local/bin/hermes"\n', desktop)

    def test_control_characters_in_home_are_rejected_before_writes(self):
        script = self.user_home_setup() + r"""
set +e
output=$(bash "$HOME/.hermes/hermes-agent/flexpair/install-lxqt-terminal-launcher.sh" 2>&1)
status=$?
set -e
printf 'HELPER_STATUS=%s\n' "$status"
printf 'SHARE_CREATED=%s\n' "$(test -e "$HOME/.local/share" && printf yes || printf no)"
printf 'HELPER_OUTPUT=%s\n' "$output"
"""
        for name in ("with\nnewline", "with\ttab", "with\x7fdelete"):
            with self.subTest(name=repr(name)):
                result = self.run_in_ubuntu(script, home=f"/home/{name}")
                self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
                self.assertIn("HELPER_STATUS=1", result.stdout)
                self.assertIn("SHARE_CREATED=no", result.stdout)
                self.assertIn("control character", result.stdout.lower())

    def test_symlink_to_home_with_trailing_newline_is_rejected(self):
        script = r"""
set -euo pipefail
actual=$'/home/actual\n'
mkdir -p "$actual/.local/bin" /home/actual/.local/bin /home/actual/.hermes
cp /usr/bin/true "$actual/.local/bin/hermes"
cp /usr/bin/true /home/actual/.local/bin/hermes
ln -s /workspace /home/actual/.hermes/hermes-agent
ln -s "$actual" "$HOME"
set +e
output=$(bash /workspace/flexpair/install-lxqt-terminal-launcher.sh 2>&1)
status=$?
set -e
printf 'HELPER_STATUS=%s\n' "$status"
printf 'WRONG_HOME_SHARE=%s\n' "$(test -e /home/actual/.local/share && printf yes || printf no)"
printf 'REAL_HOME_SHARE=%s\n' "$(test -e "$actual/.local/share" && printf yes || printf no)"
printf 'HELPER_OUTPUT=%s\n' "$output"
"""
        result = self.run_in_ubuntu(script, home="/home/alias")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("HELPER_STATUS=1", result.stdout)
        self.assertIn("WRONG_HOME_SHARE=no", result.stdout)
        self.assertIn("REAL_HOME_SHARE=no", result.stdout)
        self.assertIn("control character", result.stdout.lower())

    def test_repeat_install_repairs_existing_file_permissions(self):
        script = self.user_home_setup() + r"""
launcher="$HOME/.hermes/hermes-agent/flexpair/install-lxqt-terminal-launcher.sh"
bash "$launcher"
icon="$HOME/.local/share/icons/hermes-agent.png"
desktop="$HOME/.local/share/applications/hermes.desktop"
chmod 0600 "$icon" "$desktop"
bash "$launcher"
printf 'ICON_MODE=%s\n' "$(stat -c '%a' "$icon")"
printf 'DESKTOP_MODE=%s\n' "$(stat -c '%a' "$desktop")"
"""
        result = self.run_in_ubuntu(script)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("ICON_MODE=644", result.stdout)
        self.assertIn("DESKTOP_MODE=644", result.stdout)

    def test_failed_rollback_preserves_both_backup_files(self):
        fake_bin = self.scratch_path / "failed-rollback-bin"
        fake_bin.mkdir()
        fake_mv = fake_bin / "mv"
        fake_mv.write_text(
            "#!/bin/bash\n"
            "case \"$3\" in\n"
            "  */.hermes-agent-desktop.*|*/.hermes-agent-*-backup.*) exit 1 ;;\n"
            "esac\n"
            "exec /bin/mv \"$@\"\n",
            encoding="utf-8",
        )
        fake_mv.chmod(0o755)
        script = self.user_home_setup() + r"""
launcher="$HOME/.hermes/hermes-agent/flexpair/install-lxqt-terminal-launcher.sh"
bash "$launcher"
icon="$HOME/.local/share/icons/hermes-agent.png"
desktop="$HOME/.local/share/applications/hermes.desktop"
printf 'original icon' > "$icon"
printf 'original launcher' > "$desktop"
set +e
output=$(PATH="/fake-bin:$PATH" bash "$launcher" 2>&1)
status=$?
set -e
shopt -s nullglob
icon_backups=("$HOME"/.local/share/icons/.hermes-agent-icon-backup.*)
desktop_backups=("$HOME"/.local/share/applications/.hermes-agent-desktop-backup.*)
printf 'HELPER_STATUS=%s\n' "$status"
printf 'ICON_BACKUPS=%s\n' "${#icon_backups[@]}"
printf 'DESKTOP_BACKUPS=%s\n' "${#desktop_backups[@]}"
[[ ${#icon_backups[@]} == 1 ]] && [[ $(cat "${icon_backups[0]}") == 'original icon' ]]
[[ ${#desktop_backups[@]} == 1 ]] && [[ $(cat "${desktop_backups[0]}") == 'original launcher' ]]
printf 'BACKUPS_CONTAIN_ORIGINALS=yes\n'
"""
        result = self.run_in_ubuntu(script, mounts=((fake_bin, "/fake-bin"),))
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("HELPER_STATUS=1", result.stdout)
        self.assertIn("ICON_BACKUPS=1", result.stdout)
        self.assertIn("DESKTOP_BACKUPS=1", result.stdout)
        self.assertIn("BACKUPS_CONTAIN_ORIGINALS=yes", result.stdout)

    def test_missing_icon_fails_without_publishing(self):
        checkout = self.scratch_path / "missing-icon-checkout"
        (checkout / "flexpair").mkdir(parents=True)
        shutil.copy2(
            REPOSITORY_ROOT / HELPER_RELATIVE_PATH,
            checkout / HELPER_RELATIVE_PATH,
        )
        (checkout / "apps/desktop/assets").mkdir(parents=True)
        script = self.user_home_setup() + r"""
set +e
output=$(bash "$HOME/.hermes/hermes-agent/flexpair/install-lxqt-terminal-launcher.sh" 2>&1)
status=$?
set -e
printf 'HELPER_STATUS=%s\n' "$status"
printf 'HELPER_OUTPUT=%s\n' "$output"
printf 'SHARE_CREATED=%s\n' "$(test -e "$HOME/.local/share" && printf yes || printf no)"
printf 'ICON_CREATED=%s\n' "$(test -e "$HOME/.local/share/icons/hermes-agent.png" && printf yes || printf no)"
printf 'DESKTOP_CREATED=%s\n' "$(test -e "$HOME/.local/share/applications/hermes.desktop" && printf yes || printf no)"
"""
        result = self.run_in_ubuntu(script, checkout=checkout)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("HELPER_STATUS=1", result.stdout)
        self.assertIn("icon", result.stdout.lower())
        self.assertIn("SHARE_CREATED=no", result.stdout)
        self.assertIn("ICON_CREATED=no", result.stdout)
        self.assertIn("DESKTOP_CREATED=no", result.stdout)

    def test_missing_hermes_cli_fails_without_publishing(self):
        script = r"""
set -euo pipefail
mkdir -p -- "$HOME/.hermes" "$HOME/.local/bin"
ln -s -- /workspace "$HOME/.hermes/hermes-agent"
set +e
output=$(bash "$HOME/.hermes/hermes-agent/flexpair/install-lxqt-terminal-launcher.sh" 2>&1)
status=$?
set -e
printf 'HELPER_STATUS=%s\n' "$status"
printf 'HELPER_OUTPUT=%s\n' "$output"
printf 'SHARE_CREATED=%s\n' "$(test -e "$HOME/.local/share" && printf yes || printf no)"
"""
        result = self.run_in_ubuntu(script)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("HELPER_STATUS=1", result.stdout)
        self.assertIn("hermes", result.stdout.lower())
        self.assertIn("SHARE_CREATED=no", result.stdout)

    def test_non_linux_reports_success_without_home_mutation(self):
        fake_bin = self.scratch_path / "fake-uname-bin"
        fake_bin.mkdir()
        fake_uname = fake_bin / "uname"
        fake_uname.write_text("#!/bin/sh\nprintf 'Darwin\\n'\n", encoding="utf-8")
        fake_uname.chmod(0o755)
        script = self.user_home_setup() + r"""
snapshot() {
  find "$HOME" -mindepth 1 -printf '%P %y %i %s %m %u %g %T@\n' | sort
}
before=$(snapshot)
set +e
output=$(PATH="/fake-bin:$PATH" bash "$HOME/.hermes/hermes-agent/flexpair/install-lxqt-terminal-launcher.sh" 2>&1)
status=$?
set -e
after=$(snapshot)
printf 'HELPER_STATUS=%s\n' "$status"
printf 'HOME_UNCHANGED=%s\n' "$(test "$before" = "$after" && printf yes || printf no)"
printf 'HELPER_OUTPUT=%s\n' "$output"
"""
        result = self.run_in_ubuntu(
            script,
            mounts=((fake_bin, "/fake-bin"),),
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("HELPER_STATUS=0", result.stdout)
        self.assertIn("HOME_UNCHANGED=yes", result.stdout)
        self.assertIn("skip", result.stdout.lower())
        self.assertIn("linux", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
