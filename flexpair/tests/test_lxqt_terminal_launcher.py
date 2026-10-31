"""Integration tests for Flexpair's isolated LXQt Desktop launcher helper."""

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

    def test_lxqt_quicklaunch_executes_hermes_desktop(self):
        probe = self.scratch_path / "lxqt_click_probe.py"
        probe.write_text(r'''import os
from pathlib import Path
import subprocess
import time
from gi.repository import Gio

home = Path(os.environ["HOME"])
binary = home / ".local/bin/hermes"
binary.parent.mkdir(parents=True)
binary.write_text("#!/bin/sh\nprintf '%s\\n%s\\n%s\\n%s\\n' \"$HOME\" \"${1-}\" \"${2-}\" \"$(ps -o comm= -p \"$PPID\")\" > \"$HOME/.launcher-result.tmp\"\nmv \"$HOME/.launcher-result.tmp\" \"$HOME/.launcher-result\"\nsleep 3\n", encoding="utf-8")
binary.chmod(0o755)
marker = home / ".launcher-result"
marker.unlink(missing_ok=True)
subprocess.run(["bash", "/workspace/flexpair/install-lxqt-terminal-launcher.sh"], check=True, timeout=30)
desktop = home / ".local/share/applications/hermes.desktop"
subprocess.run(["desktop-file-validate", str(desktop)], check=True, timeout=10)
panel = home / ".config/lxqt/panel.conf"
panel.parent.mkdir(parents=True)
panel.write_text("[General]\n__userfile__=true\npanels=panel1\n\n[panel1]\nalignment=-1\niconSize=48\nlineCount=1\npanelSize=60\nplugins=quicklaunch\nposition=Top\nreserve-space=true\nwidth=100\nwidth-percent=true\n\n[quicklaunch]\nalignment=Left\napps\\1\\desktop=" + str(desktop) + "\napps\\size=1\ntype=quicklaunch\n", encoding="utf-8")
panel_process = subprocess.Popen(["lxqt-panel"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    deadline = time.monotonic() + 15
    window = None
    while time.monotonic() < deadline:
        result = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", "lxqt-panel"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.splitlines():
            window = result.stdout.splitlines()[0]
            break
        if panel_process.poll() is not None:
            raise AssertionError("LXQt panel exited")
        time.sleep(.1)
    assert window, "LXQt panel did not appear"
    time.sleep(.5)
    subprocess.run(["xdotool", "mousemove", "--window", window, "24", "24", "click", "1"], check=True, timeout=5)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not marker.exists():
        time.sleep(.1)
    assert marker.exists(), "quicklaunch did not execute Hermes in " + str(home)
    actual = marker.read_text(encoding="utf-8").splitlines()
    assert actual[:3] == [str(home), "desktop", "--skip-build"] and actual[3] != "qterminal", actual
    print("LXQt click -> Hermes Desktop: PASS", home)
finally:
    panel_process.terminate()
    try:
        panel_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        panel_process.kill()
        panel_process.wait(timeout=5)
marker.unlink()
app = Gio.DesktopAppInfo.new_from_filename(str(desktop))
assert app is not None and app.launch([], None), "Gio did not start the launcher"
deadline = time.monotonic() + 10
while time.monotonic() < deadline and not marker.exists():
    time.sleep(.1)
assert marker.exists(), "Gio did not execute Hermes in " + str(home)
actual = marker.read_text(encoding="utf-8").splitlines()
assert actual[:3] == [str(home), "desktop", "--skip-build"] and actual[3] != "qterminal", actual
print("Gio -> Hermes Desktop: PASS", home)
''', encoding="utf-8")
        probe.chmod(0o644)
        script = r'''
set -euo pipefail
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
  python3 python3-gi qterminal lxqt-panel xvfb xauth xdotool dbus-x11 desktop-file-utils procps >/dev/null
useradd --uid 12345 --create-home --user-group --shell /bin/bash launcher
for home in /home/launcher /home/lxqt%case '/home/alice smith' '/home/joe&tim'; do
  install -d -o launcher -g launcher "$home"
  runuser -u launcher -- env HOME="$home" dbus-run-session -- \
    xvfb-run -a -s '-screen 0 1024x768x24' python3 /fixture.py
done
'''
        command = ["docker", "run", "--rm", "--platform=linux/amd64",
                   "--mount", f"type=bind,source={REPOSITORY_ROOT},target=/workspace,readonly",
                   "--mount", f"type=bind,source={probe},target=/fixture.py,readonly",
                   DOCKER_IMAGE, "bash", "-c", script]
        result = subprocess.run(command, capture_output=True, text=True, timeout=300)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        for home in ("/home/launcher", "/home/lxqt%case", "/home/alice smith", "/home/joe&tim"):
            self.assertIn(f"LXQt click -> Hermes Desktop: PASS {home}", result.stdout)
            self.assertIn(f"Gio -> Hermes Desktop: PASS {home}", result.stdout)

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
            'Exec=/bin/sh -c "cd||exit;exec\\\\$IFS./.local/bin/hermes\\\\${IFS}desktop\\\\${IFS}--skip-build"\n'
            "Icon=/home/launcher/.local/share/icons/hermes-agent.png\n"
            "Terminal=false\n"
            "Categories=Development;\n",
        )

    def test_icon_path_preserves_spaces(self):
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
            "Icon=/home/alice smith/.local/share/icons/hermes-agent.png\n",
            desktop_contents,
        )


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
