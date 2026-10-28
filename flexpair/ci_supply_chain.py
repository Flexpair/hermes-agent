"""Check added PR lines for the upstream CI's critical supply-chain patterns."""

import os
import re
import subprocess

_DECODE = re.compile(r"base64\.(?:b64decode|decodebytes|urlsafe_b64decode)", re.IGNORECASE)
_EXEC = re.compile(r"(?:exec|eval)\(", re.IGNORECASE)
_SUBPROCESS = re.compile(r"subprocess\.(?:Popen|call|run)\s*\(")
_OBFUSCATED = re.compile(r"base64|\\x[0-9a-f]{2}|chr\(", re.IGNORECASE)
_SHA = re.compile(r"^[0-9a-f]{40}$")


def scan(diff: str) -> list[tuple[int, str]]:
    """Only added content inside hunks is executable source, not diff headers."""
    inside_hunk = False
    findings = []
    for number, line in enumerate(diff.splitlines(), 1):
        if line.startswith("diff --git "):
            inside_hunk = False
        elif line.startswith("@@ "):
            inside_hunk = True
        elif inside_hunk and line.startswith("+"):
            text = line[1:]
            if (_DECODE.search(text) and _EXEC.search(text)) or (
                _SUBPROCESS.search(text) and _OBFUSCATED.search(text)
            ):
                findings.append((number, text))
    return findings


def main() -> int:
    base, head = os.environ["PR_BASE"], os.environ["PR_HEAD"]
    if not _SHA.fullmatch(base) or not _SHA.fullmatch(head):
        raise ValueError("PR base/head must be full commit SHA values")
    result = subprocess.run(
        ["git", "diff", f"{base}...{head}", "--", ".", ":!uv.lock", ":!*.lock",
         ":!package-lock.json", ":!yarn.lock"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90, check=True,
    )
    findings = scan(result.stdout)
    if findings:
        print(f"::error::Found {len(findings)} critical supply-chain pattern(s) in added PR lines")
        for number, _ in findings:
            print(f"diff line {number}")
        return 1
    print("No critical supply-chain patterns found in added PR lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
