#!/usr/bin/env python3
"""Error analysis across type checkers.

This script:
1. Runs type checkers on a package and captures raw error output
2. Parses and normalizes errors from each checker
3. Groups errors by location to find discrepancies (using pyright as source of truth)
4. Creates minimal reproductions for each discrepancy
5. Verifies reproductions by running pyright and pyrefly on them
6. Generates a markdown report with findings
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Add parent directories to path for imports
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from type_checker_benchmark.daily_runner import (
    fetch_github_package,
    is_type_checker_available,
    run_process_with_timeout,
)

# Type checkers to analyze
TYPE_CHECKERS = ["pyright", "pyrefly", "ty", "mypy", "zuban"]

# Line tolerance for matching errors across checkers
LINE_TOLERANCE = 2


@dataclass
class ParsedError:
    """A parsed error from a type checker."""

    file: str
    line: int
    column: int | None
    error_code: str
    message: str
    checker: str
    severity: str = "error"  # error, warning, note

    def location_key(self, tolerance: int = 0) -> str:
        """Return a key for grouping errors by location."""
        return f"{self.file}:{self.line}"

    def matches_location(self, other: "ParsedError", tolerance: int = LINE_TOLERANCE) -> bool:
        """Check if this error matches another's location within tolerance."""
        if self.file != other.file:
            return False
        return abs(self.line - other.line) <= tolerance


@dataclass
class ErrorGroup:
    """A group of errors at the same location from different checkers."""

    file: str
    line: int
    errors: list[ParsedError] = field(default_factory=list)

    @property
    def checkers_with_errors(self) -> set[str]:
        """Return set of checkers that found errors at this location."""
        return {e.checker for e in self.errors}

    @property
    def has_pyright_error(self) -> bool:
        """Return True if pyright found an error here."""
        return "pyright" in self.checkers_with_errors

    @property
    def has_pyrefly_error(self) -> bool:
        """Return True if pyrefly found an error here."""
        return "pyrefly" in self.checkers_with_errors

    @property
    def is_consensus(self) -> bool:
        """Return True if all 5 checkers found an error here."""
        return len(self.checkers_with_errors) == 5

    @property
    def is_pyrefly_false_positive(self) -> bool:
        """Return True if pyrefly reports error but pyright does NOT.

        Uses pyright as source of truth.
        """
        return self.has_pyrefly_error and not self.has_pyright_error

    @property
    def is_pyrefly_false_negative(self) -> bool:
        """Return True if pyright reports error but pyrefly does NOT.

        Uses pyright as source of truth.
        """
        return self.has_pyright_error and not self.has_pyrefly_error

    # Keep old properties for backwards compatibility
    @property
    def is_pyrefly_only(self) -> bool:
        """Return True if only pyrefly found an error here."""
        return self.checkers_with_errors == {"pyrefly"}

    @property
    def is_pyrefly_missing(self) -> bool:
        """Return True if 2+ others found error but pyrefly didn't."""
        others = self.checkers_with_errors - {"pyrefly"}
        return len(others) >= 2 and "pyrefly" not in self.checkers_with_errors


@dataclass
class AnalysisResult:
    """Result of analyzing a potential false positive/negative."""

    error_group: ErrorGroup
    github_link: str
    source_context: str
    minimal_repro_path: Path | None = None
    pyright_repro_result: str = ""  # "error", "no_error", "failed"
    pyrefly_repro_result: str = ""  # "error", "no_error", "failed"
    repro_verified: bool = False  # True if repro confirms the discrepancy
    is_legitimate_error: bool | None = None
    claude_assessment: str = ""
    classification: str = ""  # "false_positive", "false_negative", "true_positive", etc.


def normalize_file_path(file_path: str, package_name: str = "") -> str:
    """Normalize a file path to a relative path for comparison.

    Different type checkers output paths differently:
    - pyright/mypy/pyrefly: absolute paths like /var/folders/.../django/django/foo.py
    - zuban: relative paths from within package like template/foo.py (no django/ prefix)

    This function extracts just the relative portion for comparison.
    For django specifically, we want to match:
    - /var/.../django/django/template/foo.py -> template/foo.py
    - django/template/foo.py -> template/foo.py
    - template/foo.py -> template/foo.py
    """
    # If it's already a relative path without the package prefix, return as-is
    if not file_path.startswith("/"):
        # For relative paths like "django/template/foo.py" -> "template/foo.py"
        if package_name and file_path.startswith(f"{package_name}/"):
            return file_path[len(package_name) + 1:]
        return file_path

    # For absolute paths, find the package folder and extract path after it
    parts = file_path.split("/")

    if package_name:
        # Find the last occurrence of package_name (handles .../django/django/...)
        last_pkg_idx = -1
        for i, part in enumerate(parts):
            if part == package_name:
                last_pkg_idx = i

        if last_pkg_idx >= 0:
            # Return everything after the last occurrence of the package name
            return "/".join(parts[last_pkg_idx + 1:])

    # Fallback: return the last meaningful path components
    # Skip temp directory prefixes
    for i, part in enumerate(parts):
        if part in ("src", "lib") or (package_name and part == package_name):
            return "/".join(parts[i:])

    # Last resort: return last 4 components
    if len(parts) > 4:
        return "/".join(parts[-4:])
    return file_path


