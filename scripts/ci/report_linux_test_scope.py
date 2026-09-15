#!/usr/bin/env python3
"""Report the conservative Linux test scope from pytest's collected items.

The report intentionally uses host-compatible collection rather than requiring
an explicit ``linux_only`` marker. Tests marked for another operating system
are excluded; unmarked tests remain eligible because they are shared behavior.
Dedicated e2e, integration, and docker paths are reported separately because
``scripts/run_tests_parallel.py`` excludes them by default.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

_MARKER_NAMES = ("linux_only", "macos_only", "windows_only")


def _run_collect(root: Path, args: list[str]) -> tuple[int, list[str], str]:
    """Run canonical discovery; its output is the affordable file inventory."""
    proc = subprocess.run(
        [
            "uv",
            "run",
            "--no-sync",
            "scripts/run_tests_parallel.py",
            "--generate-slices",
            "1",
            *args,
        ],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return proc.returncode, proc.stdout.splitlines(), proc.stdout


def _report(
    root: Path, files: list[str], test_cases: int | None = None
) -> dict[str, object]:
    """Report the file inventory discovered by the canonical runner.

    ``test_cases`` is a static test-function count; parametrized runtime-case
    counts are higher when the canonical runner executes them.
    """
    groups = Counter()
    for item in files:
        parts = Path(item).parts
        if "e2e" in parts:
            groups["e2e"] += 1
        elif "integration" in parts:
            groups["integration"] += 1
        elif "docker" in parts:
            groups["docker"] += 1
        else:
            groups["shared_or_unit"] += 1
    return {
        "test_cases": (
            _count_ast_tests(root, files) if test_cases is None else test_cases
        ),
        "test_files": len(files),
        "groups": dict(sorted(groups.items())),
        "files": sorted(files),
    }


def _parse_files(lines: list[str]) -> list[str]:
    """Extract paths from the runner's JSON slice output."""
    try:
        data = json.loads("\n".join(lines))
    except json.JSONDecodeError:
        return []
    files: list[str] = []
    for slice_data in data.get("slice", []):
        joined = slice_data.get("files", "")
        if joined:
            files.extend(joined.split(":"))
    return files


def _count_ast_tests(root: Path, files: list[str]) -> int:
    """Count test functions in discovered files without importing the tree."""
    total = 0
    for relative in files:
        try:
            tree = ast.parse((root / relative).read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        total += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
    return total


def _read_marker_scope(root: Path, files: list[str]) -> dict[str, set[str]]:
    """Return test node IDs carrying each explicit OS marker.

    AST traversal handles decorator, module-level ``pytestmark``, and simple
    aliases without importing test modules a second time.
    """
    result = {marker: set() for marker in _MARKER_NAMES}

    for relative in files:
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except (OSError, SyntaxError):
            continue

        def decorator_name(node: ast.AST) -> str:
            if isinstance(node, ast.Attribute):
                return node.attr
            if isinstance(node, ast.Call):
                return decorator_name(node.func)
            return ""

        module_marks = _module_marker_names(tree)

        def visit(node: ast.AST, inherited: set[str], parents: tuple[str, ...]) -> None:
            marks = set(inherited)
            if isinstance(node, ast.Module):
                marks.update(module_marks)
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                marks.update(decorator_name(d) for d in node.decorator_list)
            next_parents = parents
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                next_parents = parents + (node.name,)
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("test_")
            ):
                node_id = "::".join((relative, *next_parents))
                for marker in _MARKER_NAMES:
                    if marker in marks:
                        result[marker].add(node_id)
            child_marks = marks if isinstance(node, (ast.Module, ast.ClassDef)) else inherited
            for child in ast.iter_child_nodes(node):
                visit(child, child_marks, next_parents)

        visit(tree, set(), ())
    return result


def _module_marker_names(tree: ast.AST) -> set[str]:
    """Extract OS marks from simple ``pytestmark`` assignments and aliases."""
    aliases: dict[str, set[str]] = {}
    marks: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "pytestmark":
                    values = (
                        node.value.elts
                        if isinstance(node.value, (ast.List, ast.Tuple))
                        else [node.value]
                    )
                    for value in values:
                        if isinstance(value, ast.Attribute) and value.attr in _MARKER_NAMES:
                            marks.add(value.attr)
                        elif isinstance(value, ast.Name):
                            marks.update(aliases.get(value.id, set()))
                elif isinstance(target, ast.Name) and isinstance(node.value, ast.Attribute):
                    if node.value.attr in _MARKER_NAMES:
                        aliases[target.id] = {node.value.attr}
    return marks


def _eligible_linux_nodes(root: Path, files: list[str]) -> list[str]:
    """Return unmarked/Linux test nodes while retaining mixed-marker files.

    A file is eligible when it has at least one eligible node; only the
    explicitly foreign-OS nodes are removed from the case count.
    """
    eligible: list[str] = []
    for relative in files:
        path = root / relative
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        module_marks = _module_marker_names(tree)

        def decorator_name(node: ast.AST) -> str:
            if isinstance(node, ast.Attribute):
                return node.attr
            if isinstance(node, ast.Call):
                return decorator_name(node.func)
            return ""

        def visit(node: ast.AST, inherited: set[str], parents: tuple[str, ...]) -> None:
            marks = set(inherited)
            if isinstance(node, ast.Module):
                marks.update(module_marks)
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                marks.update(decorator_name(d) for d in node.decorator_list)
            next_parents = parents
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                next_parents = parents + (node.name,)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                node_id = "::".join((relative, *next_parents))
                if not marks.intersection({"macos_only", "windows_only"}):
                    eligible.append(node_id)

            child_marks = marks if isinstance(node, (ast.Module, ast.ClassDef)) else inherited
            for child in ast.iter_child_nodes(node):
                visit(child, child_marks, next_parents)

        visit(tree, set(), ())
    return eligible


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()

    # Route discovery through the runner's own file discovery, which applies
    # the same integration/e2e/docker exclusions as the execution path. The
    # report is informational; the following run_tests.sh step is the gate.
    rc, lines, output = _run_collect(root, ["--paths", "tests"])
    all_files = _parse_files(lines)
    all_report = _report(root, all_files)

    marker_nodes = _read_marker_scope(root, all_files)
    marker_reports = {}
    for marker, node_ids in marker_nodes.items():
        marker_files = sorted({item.split("::", 1)[0] for item in node_ids})
        marker_reports[marker] = _report(root, marker_files, len(node_ids))

    eligible_nodes = _eligible_linux_nodes(root, all_files)
    eligible_files = sorted({item.split("::", 1)[0] for item in eligible_nodes})
    eligible_report = _report(root, eligible_files, len(eligible_nodes))

    report = {
        "collection_returncode": rc,
        "all_collected": all_report,
        "linux_eligible": eligible_report,
        "marker_collections": marker_reports,
        "selection_policy": {
            "include_explicit_linux_only": True,
            "include_unmarked_shared_tests": True,
            "exclude_explicit_macos_only": True,
            "exclude_explicit_windows_only": True,
            "default_launcher_excludes": ["integration", "e2e", "docker"],
        },
        "collection_tail": output.splitlines()[-8:],
    }
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    if rc != 0:
        print(
            "pytest collection did not complete; see collection_tail in the report",
            file=sys.stderr,
        )
        return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
