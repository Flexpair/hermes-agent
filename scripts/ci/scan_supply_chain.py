#!/usr/bin/env python3
"""Scan a git range for high-signal supply-chain attack indicators.

The workflow keeps the final failure decision in GitHub Actions, but the
scanner itself lives here so its behavior can be exercised in an ordinary
subprocess test rather than inferred from workflow source text.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


_DIFF_EXCLUDES = (":!uv.lock", ":!*.lock", ":!package-lock.json", ":!yarn.lock")
_B64_EXEC_RE = re.compile(
    r"base64\.(?:b64decode|decodebytes|urlsafe_b64decode)", re.IGNORECASE
)
_EXEC_RE = re.compile(r"exec\(|eval\(", re.IGNORECASE)
_SUBPROCESS_RE = re.compile(r"subprocess\.(?:Popen|call|run)\s*\(", re.IGNORECASE)
_OBFUSCATED_ARG_RE = re.compile(r"base64|\\x[0-9a-f]{2}|chr\(", re.IGNORECASE)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _added_lines(diff: str) -> list[str]:
    return [
        line
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


def _section(title: str, explanation: str, label: str, matches: str) -> str:
    return (
        f"\n### 🚨 CRITICAL: {title}\n"
        f"{explanation}\n\n"
        f"**{label}:**\n"
        f"```\n{matches}\n```\n"
    )


def scan_diff(repo: Path, base: str, head: str) -> str:
    """Return a markdown report for critical indicators in ``base...head``."""
    diff_args = ["diff", f"{base}...{head}", "--", *_DIFF_EXCLUDES]
    diff = _git(repo, *diff_args)
    names = _git(repo, "diff", "--diff-filter=d", "--name-only", f"{base}...{head}")
    added = _added_lines(diff)
    findings = ""

    pth_files = "\n".join(
        line for line in names.splitlines() if line.endswith(".pth")
    )
    if pth_files:
        findings += _section(
            ".pth file added or modified",
            "Python `.pth` files in `site-packages/` execute automatically when the interpreter starts — no import required.",
            "Files",
            pth_files,
        )

    b64_exec_hits = "\n".join(
        f"{index}:{line}"
        for index, line in enumerate(added, start=1)
        if _B64_EXEC_RE.search(line) and _EXEC_RE.search(line)
    )
    if b64_exec_hits:
        findings += _section(
            "base64 decode + exec/eval combo",
            "Base64-decoded strings passed directly to exec/eval — the signature of hidden credential-stealing payloads.",
            "Matches",
            b64_exec_hits,
        )

    subprocess_hits = "\n".join(
        f"{index}:{line}"
        for index, line in enumerate(added, start=1)
        if _SUBPROCESS_RE.search(line) and _OBFUSCATED_ARG_RE.search(line)
    )
    if subprocess_hits:
        findings += _section(
            "subprocess with encoded/obfuscated command",
            "Subprocess calls whose command strings are base64- or hex-encoded are a strong indicator of payload execution.",
            "Matches",
            subprocess_hits,
        )

    setup_hits = "\n".join(
        line
        for line in names.splitlines()
        if re.fullmatch(
            r"(?:setup\.py|setup\.cfg|sitecustomize\.py|usercustomize\.py|__init__\.pth)",
            line,
        )
    )
    if setup_hits:
        findings += _section(
            "Install-hook file added or modified",
            "These files can execute code during package installation or interpreter startup.",
            "Files",
            setup_hits,
        )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--findings-file", type=Path, required=True)
    args = parser.parse_args()

    findings = scan_diff(args.repo.resolve(), args.base, args.head)
    args.findings_file.parent.mkdir(parents=True, exist_ok=True)
    args.findings_file.write_text(findings, encoding="utf-8")
    print(f"found={'true' if findings else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
