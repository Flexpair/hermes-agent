from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/ci/report_linux_test_scope.py")
SPEC = importlib.util.spec_from_file_location("report_linux_test_scope", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REPORT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REPORT
SPEC.loader.exec_module(REPORT)


def test_report_script_compiles() -> None:
    result = subprocess.run(
        ["uv", "run", "--no-sync", "python", "-m", "py_compile", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_marker_scope_handles_module_marks_and_aliases(tmp_path: Path) -> None:
    path = tmp_path / "tests" / "test_markers.py"
    path.parent.mkdir()
    path.write_text(
        "import pytest\n"
        "linux_only = pytest.mark.linux_only\n"
        "pytestmark = [linux_only]\n\n"
        "def test_module(): pass\n",
        encoding="utf-8",
    )
    scope = REPORT._read_marker_scope(tmp_path, ["tests/test_markers.py"])
    assert "tests/test_markers.py::test_module" in scope["linux_only"]


def test_parse_files_reads_runner_slice_output() -> None:
    lines = ['{"slice": [{"index": 1, "files": "tests/a.py:tests/b.py"}]}']
    assert REPORT._parse_files(lines) == ["tests/a.py", "tests/b.py"]


def test_count_ast_tests_counts_functions(tmp_path: Path) -> None:
    path = tmp_path / "tests" / "test_counts.py"
    path.parent.mkdir()
    path.write_text("def test_one(): pass\nasync def test_two(): pass\n", encoding="utf-8")
    assert REPORT._count_ast_tests(tmp_path, ["tests/test_counts.py"]) == 2


def test_eligible_scope_retains_mixed_marker_files(tmp_path: Path) -> None:
    path = tmp_path / "tests" / "test_mixed.py"
    path.parent.mkdir()
    path.write_text(
        "import pytest\n\n"
        "@pytest.mark.macos_only\ndef test_macos(): pass\n\n"
        "def test_shared(): pass\n",
        encoding="utf-8",
    )
    nodes = REPORT._eligible_linux_nodes(tmp_path, ["tests/test_mixed.py"])
    assert nodes == ["tests/test_mixed.py::test_shared"]


def test_report_script_records_conservative_linux_policy(tmp_path: Path) -> None:
    output = tmp_path / "scope.json"
    result = subprocess.run(
        ["uv", "run", "--no-sync", "python", str(SCRIPT), "--output", str(output)],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert result.returncode in (0, 2), result.stdout + result.stderr
    report = json.loads(output.read_text())
    assert report["selection_policy"] == {
        "default_launcher_excludes": ["integration", "e2e", "docker"],
        "exclude_explicit_macos_only": True,
        "exclude_explicit_windows_only": True,
        "include_explicit_linux_only": True,
        "include_unmarked_shared_tests": True,
    }
    assert report["collection_returncode"] == 0
    assert report["linux_eligible"]["test_cases"] > 0
    assert report["linux_eligible"]["test_cases"] <= report["all_collected"]["test_cases"]
    assert report["linux_eligible"]["test_files"] <= report["all_collected"]["test_files"]
    assert report["marker_collections"]["linux_only"]["test_files"] > 0
    assert report["marker_collections"]["macos_only"]["test_files"] > 0
    assert report["marker_collections"]["windows_only"]["test_files"] > 0
