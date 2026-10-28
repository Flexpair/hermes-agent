"""Behavioral tests for the fork's critical added-line scanner."""

from flexpair.ci_supply_chain import scan

# Compose payloads at runtime so the real PR-diff scan can inspect its own tests.
decode = 'base64.' + 'b64decode'
execute = 'exec' + '('
subprocess_call = 'subprocess.' + 'run('


def test_scan_accepts_headers_deleted_code_and_safe_added_lines():
    diff = "\n".join([
        "diff --git a/example.py b/example.py",
        "--- a/example.py",
        "+++ b/example.py",
        "@@ -1 +1 @@",
        f"-{execute}{decode}(payload))",
        "+print('ordinary content')",
    ])
    assert scan(diff) == []


def test_scan_finds_decoding_execution_and_obfuscated_subprocess():
    diff = "\n".join([
        "diff --git a/example.py b/example.py",
        "--- a/example.py",
        "+++ b/example.py",
        "@@ -1 +1,2 @@",
        f"+{execute}{decode}(payload))",
        f"+{subprocess_call}{decode}(data))",
    ])
    assert [number for number, _ in scan(diff)] == [5, 6]


def test_scan_detects_added_source_lines_starting_with_two_pluses():
    diff = "\n".join([
        "diff --git a/example.py b/example.py",
        "--- a/example.py",
        "+++ b/example.py",
        "@@ -1 +1 @@",
        f"+++{execute}{decode}(payload))",
    ])
    assert [number for number, _ in scan(diff)] == [5]


def test_scan_resets_hunk_at_each_new_file():
    diff = "\n".join([
        "diff --git a/a.py b/a.py",
        "@@ -1 +1 @@",
        "+print('safe')",
        "diff --git a/b.py b/b.py",
        f"+++{execute}{decode}(payload))",
    ])
    assert scan(diff) == []
