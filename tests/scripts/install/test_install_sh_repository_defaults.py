"""The published installer must clone the Flexpair Hermes fork.

Run the real shell script in manifest mode so these assertions cover the
installer's configuration path without performing a machine-wide install.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"
EXPECTED_URLS = (
    "git@github.com:Flexpair/hermes-agent.git",
    "https://github.com/Flexpair/hermes-agent.git",
)


def test_installer_uses_flexpair_repository_defaults() -> None:
    probe = f"""
set -eu
source "{INSTALL_SH!s}" --manifest >/dev/null
printf '%s\\n' "$REPO_URL_SSH" "$REPO_URL_HTTPS"
"""
    result = subprocess.run(
        ["bash", "-c", probe],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert tuple(result.stdout.splitlines()) == EXPECTED_URLS