def get_commit_sha(package_path: Path) -> str:
    """Get the commit SHA of the cloned repository."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=package_path,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "main"


def make_github_link(github_url: str, commit_sha: str, file_path: str, line: int) -> str:
    """Generate a GitHub link to a specific line."""
    # Convert github_url to blob URL
    # e.g., https://github.com/django/django -> https://github.com/django/django/blob/<sha>/path#L123
    base_url = github_url.rstrip("/")
    return f"{base_url}/blob/{commit_sha}/{file_path}#L{line}"


def parse_pyright_errors(output: str, checker: str = "pyright") -> list[ParsedError]:
    """Parse pyright JSON output into ParsedError objects."""
    errors = []
    try:
        data = json.loads(output)
        for diag in data.get("generalDiagnostics", []):
            severity = diag.get("severity", "error")
            if severity not in ("error", "warning"):
                continue

            file_path = diag.get("file", "")
            range_info = diag.get("range", {})
            start = range_info.get("start", {})

            errors.append(ParsedError(
                file=file_path,
                line=start.get("line", 0) + 1,  # pyright uses 0-indexed lines
                column=start.get("character", 0) + 1,
                error_code=diag.get("rule", "unknown"),
                message=diag.get("message", ""),
                checker=checker,
                severity=severity,
            ))
    except json.JSONDecodeError:
        # Fallback to text parsing
        pass
    return errors


def parse_pyrefly_errors(output: str) -> list[ParsedError]:
    """Parse pyrefly output into ParsedError objects.

    Pyrefly format:
    ERROR message [code]
       --> file:line:col
    """
    errors = []
    lines = output.split('\n')

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Look for ERROR or WARNING lines
        error_match = re.match(r'^(ERROR|WARNING)\s+(.+?)(?:\s*\[([^\]]+)\])?\s*$', line)
        if error_match:
            severity = error_match.group(1).lower()
            message = error_match.group(2).strip()
            error_code = error_match.group(3) or "unknown"

            # Look for the location on the next line(s)
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith('|'):
                j += 1

            if j < len(lines):
                loc_line = lines[j].strip()
                loc_match = re.match(r'^-->\s*(.+?):(\d+):(\d+)', loc_line)
                if loc_match:
                    file_path = loc_match.group(1)
                    line_num = int(loc_match.group(2))
                    col = int(loc_match.group(3))

                    errors.append(ParsedError(
                        file=file_path,
                        line=line_num,
                        column=col,
                        error_code=error_code,
                        message=message,
                        checker="pyrefly",
                        severity=severity,
                    ))
                    i = j
        i += 1

    return errors


def parse_ty_errors(output: str) -> list[ParsedError]:
    """Parse ty output into ParsedError objects.

    ty format is similar to pyrefly:
    error[code]: message
       --> file:line:col
    """
    errors = []
    lines = output.split('\n')

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Look for error[code] or warning[code] lines
        error_match = re.match(r'^(error|warning)\[([^\]]+)\]:\s*(.+)$', line, re.IGNORECASE)
        if error_match:
            severity = error_match.group(1).lower()
            error_code = error_match.group(2)
            message = error_match.group(3).strip()

            # Look for the location on subsequent lines
            j = i + 1
            while j < len(lines):
                loc_line = lines[j].strip()
                loc_match = re.match(r'^-->\s*(.+?):(\d+):(\d+)', loc_line)
                if loc_match:
                    file_path = loc_match.group(1)
                    line_num = int(loc_match.group(2))
                    col = int(loc_match.group(3))

                    errors.append(ParsedError(
                        file=file_path,
                        line=line_num,
                        column=col,
                        error_code=error_code,
                        message=message,
                        checker="ty",
                        severity=severity,
                    ))
                    i = j
                    break
                elif loc_line.startswith('|') or loc_line == '':
                    j += 1
                else:
                    break
        i += 1

    return errors


def parse_text_errors(output: str, checker: str) -> list[ParsedError]:
    """Parse text-based error output (mypy, pyrefly, ty, zuban style)."""
    errors = []

    # Common pattern: file.py:line:col: severity: message [code]
    # Also handles: file.py:line: severity: message
    pattern = r'^(.+?):(\d+):(?:(\d+):)?\s*(error|warning|note):\s*(.+?)(?:\s*\[([^\]]+)\])?$'

    for line in output.split('\n'):
        line = line.strip()
        if not line:
            continue

        match = re.match(pattern, line, re.IGNORECASE)
        if match:
            file_path, line_num, col, severity, message, code = match.groups()
            if severity.lower() not in ("error", "warning"):
                continue

            errors.append(ParsedError(
                file=file_path,
                line=int(line_num),
                column=int(col) if col else None,
                error_code=code or "unknown",
                message=message.strip(),
                checker=checker,
                severity=severity.lower(),
            ))

    return errors


def parse_errors(output: str, checker: str) -> list[ParsedError]:
    """Parse error output based on checker type."""
    if checker == "pyright":
        errors = parse_pyright_errors(output, checker)
        if errors:
            return errors

    if checker == "pyrefly":
        errors = parse_pyrefly_errors(output)
        if errors:
            return errors

    if checker == "ty":
        errors = parse_ty_errors(output)
        if errors:
            return errors

    return parse_text_errors(output, checker)


def run_checker_with_output(
    checker: str,
    package_path: Path,
    check_path: Path,
    timeout: int,
) -> tuple[str, list[ParsedError]]:
    """Run a type checker and return raw output and parsed errors."""

    if checker == "pyright":
        result = run_process_with_timeout(
            ["pyright", "--outputjson", str(check_path)],
            cwd=package_path,
            timeout=timeout,
        )
    elif checker == "mypy":
        result = run_process_with_timeout(
            [sys.executable, "-m", "mypy", str(check_path)],
            cwd=package_path,
            timeout=timeout,
        )
    elif checker == "pyrefly":
        # Run pyrefly init to migrate any existing mypy/pyright configs
        try:
            subprocess.run(
                ["pyrefly", "init", str(package_path)],
                cwd=package_path,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, Exception):
            pass
        result = run_process_with_timeout(
            ["pyrefly", "check", str(check_path)],
            cwd=check_path,
            timeout=timeout,
        )
    elif checker == "ty":
        result = run_process_with_timeout(
            ["ty", "check", str(check_path)],
            cwd=check_path,
            timeout=timeout,
        )
    elif checker == "zuban":
        result = run_process_with_timeout(
            ["zuban", "check", "."],
            cwd=check_path,
            timeout=timeout,
        )
    else:
        return "", []

    if result["timed_out"]:
        return f"TIMEOUT after {timeout}s", []

    output = result["stdout"] + result["stderr"]
    errors = parse_errors(output, checker)

    return output, errors


def group_errors_by_location(
    all_errors: dict[str, list[ParsedError]],
    tolerance: int = LINE_TOLERANCE,
    package_name: str = "",
) -> list[ErrorGroup]:
    """Group errors from all checkers by file:line location.

    Uses normalized file paths to match errors across checkers that output
    different path formats (absolute vs relative).
    """

    # First, collect all unique locations using normalized paths
    # Key is normalized_file:line, value is the ErrorGroup
    location_to_group: dict[str, ErrorGroup] = {}
    # Track the normalized path for each group's file
    group_normalized_paths: dict[str, str] = {}

    for checker, errors in all_errors.items():
        for error in errors:
            # Normalize the file path for comparison
            normalized_file = normalize_file_path(error.file, package_name)
            key = f"{normalized_file}:{error.line}"

            # Check if there's an existing group within tolerance
            matched_group = None
            for existing_key, group in location_to_group.items():
                existing_normalized = group_normalized_paths[existing_key]
                existing_line_str = existing_key.rsplit(":", 1)[1]
                existing_line = int(existing_line_str)

                if normalized_file == existing_normalized and abs(error.line - existing_line) <= tolerance:
                    matched_group = group
                    break

            if matched_group:
                matched_group.errors.append(error)
            else:
                location_to_group[key] = ErrorGroup(
                    file=error.file,  # Keep original file path for the group
                    line=error.line,
                    errors=[error],
                )
                group_normalized_paths[key] = normalized_file

    return list(location_to_group.values())


def get_source_context(package_path: Path, file_path: str, line: int, context_lines: int = 5) -> str:
    """Get source code context around a specific line."""
    full_path = package_path / file_path
    if not full_path.exists():
        return f"[File not found: {file_path}]"

    try:
        with open(full_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        start = max(0, line - context_lines - 1)
        end = min(len(lines), line + context_lines)

        context: list[str] = []
        for i in range(start, end):
            line_num = i + 1
            marker = ">>>" if line_num == line else "   "
            context.append(f"{marker} {line_num:4d} | {lines[i].rstrip()}")

        return "\n".join(context)
    except Exception as e:
        return f"[Error reading file: {e}]"


class NameCollector(ast.NodeVisitor):
    """AST visitor that collects all referenced names in a node."""

    def __init__(self) -> None:
        self.names: set[str] = set()
        self.defined_names: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.names.add(node.id)
        elif isinstance(node.ctx, ast.Store):
            self.defined_names.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Collect the base name (e.g., for 'foo.bar', collect 'foo')
        if isinstance(node.value, ast.Name):
            self.names.add(node.value.id)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.defined_names.add(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.defined_names.add(node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.defined_names.add(node.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name.split('.')[0]
            self.defined_names.add(name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.defined_names.add(name)
        self.generic_visit(node)


def find_enclosing_scope(
    tree: ast.Module,
    target_line: int,
) -> tuple[ast.AST | None, int, int]:
    """Find the function or class that contains the target line.

    Returns:
        Tuple of (node, start_line, end_line) or (None, 0, 0) if not found.
    """
    best_match: ast.AST | None = None
    best_start = 0
    best_end = 0

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno
            end = getattr(node, 'end_lineno', start + 50) or start + 50

            if start <= target_line <= end:
                # Prefer the innermost scope (smallest range containing target)
                if best_match is None or (end - start) < (best_end - best_start):
                    best_match = node
                    best_start = start
                    best_end = end

    return best_match, best_start, best_end


def collect_definitions_at_module_level(
    tree: ast.Module,
    needed_names: set[str],
) -> dict[str, str]:
    """Find module-level definitions (classes, functions, assignments) for needed names.

    Returns:
        Dict mapping name -> source code of the definition.
    """
    definitions: dict[str, str] = {}

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in needed_names:
                definitions[node.name] = ast.unparse(node)
        elif isinstance(node, ast.ClassDef):
            if node.name in needed_names:
                definitions[node.name] = ast.unparse(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in needed_names:
                        definitions[target.id] = ast.unparse(node)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id in needed_names:
                    definitions[node.target.id] = ast.unparse(node)

    return definitions


# Standard library and typing names that don't need stubs
BUILTIN_NAMES = {
    'True', 'False', 'None', 'print', 'len', 'range', 'str', 'int', 'float',
    'bool', 'list', 'dict', 'set', 'tuple', 'type', 'object', 'super',
    'isinstance', 'issubclass', 'hasattr', 'getattr', 'setattr', 'delattr',
    'property', 'staticmethod', 'classmethod', 'abs', 'all', 'any', 'bin',
    'callable', 'chr', 'ord', 'dir', 'divmod', 'enumerate', 'eval', 'exec',
    'filter', 'format', 'frozenset', 'globals', 'hash', 'hex', 'id', 'input',
    'iter', 'locals', 'map', 'max', 'min', 'next', 'oct', 'open', 'pow',
    'repr', 'reversed', 'round', 'slice', 'sorted', 'sum', 'vars', 'zip',
    'Exception', 'BaseException', 'TypeError', 'ValueError', 'AttributeError',
    'KeyError', 'IndexError', 'RuntimeError', 'StopIteration', 'OSError',
    'IOError', 'FileNotFoundError', 'NotImplementedError', 'AssertionError',
    'ImportError', 'ModuleNotFoundError', 'NameError', 'ZeroDivisionError',
    # Common typing names
    'Any', 'Optional', 'Union', 'List', 'Dict', 'Set', 'Tuple', 'Callable',
    'Type', 'TypeVar', 'Generic', 'Protocol', 'Literal', 'Final', 'ClassVar',
    'Sequence', 'Mapping', 'Iterable', 'Iterator', 'Generator', 'Coroutine',
    'Awaitable', 'AsyncIterator', 'AsyncIterable', 'AsyncGenerator',
    'overload', 'cast', 'Self', 'Never', 'NoReturn', 'Concatenate', 'ParamSpec',
    'TypeAlias', 'TypeGuard', 'Unpack', 'Required', 'NotRequired', 'TypedDict',
}


def generate_stub_for_name(name: str) -> str:
    """Generate a type stub for an undefined name."""
    # Simple heuristic: CamelCase names are likely classes, others are likely variables
    if name and name[0].isupper() and not name.isupper():
        return f"class {name}: ..."
    else:
        return f"{name}: Any = None"


def create_minimal_repro_with_claude(
    package_path: Path,
    file_path: str,
    error_line: int,
    repro_dir: Path,
    repro_name: str,
    error_group: ErrorGroup,
    is_false_positive: bool,
    intermediate_file: Path,
    verified_repros: list[Path],
) -> tuple[Path | None, bool]:
    """Create a minimal reproduction using Claude CLI with LSP-based type extraction.

    Uses Claude Code CLI to analyze the source file with LSP, extract type information
    for relevant symbols, and synthesize a self-contained repro that reproduces the
    type checker discrepancy.

    Args:
        package_path: Path to the cloned package
        file_path: Relative path to the file within the package
        error_line: Line number where the error occurs
        repro_dir: Directory to write repro files
        repro_name: Name for the repro file (without .py extension)
        error_group: ErrorGroup containing errors from all checkers
        is_false_positive: True if this is a false positive (pyrefly error, no pyright error)
        intermediate_file: Path to JSON file with all errors for scanning
        verified_repros: List of already verified repro files to check for similarity

    Returns:
        Tuple of (repro_path, verified) - repro_path is None if creation failed,
        verified is True if the repro reproduces the discrepancy.
    """
    full_path = package_path / file_path
    if not full_path.exists():
        return None, False

    # Get error details
    pyrefly_error = next((e for e in error_group.errors if e.checker == "pyrefly"), None)
    pyright_error = next((e for e in error_group.errors if e.checker == "pyright"), None)

    if is_false_positive:
        error_desc = f"Pyrefly error: {pyrefly_error.message} [{pyrefly_error.error_code}]" if pyrefly_error else "Pyrefly error"
        expectation = "pyrefly should report an error but pyright should NOT"
        error_type = "false_positives"
    else:
        error_desc = f"Pyright error: {pyright_error.message} [{pyright_error.error_code}]" if pyright_error else "Pyright error"
        expectation = "pyright should report an error but pyrefly should NOT"
        error_type = "false_negatives"

    repro_path = repro_dir / f"{repro_name}.py"

    # Build list of existing repros for similarity check
    existing_repros_str = ""
    if verified_repros:
        existing_repros_str = "\n".join([f"  - {p.name}" for p in verified_repros])

    # Build detailed prompt for Claude CLI
    prompt = f'''Create a minimal, self-contained Python file that reproduces a type checker discrepancy.

SOURCE FILE: {full_path}
ERROR LINE: {error_line}
ERROR: {error_desc}
EXPECTATION: When type-checked, {expectation}

INTERMEDIATE FILE: {intermediate_file}
This JSON file contains all {error_type} from the analysis. Read it first to understand patterns.

EXISTING VERIFIED REPROS:
{existing_repros_str if existing_repros_str else "  (none yet)"}

INSTRUCTIONS:
0. FIRST: Read the intermediate file {intermediate_file} and scan the list of errors.
   Look for errors with similar patterns (same error code, similar message structure).
   If this error appears to be the same root cause as an existing verified repro, respond with "DUPLICATE_OF: <repro_name>".

1. If not a duplicate, read the source file to understand the code context around line {error_line}.

2. Use the LSP tool to get type information:
   - Call LSP hover on line {error_line} to get the types of symbols involved in the error
   - Call LSP goToDefinition to find the type definitions being used
   - Identify the exact type signatures that cause the discrepancy

3. Create a MINIMAL repro file that:
   - Has ONLY `from typing import ...` - NO other imports allowed
   - NO `import sys`, NO `from __future__ import`, NO `import abc`, etc.
   - Synthesizes stub classes/types that match the actual type signatures from LSP
   - Preserves the type relationships that cause the error
   - Is as SHORT as possible while still reproducing the issue
   - Does NOT use `Any` for types involved in the error - use the actual type structure from LSP
   - Must be FULLY ISOLATED - runnable with zero dependencies

4. Write the repro to: {repro_path}

5. Verify by running both type checkers:
   - Run: pyright {repro_path}
   - Run: pyrefly check {repro_path}

   Confirm that {expectation}.

6. If verification fails, iterate and fix the repro until it works.

IMPORTANT: Respond with:
- "DUPLICATE_OF: <name>" if this is the same issue as an existing repro
- "CANNOT_REPRODUCE" if you cannot create a verified repro after a few attempts
- Otherwise, just complete the task and create the verified repro file
'''

    try:
        # Run Claude CLI with print mode
        # Pass prompt via stdin to avoid argument parsing issues with special characters
        result = subprocess.run(
            [
                "claude",
                "--print",
                "--add-dir", str(package_path),  # Allow access to the temp package directory
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=180,  # 3 minutes
        )

        # Debug: print stderr if there was an issue
        if result.stderr:
            print(f"    Claude CLI stderr: {result.stderr[:200]}")

        # Check for duplicate detection
        if "DUPLICATE_OF:" in result.stdout:
            import re
            match = re.search(r'DUPLICATE_OF:\s*(\S+)', result.stdout)
            if match:
                print(f"    Duplicate of existing repro: {match.group(1)}")
            return None, False

        # Check for cannot reproduce
        if "CANNOT_REPRODUCE" in result.stdout or "CANNOT_REPRODUCE" in result.stderr:
            print(f"    Claude responded with CANNOT_REPRODUCE")
            return None, False

        # Check if repro was created
        if not repro_path.exists():
            print(f"    Repro file not created at: {repro_path}")
            # Show first 500 chars of output for debugging
            if result.stdout:
                print(f"    Claude output (first 300 chars): {result.stdout[:300]}")
            return None, False

        # Verify the repro
        pyright_result, pyrefly_result, verified = verify_repro(
            repro_path,
            expected_pyright_error=not is_false_positive,
            expected_pyrefly_error=is_false_positive,
        )

        if verified:
            return repro_path, True
        else:
            # Delete unverified repro
            repro_path.unlink(missing_ok=True)
            return None, False

    except subprocess.TimeoutExpired:
        return None, False
    except FileNotFoundError:
        # Claude CLI not available
        return None, False
    except Exception:
        return None, False


def create_minimal_repro(
    package_path: Path,
    file_path: str,
    error_line: int,
    repro_dir: Path,
    repro_name: str,
    error_group: ErrorGroup,
) -> Path | None:
    """Create a minimal, self-contained reproduction for a type checker discrepancy.

    The reproduction file:
    - Has NO external dependencies (only stdlib typing imports)
    - Stubs all undefined names with `class X: ...` or `X: Any`
    - Extracts only the relevant function/class containing the error
    - Can be type-checked by pyright/pyrefly without installing anything

    Returns:
        Path to the created repro file, or None if creation failed.
    """
    full_path = package_path / file_path
    if not full_path.exists():
        return None

    try:
        with open(full_path, encoding="utf-8", errors="replace") as f:
            source = f.read()
            all_lines = source.splitlines(keepends=True)
    except Exception:
        return None

    # Try AST-based extraction
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fall back to line-based extraction for unparseable files
        return _create_fallback_repro(
            all_lines, error_line, repro_dir, repro_name, error_group, file_path
        )

    # Find the enclosing function or class
    scope_node, scope_start, scope_end = find_enclosing_scope(tree, error_line)

    # Determine what source to extract
    if scope_node is not None:
        # Extract the scope (function or class)
        extracted_source = ast.unparse(scope_node)
        scope_name = getattr(scope_node, 'name', 'unknown')
    else:
        # No enclosing scope found - extract lines around the error
        start = max(0, error_line - 15)
        end = min(len(all_lines), error_line + 10)
        extracted_source = "".join(all_lines[start:end])
        scope_name = "module_level"

    # Collect names used in the extracted source
    collector = NameCollector()
    try:
        extracted_tree = ast.parse(extracted_source)
        collector.visit(extracted_tree)
    except SyntaxError:
        pass

    # Find ALL undefined names (used but not defined locally)
    used_names = collector.names
    defined_in_scope = collector.defined_names
    undefined_names = used_names - defined_in_scope - BUILTIN_NAMES

    # Try to find module-level definitions for undefined names from same file
    local_definitions = collect_definitions_at_module_level(tree, undefined_names)
    names_with_local_defs = set(local_definitions.keys())

    # Everything else gets stubbed (no external imports!)
    names_to_stub = undefined_names - names_with_local_defs

    # Build the reproduction file
    repro_parts: list[str] = []

    # Header comment with error information
    pyrefly_error = next((e for e in error_group.errors if e.checker == "pyrefly"), None)
    pyright_error = next((e for e in error_group.errors if e.checker == "pyright"), None)

    repro_parts.append('"""Minimal reproduction for type checker discrepancy.\n\n')
    repro_parts.append(f"Original file: {file_path}\n")
    repro_parts.append(f"Original line: {error_line}\n")
    repro_parts.append(f"Extracted scope: {scope_name}\n")
    if pyrefly_error:
        repro_parts.append(f"\nPyrefly error: {pyrefly_error.message} [{pyrefly_error.error_code}]\n")
    if pyright_error:
        repro_parts.append(f"Pyright error: {pyright_error.message} [{pyright_error.error_code}]\n")
    repro_parts.append('\nThis is a self-contained repro with no external dependencies.\n')
    repro_parts.append('"""\n\n')

    # Add from __future__ annotations if original file had it
    for line in all_lines[:20]:
        if "from __future__ import annotations" in line:
            repro_parts.append("from __future__ import annotations\n\n")
            break

    # Add typing imports (only stdlib - no external dependencies)
    repro_parts.append("from typing import (\n")
    repro_parts.append("    Any, Callable, ClassVar, Final, Generic, Literal,\n")
    repro_parts.append("    Optional, Protocol, TypeVar, Union, overload,\n")
    repro_parts.append(")\n\n")

    # Generate stubs for all undefined names
    if names_to_stub:
        repro_parts.append("# === Stubs for external dependencies ===\n")
        repro_parts.append("# These replace imports that would require external packages\n\n")
        for name in sorted(names_to_stub):
            repro_parts.append(generate_stub_for_name(name))
            repro_parts.append("\n")
        repro_parts.append("\n")

    # Add local definitions that are needed
    if local_definitions:
        repro_parts.append("# === Dependencies from same file ===\n\n")
        for definition in local_definitions.values():
            repro_parts.append(definition)
            repro_parts.append("\n\n")

    # Add the main extracted source
    repro_parts.append("# === Code containing the type error ===\n\n")
    repro_parts.append(extracted_source)
    repro_parts.append("\n")

    repro_content = "".join(repro_parts)

    # Write the repro file
    repro_dir.mkdir(parents=True, exist_ok=True)
    repro_path = repro_dir / f"{repro_name}.py"

    try:
        with open(repro_path, "w", encoding="utf-8") as f:
            f.write(repro_content)
        return repro_path
    except Exception:
        return None


