#!/usr/bin/env python3
"""Scan a Git range for high-signal supply-chain attack indicators."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

_DIFF_EXCLUDES = (":!uv.lock", ":!*.lock", ":!package-lock.json", ":!yarn.lock")
_B64_EXEC_RE = re.compile(
    r"base64\.(?:b64decode|decodebytes|urlsafe_b64decode)", re.IGNORECASE
)
_EXEC_RE = re.compile(r"(?:exec|eval)\s*\(", re.IGNORECASE)
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
    """Return added source lines, keeping ``++`` source prefixes intact."""
    added: list[str] = []
    in_hunk = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            in_hunk = False
            continue
        if line.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk or line == "---" or line == "+++":
            continue
        if line.startswith("+"):
            added.append(line[1:])
    return added


def _section(title: str, explanation: str, label: str, matches: str) -> str:
    return (
        f"\n### 🚨 CRITICAL: {title}\n{explanation}\n\n"
        f"**{label}:**\n```\n{matches}\n```\n"
    )


def scan_diff(repo: Path, base: str, head: str) -> str:
    """Return a markdown report for critical indicators in ``base...head``."""
    diff = _git(repo, "diff", f"{base}...{head}", "--", *_DIFF_EXCLUDES)
    names = _git(
        repo,
        "diff",
        "--diff-filter=d",
        "--name-only",
        f"{base}...{head}",
        "--",
        *_DIFF_EXCLUDES,
    )
    added = _added_lines(diff)
    findings = ""

    pth_files = "\n".join(line for line in names.splitlines() if line.endswith(".pth"))
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
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="return a non-zero status when a critical indicator is found",
    )
    args = parser.parse_args()
    findings = scan_diff(args.repo.resolve(), args.base, args.head)
    args.findings_file.parent.mkdir(parents=True, exist_ok=True)
    args.findings_file.write_text(findings, encoding="utf-8")
    print(f"found={'true' if findings else 'false'}")
    return 1 if findings and args.fail_on_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