def _create_fallback_repro(
    all_lines: list[str],
    error_line: int,
    repro_dir: Path,
    repro_name: str,
    error_group: ErrorGroup,
    file_path: str,
) -> Path | None:
    """Create a fallback repro when AST parsing fails.

    Still self-contained with no external dependencies - just uses raw extraction.
    """
    # Find function/class boundaries
    start_line = max(0, error_line - 50)
    end_line = min(len(all_lines), error_line + 20)

    # Try to find the start of the enclosing function/class
    for i in range(error_line - 2, start_line - 1, -1):
        line = all_lines[i] if i < len(all_lines) else ""
        stripped = line.lstrip()
        if stripped.startswith(("def ", "class ", "async def ")):
            indent = len(line) - len(stripped)
            if indent == 0 or i < error_line - 40:
                start_line = i
                break
            start_line = i

    source_lines = all_lines[start_line:end_line]

    # Build the repro (NO external imports - self-contained)
    pyrefly_error = next((e for e in error_group.errors if e.checker == "pyrefly"), None)
    pyright_error = next((e for e in error_group.errors if e.checker == "pyright"), None)

    repro_parts: list[str] = []
    repro_parts.append('"""Minimal reproduction (fallback extraction).\n\n')
    repro_parts.append(f"Original file: {file_path}\n")
    repro_parts.append(f"Original line: {error_line}\n")
    if pyrefly_error:
        repro_parts.append(f"\nPyrefly error: {pyrefly_error.message} [{pyrefly_error.error_code}]\n")
    if pyright_error:
        repro_parts.append(f"Pyright error: {pyright_error.message} [{pyright_error.error_code}]\n")
    repro_parts.append('\nThis is a self-contained repro with no external dependencies.\n')
    repro_parts.append('NOTE: AST parsing failed, so this is a raw extraction.\n')
    repro_parts.append('"""\n\n')

    # Check for future annotations
    for line in all_lines[:20]:
        if "from __future__ import annotations" in line:
            repro_parts.append("from __future__ import annotations\n\n")
            break

    repro_parts.append("from typing import Any, Optional, Union, Callable, TypeVar, Generic\n\n")

    repro_parts.append("# === Source code (raw extraction) ===\n")
    repro_parts.append("# NOTE: May have undefined names - add stubs above as needed\n\n")
    repro_parts.append("".join(source_lines))

    repro_content = "".join(repro_parts)

    repro_dir.mkdir(parents=True, exist_ok=True)
    repro_path = repro_dir / f"{repro_name}.py"

    try:
        with open(repro_path, "w", encoding="utf-8") as f:
            f.write(repro_content)
        return repro_path
    except Exception:
        return None


def run_checker_on_file(checker: str, file_path: Path) -> tuple[bool, str]:
    """Run a type checker on a single file and return whether it found errors.

    Returns:
        Tuple of (has_errors: bool, output: str)
    """
    try:
        if checker == "pyright":
            result = subprocess.run(
                ["pyright", str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            # Pyright returns non-zero if there are errors
            has_errors = result.returncode != 0
            output = result.stdout + result.stderr
        elif checker == "pyrefly":
            result = subprocess.run(
                ["pyrefly", "check", str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            # Check for "0 errors" in output
            has_errors = "0 errors" not in result.stdout and "0 errors" not in result.stderr
            output = result.stdout + result.stderr
        else:
            return False, f"Unknown checker: {checker}"

        return has_errors, output
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except FileNotFoundError:
        return False, f"{checker} not found"
    except Exception as e:
        return False, f"Error: {e}"


def verify_repro(
    repro_path: Path,
    expected_pyright_error: bool,
    expected_pyrefly_error: bool,
) -> tuple[str, str, bool]:
    """Verify that a minimal reproduction confirms the discrepancy.

    Args:
        repro_path: Path to the reproduction file
        expected_pyright_error: True if pyright should find an error
        expected_pyrefly_error: True if pyrefly should find an error

    Returns:
        Tuple of (pyright_result, pyrefly_result, verified)
        - pyright_result: "error", "no_error", or "failed"
        - pyrefly_result: "error", "no_error", or "failed"
        - verified: True if the repro confirms the expected discrepancy
    """
    pyright_has_error, pyright_output = run_checker_on_file("pyright", repro_path)
    pyrefly_has_error, pyrefly_output = run_checker_on_file("pyrefly", repro_path)

    # Determine results
    if "not found" in pyright_output or "TIMEOUT" in pyright_output:
        pyright_result = "failed"
    else:
        pyright_result = "error" if pyright_has_error else "no_error"

    if "not found" in pyrefly_output or "TIMEOUT" in pyrefly_output:
        pyrefly_result = "failed"
    else:
        pyrefly_result = "error" if pyrefly_has_error else "no_error"

    # Check if the repro confirms the discrepancy
    # For false positive: pyrefly should error, pyright should not
    # For false negative: pyright should error, pyrefly should not
    if expected_pyright_error and not expected_pyrefly_error:
        # False negative case
        verified = pyright_result == "error" and pyrefly_result == "no_error"
    elif expected_pyrefly_error and not expected_pyright_error:
        # False positive case
        verified = pyrefly_result == "error" and pyright_result == "no_error"
    else:
        verified = False

    return pyright_result, pyrefly_result, verified


def get_top_pyrefly_error_category(errors: list[ParsedError]) -> str | None:
    """Get the most common error code from pyrefly errors."""
    if not errors:
        return None

    code_counts: dict[str, int] = defaultdict(int)
    for error in errors:
        code_counts[error.error_code] += 1

    if not code_counts:
        return None

    return max(code_counts, key=lambda k: code_counts[k])


def get_top_pyrefly_error_categories(
    errors: list[ParsedError],
    top_n: int = 5,
) -> list[tuple[str, int]]:
    """Get the top N most common error codes from pyrefly errors.

    Returns:
        List of (error_code, count) tuples sorted by count descending.
    """
    if not errors:
        return []

    code_counts: dict[str, int] = defaultdict(int)
    for error in errors:
        code_counts[error.error_code] += 1

    if not code_counts:
        return []

    sorted_codes = sorted(code_counts.items(), key=lambda x: x[1], reverse=True)
    return sorted_codes[:top_n]


def call_claude_for_analysis(
    source_context: str,
    error_group: ErrorGroup,
    github_link: str,
    analysis_type: str,  # "false_positive" or "false_negative"
) -> str:
    """Call Claude Code CLI to analyze an error."""

    # Build the prompt
    if analysis_type == "false_positive":
        prompt = f"""Analyze this potential pyrefly false positive.

Pyrefly reports an error at this location, but NO other type checker (pyright, mypy, ty, zuban) reports an error here.

**Pyrefly error:**
{error_group.errors[0].message} [{error_group.errors[0].error_code}]

**Source code:**
```python
{source_context}
```

**GitHub link:** {github_link}

Is this a legitimate type error that pyrefly correctly found (and others missed), or is this a pyrefly false positive?

Respond with:
1. VERDICT: "LEGITIMATE ERROR" or "FALSE POSITIVE"
2. Brief explanation (1-2 sentences)
"""
    else:  # false_negative
        other_errors = [e for e in error_group.errors if e.checker != "pyrefly"]
        other_messages = "\n".join([f"- {e.checker}: {e.message} [{e.error_code}]" for e in other_errors])

        prompt = f"""Analyze this potential pyrefly false negative.

Multiple type checkers report an error at this location, but pyrefly does NOT report an error here.

**Other checkers' errors:**
{other_messages}

**Source code:**
```python
{source_context}
```

**GitHub link:** {github_link}

Is this a legitimate type error that pyrefly should catch (false negative), or are the other checkers being overly strict?

Respond with:
1. VERDICT: "FALSE NEGATIVE" or "OTHER CHECKERS OVERLY STRICT"
2. Brief explanation (1-2 sentences)
"""

    # Call Claude CLI
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.stdout.strip() if result.returncode == 0 else f"Error: {result.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Claude CLI timed out"
    except FileNotFoundError:
        return "Error: Claude CLI not found"
    except Exception as e:
        return f"Error: {e}"


def extract_relative_path_from_github_link(github_link: str) -> str:
    """Extract the relative file path from a GitHub link.

    Example: https://github.com/django/django/blob/abc123/django/foo.py#L42
    Returns: django/foo.py
    """
    # Pattern: /blob/<sha>/<path>#L<line>
    match = re.search(r'/blob/[^/]+/(.+?)#L\d+', github_link)
    if match:
        return match.group(1)
    return github_link


def write_markdown_report(
    report_path: Path,
    package_name: str,
    github_url: str,
    commit_sha: str,
    all_errors: dict[str, list[ParsedError]],
    error_groups: list[ErrorGroup],
    false_positive_results: list[AnalysisResult],
    false_negative_results: list[AnalysisResult],
) -> None:
    """Write the analysis report to a markdown file."""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Type Checker Error Analysis: {package_name}\n\n")
        f.write(f"**Generated:** {datetime.now(timezone.utc).isoformat()}\n\n")
        f.write(f"**Repository:** [{github_url}]({github_url})\n\n")
        f.write(f"**Commit:** `{commit_sha}`\n\n")
        f.write("**Source of Truth:** Pyright\n\n")

        # Summary
        f.write("## Summary\n\n")
        f.write("| Type Checker | Total Errors |\n")
        f.write("|-------------|-------------|\n")
        for checker in TYPE_CHECKERS:
            count = len(all_errors.get(checker, []))
            f.write(f"| {checker} | {count} |\n")
        f.write("\n")

        # Error category stats (using pyright as source of truth)
        consensus_count = sum(1 for g in error_groups if g.is_consensus)
        false_positive_count = sum(1 for g in error_groups if g.is_pyrefly_false_positive)
        false_negative_count = sum(1 for g in error_groups if g.is_pyrefly_false_negative)

        # Count verified reproductions
        verified_fp_count = sum(1 for r in false_positive_results if r.repro_verified)
        verified_fn_count = sum(1 for r in false_negative_results if r.repro_verified)

        f.write("### Error Location Categories (Pyright as Source of Truth)\n\n")
        f.write(f"- **Consensus (all 5 agree):** {consensus_count}\n")
        f.write(f"- **False Positives (pyrefly error, no pyright error):** {false_positive_count}\n")
        f.write(f"- **False Negatives (pyright error, no pyrefly error):** {false_negative_count}\n\n")

        f.write("### Reproduction Verification\n\n")
        f.write(f"- **False Positives Verified:** {verified_fp_count}/{len(false_positive_results)}\n")
        f.write(f"- **False Negatives Verified:** {verified_fn_count}/{len(false_negative_results)}\n\n")

        # Top 5 pyrefly error categories
        pyrefly_errors = all_errors.get("pyrefly", [])
        top_categories = get_top_pyrefly_error_categories(pyrefly_errors, top_n=5)
        if top_categories:
            f.write("### Top 5 Pyrefly Error Categories\n\n")
            f.write("| Error Code | Count |\n")
            f.write("|------------|-------|\n")
            for code, count in top_categories:
                f.write(f"| `{code}` | {count} |\n")
            f.write("\n")

        # False positives section - only include verified repros
        verified_fp_results = [r for r in false_positive_results if r.repro_verified]
        f.write("## Verified Pyrefly False Positives\n\n")
        f.write("_Pyrefly reports an error but Pyright does not. Only verified repros are shown._\n\n")
        if verified_fp_results:
            for i, result in enumerate(verified_fp_results, 1):
                rel_path = extract_relative_path_from_github_link(result.github_link)
                f.write(f"### {i}. {rel_path}:{result.error_group.line}\n\n")
                f.write(f"**GitHub:** [{rel_path}#L{result.error_group.line}]({result.github_link})\n\n")

                pyrefly_error = next((e for e in result.error_group.errors if e.checker == "pyrefly"), None)
                if pyrefly_error:
                    f.write(f"**Pyrefly error:** `{pyrefly_error.message}` [{pyrefly_error.error_code}]\n\n")

                if result.minimal_repro_path:
                    f.write(f"**Minimal Repro:** `{result.minimal_repro_path.name}`\n\n")

                f.write("**Source:**\n```python\n")
                f.write(result.source_context)
                f.write("\n```\n\n")
                f.write("---\n\n")
        else:
            f.write("_No verified false positives._\n\n")

        # False negatives section - only include verified repros
        verified_fn_results = [r for r in false_negative_results if r.repro_verified]
        f.write("## Verified Pyrefly False Negatives\n\n")
        f.write("_Pyright reports an error but Pyrefly does not. Only verified repros are shown._\n\n")
        if verified_fn_results:
            for i, result in enumerate(verified_fn_results, 1):
                rel_path = extract_relative_path_from_github_link(result.github_link)
                f.write(f"### {i}. {rel_path}:{result.error_group.line}\n\n")
                f.write(f"**GitHub:** [{rel_path}#L{result.error_group.line}]({result.github_link})\n\n")

                pyright_error = next((e for e in result.error_group.errors if e.checker == "pyright"), None)
                if pyright_error:
                    f.write(f"**Pyright error:** `{pyright_error.message}` [{pyright_error.error_code}]\n\n")

                if result.minimal_repro_path:
                    f.write(f"**Minimal Repro:** `{result.minimal_repro_path.name}`\n\n")

                f.write("**Source:**\n```python\n")
                f.write(result.source_context)
                f.write("\n```\n\n")
                f.write("---\n\n")
        else:
            f.write("_No verified false negatives._\n\n")


def update_markdown_status(report_path: Path, status: str) -> None:
    """Append a status update to the markdown file."""
    with open(report_path, "a", encoding="utf-8") as f:
        f.write(f"\n_Status: {status} ({datetime.now(timezone.utc).strftime('%H:%M:%S UTC')})_\n")


def run_batch_analysis(
    packages: list[dict[str, str]],
    output_dir: Path | None = None,
    timeout: int = 300,
) -> list[Path]:
    """Run type checker analysis on multiple packages, generating intermediate files.

    This function runs type checkers and generates intermediate JSON files with
    all false positives/negatives, but does NOT invoke Claude for repros.
    The intermediate files can later be analyzed together with analyze_cross_project.

    Args:
        packages: List of dicts with 'name' and 'github_url' keys
        output_dir: Directory to write intermediate files
        timeout: Timeout per type checker in seconds

    Returns:
        List of paths to intermediate files generated
    """
    if output_dir is None:
        output_dir = ROOT_DIR / "type_checker_benchmark" / "analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    intermediate_files: list[Path] = []
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    for i, pkg in enumerate(packages):
        package_name = pkg["name"]
        github_url = pkg["github_url"]
        print(f"\n[{i+1}/{len(packages)}] Processing {package_name}...")

        intermediate_file = output_dir / f"intermediate_{package_name}_{timestamp}.json"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Clone repository
            print(f"  Cloning {github_url}...")
            package_path = fetch_github_package(github_url, package_name, temp_path)

            if not package_path:
                print(f"  ERROR: Failed to clone repository")
                continue

            commit_sha = get_commit_sha(package_path)
            print(f"  Commit SHA: {commit_sha}")

            # Determine check path
            check_path = package_path
            if package_name == "django":
                django_src = package_path / "django"
                if django_src.exists():
                    check_path = django_src

            # Run only pyright and pyrefly (the two we compare)
            all_errors: dict[str, list[ParsedError]] = {}

            for checker in ["pyright", "pyrefly"]:
                if not is_type_checker_available(checker):
                    print(f"  Skipping {checker}: not installed")
                    continue

                print(f"  Running {checker}...")
                output, errors = run_checker_with_output(checker, package_path, check_path, timeout)
                all_errors[checker] = errors
                print(f"    Found {len(errors)} errors")

            # Group errors by location
            error_groups = group_errors_by_location(all_errors, package_name=package_name)

            # Find false positives and negatives
            false_positive_groups = [g for g in error_groups if g.is_pyrefly_false_positive]
            false_negative_groups = [g for g in error_groups if g.is_pyrefly_false_negative]

            print(f"  False positives: {len(false_positive_groups)}")
            print(f"  False negatives: {len(false_negative_groups)}")

            # Build intermediate data with augmented context
            intermediate_data = {
                "package_name": package_name,
                "github_url": github_url,
                "commit_sha": commit_sha,
                "summary": {
                    "pyright_errors": len(all_errors.get("pyright", [])),
                    "pyrefly_errors": len(all_errors.get("pyrefly", [])),
                    "false_positives": len(false_positive_groups),
                    "false_negatives": len(false_negative_groups),
                },
                "false_positives": [],
                "false_negatives": [],
            }

            # Add false positives with source context
            for group in false_positive_groups[:100]:  # Limit to 100 per package
                pyrefly_error = next((e for e in group.errors if e.checker == "pyrefly"), None)
                if pyrefly_error:
                    rel_file = group.file.replace(str(package_path) + "/", "")
                    source_context = get_source_context(package_path, rel_file, group.line, context_lines=3)

                    intermediate_data["false_positives"].append({
                        "file": rel_file,
                        "line": group.line,
                        "error_code": pyrefly_error.error_code,
                        "message": pyrefly_error.message,
                        "source_context": source_context,
                        "github_link": make_github_link(github_url, commit_sha, rel_file, group.line),
                    })

            # Add false negatives with source context
            for group in false_negative_groups[:100]:  # Limit to 100 per package
                pyright_error = next((e for e in group.errors if e.checker == "pyright"), None)
                if pyright_error:
                    rel_file = group.file.replace(str(package_path) + "/", "")
                    source_context = get_source_context(package_path, rel_file, group.line, context_lines=3)

                    intermediate_data["false_negatives"].append({
                        "file": rel_file,
                        "line": group.line,
                        "error_code": pyright_error.error_code,
                        "message": pyright_error.message,
                        "source_context": source_context,
                        "github_link": make_github_link(github_url, commit_sha, rel_file, group.line),
                    })

            # Write intermediate file
            with open(intermediate_file, "w", encoding="utf-8") as f:
                json.dump(intermediate_data, f, indent=2)

            print(f"  Wrote: {intermediate_file}")
            intermediate_files.append(intermediate_file)

    print(f"\nBatch analysis complete. Generated {len(intermediate_files)} intermediate files.")
    return intermediate_files


def analyze_cross_project(
    intermediate_files: list[Path],
    output_dir: Path | None = None,
    top_n: int = 10,
) -> Path:
    """Analyze intermediate files across projects to find top false positives.

    Calls Claude once with all intermediate data to find the most common/impactful
    false positive patterns across multiple projects.

    Args:
        intermediate_files: List of paths to intermediate JSON files
        output_dir: Directory to write the analysis report
        top_n: Number of top false positives to find

    Returns:
        Path to the generated analysis report
    """
    if output_dir is None:
        output_dir = ROOT_DIR / "type_checker_benchmark" / "analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load all intermediate files
    all_data: list[dict] = []
    for f in intermediate_files:
        if f.exists():
            with open(f, encoding="utf-8") as fp:
                all_data.append(json.load(fp))

    if not all_data:
        print("No intermediate files found to analyze")
        report_path = output_dir / f"cross_project_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(report_path, "w") as f:
            f.write("# Cross-Project Analysis\n\nNo data found.\n")
        return report_path

    # Build summary of all false positives grouped by error code
    error_code_summary: dict[str, list[dict]] = defaultdict(list)
    for pkg_data in all_data:
        package_name = pkg_data.get("package_name", "unknown")
        for fp in pkg_data.get("false_positives", []):
            error_code = fp.get("error_code", "unknown")
            error_code_summary[error_code].append({
                "package": package_name,
                "file": fp.get("file", ""),
                "line": fp.get("line", 0),
                "message": fp.get("message", ""),
                "source_context": fp.get("source_context", ""),
                "github_link": fp.get("github_link", ""),
            })

    # Sort by frequency
    sorted_codes = sorted(error_code_summary.items(), key=lambda x: len(x[1]), reverse=True)

    # Build prompt for Claude
    prompt_parts = [
        f"Analyze these pyrefly false positives across {len(all_data)} Python projects.",
        f"Find the top {top_n} most impactful false positive patterns that should be fixed.",
        "",
        "For each pattern, provide:",
        "1. The error code and a descriptive title",
        "2. Why this is a false positive (pyrefly reports error but pyright does not)",
        "3. The root cause in pyrefly",
        "4. One representative example with source code",
        "5. Recommended fix for pyrefly",
        "",
        "## Summary by Error Code",
        "",
    ]

    for code, examples in sorted_codes[:20]:  # Show top 20 for context
        prompt_parts.append(f"### {code} ({len(examples)} occurrences across projects)")
        # Show up to 3 examples per code
        for ex in examples[:3]:
            prompt_parts.append(f"**{ex['package']}**: {ex['file']}:{ex['line']}")
            prompt_parts.append(f"Message: {ex['message']}")
            prompt_parts.append(f"```python\n{ex['source_context']}\n```")
            prompt_parts.append(f"[GitHub]({ex['github_link']})")
            prompt_parts.append("")

    prompt = "\n".join(prompt_parts)

    # Write prompt to file for debugging
    prompt_file = output_dir / f"cross_project_prompt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"Wrote prompt to: {prompt_file}")

    # Call Claude CLI
    print(f"Calling Claude to analyze {len(all_data)} projects...")
    try:
        result = subprocess.run(
            ["claude", "--print"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes
        )
        claude_response = result.stdout if result.returncode == 0 else f"Error: {result.stderr}"
    except subprocess.TimeoutExpired:
        claude_response = "Error: Claude CLI timed out"
    except FileNotFoundError:
        claude_response = "Error: Claude CLI not found"
    except Exception as e:
        claude_response = f"Error: {e}"

    # Generate report
    report_path = output_dir / f"cross_project_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Cross-Project Pyrefly False Positive Analysis\n\n")
        f.write(f"**Generated:** {datetime.now(timezone.utc).isoformat()}\n\n")
        f.write(f"**Projects Analyzed:** {len(all_data)}\n\n")

        # Summary table
        f.write("## Summary\n\n")
        f.write("| Project | False Positives | False Negatives |\n")
        f.write("|---------|-----------------|----------------|\n")
        total_fp = 0
        total_fn = 0
        for pkg_data in all_data:
            fp_count = len(pkg_data.get("false_positives", []))
            fn_count = len(pkg_data.get("false_negatives", []))
            total_fp += fp_count
            total_fn += fn_count
            f.write(f"| {pkg_data.get('package_name', 'unknown')} | {fp_count} | {fn_count} |\n")
        f.write(f"| **Total** | **{total_fp}** | **{total_fn}** |\n\n")

        # Error code frequency
        f.write("## False Positive Error Codes by Frequency\n\n")
        f.write("| Error Code | Count | Packages |\n")
        f.write("|------------|-------|----------|\n")
        for code, examples in sorted_codes[:15]:
            packages = set(ex["package"] for ex in examples)
            f.write(f"| `{code}` | {len(examples)} | {', '.join(sorted(packages))} |\n")
        f.write("\n")

        # Claude's analysis
        f.write(f"## Top {top_n} False Positive Patterns\n\n")
        f.write(claude_response)
        f.write("\n")

    print(f"Wrote report: {report_path}")
    return report_path


def run_analysis(
    package_name: str,
    github_url: str,
    output_dir: Path | None = None,
    max_false_positives: int = 20,
    max_false_negatives: int = 20,
    timeout: int = 300,
    skip_claude: bool = False,
) -> Path:
    """Run the full error analysis on a package."""

    if output_dir is None:
        output_dir = ROOT_DIR / "type_checker_benchmark" / "analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / f"analysis_{package_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    # Initialize report
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Type Checker Error Analysis: {package_name}\n\n")
        f.write("_Analysis in progress..._\n\n")

    print(f"Analysis report: {report_path}")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Clone repository
        update_markdown_status(report_path, "Cloning repository...")
        print(f"Cloning {github_url}...")
        package_path = fetch_github_package(github_url, package_name, temp_path)

        if not package_path:
            update_markdown_status(report_path, "ERROR: Failed to clone repository")
            return report_path

        commit_sha = get_commit_sha(package_path)
        print(f"Commit SHA: {commit_sha}")

        # Determine check path (special handling for django)
        check_path = package_path
        if package_name == "django":
            django_src = package_path / "django"
            if django_src.exists():
                check_path = django_src

        # Run all type checkers
        all_errors: dict[str, list[ParsedError]] = {}
        raw_outputs: dict[str, str] = {}

        for checker in TYPE_CHECKERS:
            if not is_type_checker_available(checker):
                print(f"  Skipping {checker}: not installed")
                continue

            update_markdown_status(report_path, f"Running {checker}...")
            print(f"Running {checker}...")

            output, errors = run_checker_with_output(checker, package_path, check_path, timeout)
            raw_outputs[checker] = output
            all_errors[checker] = errors

            print(f"  Found {len(errors)} errors")

        # Save raw outputs
        raw_output_dir = output_dir / f"raw_{package_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        raw_output_dir.mkdir(parents=True, exist_ok=True)
        for checker, output in raw_outputs.items():
            with open(raw_output_dir / f"{checker}.txt", "w", encoding="utf-8") as f:
                f.write(output)

        # Group errors by location
        update_markdown_status(report_path, "Grouping errors by location...")
        print("Grouping errors by location...")
        error_groups = group_errors_by_location(all_errors, package_name=package_name)

        # Find false positives: pyrefly errors but NOT pyright (using pyright as source of truth)
        false_positive_groups = [g for g in error_groups if g.is_pyrefly_false_positive]
        print(f"Found {len(false_positive_groups)} potential false positives (pyrefly error, no pyright error)")

        # Find false negatives: pyright errors but NOT pyrefly (using pyright as source of truth)
        false_negative_groups = [g for g in error_groups if g.is_pyrefly_false_negative]
        print(f"Found {len(false_negative_groups)} potential false negatives (pyright error, no pyrefly error)")

        # Deduplicate by error code - only keep one example per unique error code
        def deduplicate_by_error_code(
            groups: list[ErrorGroup],
            checker: str,
        ) -> list[ErrorGroup]:
            """Keep only one error per unique error code to avoid duplicate repros."""
            seen_codes: set[str] = set()
            unique_groups: list[ErrorGroup] = []
            for group in groups:
                error = next((e for e in group.errors if e.checker == checker), None)
                if error:
                    code = error.error_code or "unknown"
                    if code not in seen_codes:
                        seen_codes.add(code)
                        unique_groups.append(group)
            return unique_groups

        # Deduplicate false positives by pyrefly error code
        unique_fp_groups = deduplicate_by_error_code(false_positive_groups, "pyrefly")
        print(f"  After deduplication: {len(unique_fp_groups)} unique error codes")

        # Deduplicate false negatives by pyright error code
        unique_fn_groups = deduplicate_by_error_code(false_negative_groups, "pyright")
        print(f"  After deduplication: {len(unique_fn_groups)} unique error codes")

        # Write intermediate file with all errors for debugging and Claude analysis
        intermediate_file = output_dir / f"intermediate_{package_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        intermediate_data = {
            "package_name": package_name,
            "github_url": github_url,
            "commit_sha": commit_sha,
            "false_positives": [],
            "false_negatives": [],
        }

        for group in false_positive_groups:
            pyrefly_error = next((e for e in group.errors if e.checker == "pyrefly"), None)
            if pyrefly_error:
                intermediate_data["false_positives"].append({
                    "file": group.file.replace(str(package_path) + "/", ""),
                    "line": group.line,
                    "error_code": pyrefly_error.error_code,
                    "message": pyrefly_error.message,
                })

        for group in false_negative_groups:
            pyright_error = next((e for e in group.errors if e.checker == "pyright"), None)
            if pyright_error:
                intermediate_data["false_negatives"].append({
                    "file": group.file.replace(str(package_path) + "/", ""),
                    "line": group.line,
                    "error_code": pyright_error.error_code,
                    "message": pyright_error.message,
                })

        with open(intermediate_file, "w", encoding="utf-8") as f:
            json.dump(intermediate_data, f, indent=2)
        print(f"\nWrote intermediate file: {intermediate_file}")

        # Create repro directory
        repro_dir = output_dir / f"repro_{package_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        repro_dir.mkdir(parents=True, exist_ok=True)

        # Track verified repros to avoid duplicates
        verified_repros: list[Path] = []

        # Analyze false positives with minimal reproductions
        false_positive_results: list[AnalysisResult] = []

        if skip_claude:
            # Skip Claude-based repro generation, just collect results
            print(f"\nCollecting {min(len(unique_fp_groups), max_false_positives)} unique false positives (skipping Claude)...")
            for i, group in enumerate(unique_fp_groups[:max_false_positives]):
                rel_file = group.file.replace(str(package_path) + "/", "")
                if package_name == "django" and not rel_file.startswith("django/"):
                    rel_file = f"django/{rel_file}"
                github_link = make_github_link(github_url, commit_sha, rel_file, group.line)
                source_context = get_source_context(package_path, group.file.replace(str(package_path) + "/", ""), group.line)
                false_positive_results.append(AnalysisResult(
                    error_group=group,
                    github_link=github_link,
                    source_context=source_context,
                ))
        else:
            # Use Claude to create minimal reproductions
            update_markdown_status(report_path, "Creating minimal reproductions for false positives with Claude...")
            print(f"\nCreating minimal reproductions for up to {max_false_positives} unique false positives...")

            for i, group in enumerate(unique_fp_groups[:max_false_positives]):
                print(f"  [{i+1}/{min(len(unique_fp_groups), max_false_positives)}] {group.file}:{group.line}")

                # Make relative path for GitHub link
                rel_file = group.file
                if rel_file.startswith(str(check_path)):
                    rel_file = rel_file[len(str(check_path)):].lstrip("/")
                elif rel_file.startswith(str(package_path)):
                    rel_file = rel_file[len(str(package_path)):].lstrip("/")

                # For django, prepend "django/" to the path
                if package_name == "django" and not rel_file.startswith("django/"):
                    rel_file = f"django/{rel_file}"

                github_link = make_github_link(github_url, commit_sha, rel_file, group.line)
                source_context = get_source_context(package_path, group.file.replace(str(package_path) + "/", ""), group.line)

                # Create minimal reproduction using Claude with LSP
                repro_name = f"fp_{i+1}_{Path(rel_file).stem}_{group.line}"
                repro_path, repro_verified = create_minimal_repro_with_claude(
                    package_path,
                    group.file.replace(str(package_path) + "/", ""),
                    group.line,
                    repro_dir,
                    repro_name,
                    group,
                    is_false_positive=True,
                    intermediate_file=intermediate_file,
                    verified_repros=verified_repros,
                )

                if repro_verified and repro_path:
                    print(f"    VERIFIED repro created: {repro_name}.py")
                    verified_repros.append(repro_path)
                else:
                    print(f"    Could not create verified repro")

                false_positive_results.append(AnalysisResult(
                    error_group=group,
                    github_link=github_link,
                    source_context=source_context,
                    minimal_repro_path=repro_path,
                    repro_verified=repro_verified,
                ))

        # Analyze false negatives with minimal reproductions
        false_negative_results: list[AnalysisResult] = []

        if skip_claude:
            # Skip Claude-based repro generation, just collect results
            print(f"\nCollecting {min(len(unique_fn_groups), max_false_negatives)} unique false negatives (skipping Claude)...")
            for i, group in enumerate(unique_fn_groups[:max_false_negatives]):
                rel_file = group.file.replace(str(package_path) + "/", "")
                if package_name == "django" and not rel_file.startswith("django/"):
                    rel_file = f"django/{rel_file}"
                github_link = make_github_link(github_url, commit_sha, rel_file, group.line)
                source_context = get_source_context(package_path, group.file.replace(str(package_path) + "/", ""), group.line)
                false_negative_results.append(AnalysisResult(
                    error_group=group,
                    github_link=github_link,
                    source_context=source_context,
                ))
        else:
            # Use Claude to create minimal reproductions
            update_markdown_status(report_path, "Creating minimal reproductions for false negatives with Claude...")
            print(f"\nCreating minimal reproductions for up to {max_false_negatives} unique false negatives...")

            for i, group in enumerate(unique_fn_groups[:max_false_negatives]):
                print(f"  [{i+1}/{min(len(unique_fn_groups), max_false_negatives)}] {group.file}:{group.line}")

                rel_file = group.file
                if rel_file.startswith(str(check_path)):
                    rel_file = rel_file[len(str(check_path)):].lstrip("/")
                elif rel_file.startswith(str(package_path)):
                    rel_file = rel_file[len(str(package_path)):].lstrip("/")

                if package_name == "django" and not rel_file.startswith("django/"):
                    rel_file = f"django/{rel_file}"

                github_link = make_github_link(github_url, commit_sha, rel_file, group.line)
                source_context = get_source_context(package_path, group.file.replace(str(package_path) + "/", ""), group.line)

                # Create minimal reproduction using Claude with LSP
                repro_name = f"fn_{i+1}_{Path(rel_file).stem}_{group.line}"
                repro_path, repro_verified = create_minimal_repro_with_claude(
                    package_path,
                    group.file.replace(str(package_path) + "/", ""),
                    group.line,
                    repro_dir,
                    repro_name,
                    group,
                    is_false_positive=False,
                    intermediate_file=intermediate_file,
                    verified_repros=verified_repros,
                )

                if repro_verified and repro_path:
                    print(f"    VERIFIED repro created: {repro_name}.py")
                    verified_repros.append(repro_path)
                else:
                    print(f"    Could not create verified repro")

                false_negative_results.append(AnalysisResult(
                    error_group=group,
                    github_link=github_link,
                    source_context=source_context,
                    minimal_repro_path=repro_path,
                    repro_verified=repro_verified,
                ))

        # Write final report
        update_markdown_status(report_path, "Writing final report...")
        print("\nWriting final report...")
        write_markdown_report(
            report_path,
            package_name,
            github_url,
            commit_sha,
            all_errors,
            error_groups,
            false_positive_results,
            false_negative_results,
        )

        print(f"\nAnalysis complete! Report: {report_path}")
        print(f"Raw outputs: {raw_output_dir}")
        print(f"Reproductions: {repro_dir}")

    return report_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze type checker errors and find pyrefly discrepancies"
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--batch",
        type=int,
        metavar="N",
        help="Run batch analysis on N packages from benchmark_packages.json (no Claude)",
    )
    mode_group.add_argument(
        "--analyze-cross",
        nargs="+",
        type=Path,
        metavar="FILE",
        help="Analyze intermediate files from batch analysis with Claude",
    )

    # Single package mode options
    parser.add_argument(
        "--package",
        "-p",
        type=str,
        help="Package name to analyze (single package mode)",
    )
    parser.add_argument(
        "--github-url",
        "-g",
        type=str,
        help="GitHub URL of the package (single package mode)",
    )
    parser.add_argument(
        "--max-false-positives",
        type=int,
        default=20,
        help="Maximum number of false positives to analyze (default: 20)",
    )
    parser.add_argument(
        "--max-false-negatives",
        type=int,
        default=20,
        help="Maximum number of false negatives to analyze (default: 20)",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        type=int,
        default=300,
        help="Timeout per type checker in seconds (default: 300)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output directory for analysis results",
    )
    parser.add_argument(
        "--skip-claude",
        action="store_true",
        help="Skip Claude-based repro generation (single package mode)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Number of top false positives to find in cross-project analysis (default: 10)",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    # Batch mode: run on N packages from benchmark_packages.json
    if args.batch:
        packages_file = ROOT_DIR / "type_checker_benchmark" / "benchmark_packages.json"
        if not packages_file.exists():
            print(f"ERROR: {packages_file} not found")
            return 1

        with open(packages_file, encoding="utf-8") as f:
            data = json.load(f)

        packages = [
            {"name": p["name"], "github_url": p["github_url"]}
            for p in data["packages"][:args.batch]
        ]

        print(f"Running batch analysis on {len(packages)} packages...")
        intermediate_files = run_batch_analysis(
            packages=packages,
            output_dir=args.output,
            timeout=args.timeout,
        )

        # After batch, run cross-project analysis
        if intermediate_files:
            print("\nRunning cross-project analysis...")
            analyze_cross_project(
                intermediate_files=intermediate_files,
                output_dir=args.output,
                top_n=args.top_n,
            )

        return 0

    # Cross-project analysis mode
    if args.analyze_cross:
        print(f"Analyzing {len(args.analyze_cross)} intermediate files...")
        analyze_cross_project(
            intermediate_files=args.analyze_cross,
            output_dir=args.output,
            top_n=args.top_n,
        )
        return 0

    # Single package mode
    if not args.package or not args.github_url:
        print("ERROR: --package and --github-url required for single package mode")
        print("       Or use --batch N to run on N packages from benchmark_packages.json")
        return 1

    run_analysis(
        package_name=args.package,
        github_url=args.github_url,
        output_dir=args.output,
        max_false_positives=args.max_false_positives,
        max_false_negatives=args.max_false_negatives,
        timeout=args.timeout,
        skip_claude=args.skip_claude,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
