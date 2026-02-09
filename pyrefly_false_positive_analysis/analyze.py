#!/usr/bin/env python3
"""
Pyrefly False Positive Analysis Tool

This tool:
1. Runs pyright and pyrefly on multiple Python packages
2. Identifies false positives (pyrefly error, no pyright error)
3. Uses Claude CLI to create minimal standalone reproductions
4. Generates sandbox URLs for easy verification
5. Produces a summary markdown report

Usage:
    # Analyze 10 packages from the default list
    python analyze.py --batch 10

    # Analyze specific packages
    python analyze.py --packages requests flask django

    # Re-run cross-project analysis on existing intermediate files
    python analyze.py --analyze-cross output/intermediate_*.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sandbox_links import generate_pyrefly_link, generate_pyright_link

# Package list file
PACKAGES_FILE = Path(__file__).parent / "packages.json"


def load_packages() -> list[dict[str, str]]:
    """Load packages from packages.json."""
    if not PACKAGES_FILE.exists():
        print(f"ERROR: {PACKAGES_FILE} not found. Run merge_packages.py first.")
        return []
    with open(PACKAGES_FILE) as f:
        data = json.load(f)
    return [
        {"name": p["name"], "github_url": p["github_url"]}
        for p in data.get("packages", [])
    ]

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
    severity: str = "error"

    def location_key(self) -> str:
        return f"{self.file}:{self.line}"


@dataclass
class ErrorGroup:
    """A group of errors at the same location from different checkers."""
    file: str
    line: int
    errors: list[ParsedError] = field(default_factory=list)

    @property
    def checkers_with_errors(self) -> set[str]:
        return {e.checker for e in self.errors}

    @property
    def is_pyrefly_false_positive(self) -> bool:
        """Pyrefly reports error but pyright does NOT."""
        return "pyrefly" in self.checkers_with_errors and "pyright" not in self.checkers_with_errors


@dataclass
class VerifiedRepro:
    """A verified reproduction of a false positive."""
    package: str
    error_code: str
    message: str
    original_file: str
    original_line: int
    github_link: str
    repro_code: str
    repro_path: Path
    pyrefly_url: str
    pyright_url: str


def is_type_checker_available(checker: str) -> bool:
    """Check if a type checker is available."""
    try:
        if checker == "pyright":
            result = subprocess.run(["pyright", "--version"], capture_output=True, timeout=10)
        elif checker == "pyrefly":
            result = subprocess.run(["pyrefly", "--version"], capture_output=True, timeout=10)
        else:
            return False
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def fetch_github_package(github_url: str, package_name: str, dest_dir: Path) -> Path | None:
    """Clone a GitHub repository."""
    package_path = dest_dir / package_name
    try:
        result = subprocess.run(
            ["git", "clone", "--depth=1", github_url, str(package_path)],
            capture_output=True,
            timeout=120,
        )
        if result.returncode == 0 and package_path.exists():
            return package_path
    except subprocess.TimeoutExpired:
        pass
    return None


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
    base_url = github_url.rstrip("/")
    return f"{base_url}/blob/{commit_sha}/{file_path}#L{line}"


def parse_pyright_errors(output: str) -> list[ParsedError]:
    """Parse pyright JSON output."""
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
                line=start.get("line", 0) + 1,
                column=start.get("character", 0) + 1,
                error_code=diag.get("rule", "unknown"),
                message=diag.get("message", ""),
                checker="pyright",
                severity=severity,
            ))
    except json.JSONDecodeError:
        pass
    return errors


def parse_pyrefly_errors(output: str) -> list[ParsedError]:
    """Parse pyrefly output."""
    errors = []
    lines = output.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        error_match = re.match(r'^(ERROR|WARNING)\s+(.+?)(?:\s*\[([^\]]+)\])?\s*$', line)
        if error_match:
            severity = error_match.group(1).lower()
            message = error_match.group(2).strip()
            error_code = error_match.group(3) or "unknown"
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith('|'):
                j += 1
            if j < len(lines):
                loc_line = lines[j].strip()
                loc_match = re.match(r'^-->\s*(.+?):(\d+):(\d+)', loc_line)
                if loc_match:
                    errors.append(ParsedError(
                        file=loc_match.group(1),
                        line=int(loc_match.group(2)),
                        column=int(loc_match.group(3)),
                        error_code=error_code,
                        message=message,
                        checker="pyrefly",
                        severity=severity,
                    ))
                    i = j
        i += 1
    return errors


def run_checker(checker: str, package_path: Path, check_path: Path, timeout: int) -> list[ParsedError]:
    """Run a type checker and return parsed errors."""
    try:
        if checker == "pyright":
            result = subprocess.run(
                ["pyright", "--outputjson", str(check_path)],
                cwd=package_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return parse_pyright_errors(result.stdout)
        elif checker == "pyrefly":
            result = subprocess.run(
                ["pyrefly", "check", str(check_path)],
                cwd=check_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return parse_pyrefly_errors(result.stdout + result.stderr)
    except subprocess.TimeoutExpired:
        pass
    return []


def normalize_file_path(file_path: str, package_name: str = "") -> str:
    """Normalize a file path for comparison."""
    if not file_path.startswith("/"):
        if package_name and file_path.startswith(f"{package_name}/"):
            return file_path[len(package_name) + 1:]
        return file_path
    parts = file_path.split("/")
    if package_name:
        last_pkg_idx = -1
        for i, part in enumerate(parts):
            if part == package_name:
                last_pkg_idx = i
        if last_pkg_idx >= 0:
            return "/".join(parts[last_pkg_idx + 1:])
    if len(parts) > 4:
        return "/".join(parts[-4:])
    return file_path


def group_errors_by_location(
    all_errors: dict[str, list[ParsedError]],
    package_name: str = "",
) -> list[ErrorGroup]:
    """Group errors from all checkers by location."""
    location_to_group: dict[str, ErrorGroup] = {}
    group_normalized_paths: dict[str, str] = {}

    for checker, errors in all_errors.items():
        for error in errors:
            normalized_file = normalize_file_path(error.file, package_name)
            key = f"{normalized_file}:{error.line}"
            matched_group = None
            for existing_key, group in location_to_group.items():
                existing_normalized = group_normalized_paths[existing_key]
                existing_line = int(existing_key.rsplit(":", 1)[1])
                if normalized_file == existing_normalized and abs(error.line - existing_line) <= LINE_TOLERANCE:
                    matched_group = group
                    break
            if matched_group:
                matched_group.errors.append(error)
            else:
                location_to_group[key] = ErrorGroup(file=error.file, line=error.line, errors=[error])
                group_normalized_paths[key] = normalized_file

    return list(location_to_group.values())


def get_source_context(package_path: Path, file_path: str, line: int, context_lines: int = 3) -> str:
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


def run_checker_on_file(checker: str, file_path: Path) -> tuple[bool, str]:
    """Run a type checker on a single file."""
    try:
        if checker == "pyright":
            result = subprocess.run(
                ["pyright", str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            has_errors = result.returncode != 0
            output = result.stdout + result.stderr
        elif checker == "pyrefly":
            result = subprocess.run(
                ["pyrefly", "check", str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            has_errors = "0 errors" not in result.stdout and "0 errors" not in result.stderr
            output = result.stdout + result.stderr
        else:
            return False, f"Unknown checker: {checker}"
        return has_errors, output
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except FileNotFoundError:
        return False, f"{checker} not found"


def verify_repro(repro_path: Path) -> tuple[bool, bool, bool]:
    """Verify a repro shows pyrefly error but no pyright error.

    Returns: (pyrefly_has_error, pyright_has_error, is_valid_false_positive)
    """
    pyrefly_has_error, _ = run_checker_on_file("pyrefly", repro_path)
    pyright_has_error, _ = run_checker_on_file("pyright", repro_path)
    is_valid = pyrefly_has_error and not pyright_has_error
    return pyrefly_has_error, pyright_has_error, is_valid


def create_repro_with_claude(
    package_path: Path,
    file_path: str,
    error_line: int,
    repro_dir: Path,
    repro_name: str,
    error_code: str,
    error_message: str,
) -> tuple[Path | None, bool]:
    """Create a minimal reproduction using Claude CLI."""
    full_path = package_path / file_path
    if not full_path.exists():
        return None, False

    repro_path = repro_dir / f"{repro_name}.py"

    prompt = f'''Create a minimal, self-contained Python file that reproduces a pyrefly false positive.

SOURCE FILE: {full_path}
ERROR LINE: {error_line}
PYREFLY ERROR: {error_message} [{error_code}]

EXPECTATION: The file should cause pyrefly to report an error, but pyright should report NO error.

INSTRUCTIONS:
1. Read the source file to understand the code context around line {error_line}.

2. Use the LSP tool to get type information:
   - Call LSP hover on line {error_line} to get types of symbols involved
   - Call LSP goToDefinition to find type definitions being used

3. Create a MINIMAL repro file that:
   - Has ONLY `from typing import ...` - NO other imports allowed
   - NO `import sys`, NO `from __future__ import`, NO `import abc`, etc.
   - Synthesizes stub classes/types that match actual type signatures from LSP
   - Is as SHORT as possible while reproducing the issue
   - Must be FULLY ISOLATED - runnable with zero dependencies

4. Write the repro to: {repro_path}

5. Verify by running both type checkers:
   - Run: pyright {repro_path}
   - Run: pyrefly check {repro_path}
   Confirm that pyrefly reports an error but pyright does NOT.

6. If verification fails, iterate until it works or respond with CANNOT_REPRODUCE.

IMPORTANT: Respond with CANNOT_REPRODUCE if you cannot create a verified repro.
'''

    try:
        result = subprocess.run(
            ["claude", "--print", "--add-dir", str(package_path)],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=180,
        )

        if "CANNOT_REPRODUCE" in result.stdout or "CANNOT_REPRODUCE" in result.stderr:
            return None, False

        if not repro_path.exists():
            return None, False

        pyrefly_err, pyright_err, verified = verify_repro(repro_path)
        if verified:
            return repro_path, True
        else:
            repro_path.unlink(missing_ok=True)
            return None, False

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None, False


def run_batch_analysis(
    packages: list[dict[str, str]],
    output_dir: Path,
    timeout: int = 300,
) -> list[Path]:
    """Run type checker analysis on multiple packages."""
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
            print(f"  Cloning {github_url}...")
            package_path = fetch_github_package(github_url, package_name, temp_path)

            if not package_path:
                print(f"  ERROR: Failed to clone repository")
                continue

            commit_sha = get_commit_sha(package_path)
            check_path = package_path
            if package_name == "django":
                django_src = package_path / "django"
                if django_src.exists():
                    check_path = django_src

            all_errors: dict[str, list[ParsedError]] = {}
            for checker in ["pyright", "pyrefly"]:
                if not is_type_checker_available(checker):
                    print(f"  Skipping {checker}: not installed")
                    continue
                print(f"  Running {checker}...")
                errors = run_checker(checker, package_path, check_path, timeout)
                all_errors[checker] = errors
                print(f"    Found {len(errors)} errors")

            error_groups = group_errors_by_location(all_errors, package_name=package_name)
            false_positive_groups = [g for g in error_groups if g.is_pyrefly_false_positive]
            print(f"  False positives: {len(false_positive_groups)}")

            intermediate_data = {
                "package_name": package_name,
                "github_url": github_url,
                "commit_sha": commit_sha,
                "summary": {
                    "pyright_errors": len(all_errors.get("pyright", [])),
                    "pyrefly_errors": len(all_errors.get("pyrefly", [])),
                    "false_positives": len(false_positive_groups),
                },
                "false_positives": [],
            }

            for group in false_positive_groups[:100]:
                pyrefly_error = next((e for e in group.errors if e.checker == "pyrefly"), None)
                if pyrefly_error:
                    rel_file = group.file.replace(str(package_path) + "/", "")
                    source_context = get_source_context(package_path, rel_file, group.line)
                    intermediate_data["false_positives"].append({
                        "file": rel_file,
                        "line": group.line,
                        "error_code": pyrefly_error.error_code,
                        "message": pyrefly_error.message,
                        "source_context": source_context,
                        "github_link": make_github_link(github_url, commit_sha, rel_file, group.line),
                    })

            with open(intermediate_file, "w", encoding="utf-8") as f:
                json.dump(intermediate_data, f, indent=2)
            intermediate_files.append(intermediate_file)

    return intermediate_files


def analyze_and_create_repros(
    intermediate_files: list[Path],
    output_dir: Path,
    max_repros_per_code: int = 3,
    top_n: int = 10,
) -> Path:
    """Analyze intermediate files and create verified repros with sandbox URLs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    repro_dir = output_dir / "repros"
    repro_dir.mkdir(parents=True, exist_ok=True)

    # Load all intermediate files
    all_data: list[dict] = []
    for f in intermediate_files:
        if f.exists():
            with open(f, encoding="utf-8") as fp:
                all_data.append(json.load(fp))

    if not all_data:
        print("No intermediate files found")
        report_path = output_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(report_path, "w") as f:
            f.write("# Pyrefly False Positive Analysis\n\nNo data found.\n")
        return report_path

    # Group by error code
    error_code_summary: dict[str, list[dict]] = defaultdict(list)
    for pkg_data in all_data:
        package_name = pkg_data.get("package_name", "unknown")
        github_url = pkg_data.get("github_url", "")
        commit_sha = pkg_data.get("commit_sha", "main")
        for fp in pkg_data.get("false_positives", []):
            error_code = fp.get("error_code", "unknown")
            error_code_summary[error_code].append({
                "package": package_name,
                "github_url": github_url,
                "commit_sha": commit_sha,
                **fp,
            })

    sorted_codes = sorted(error_code_summary.items(), key=lambda x: len(x[1]), reverse=True)

    # Create repros for top error codes
    verified_repros: list[VerifiedRepro] = []
    repro_count = 0

    print(f"\nCreating verified reproductions for top {top_n} error codes...")

    for error_code, examples in sorted_codes[:top_n]:
        print(f"\n  [{error_code}] ({len(examples)} occurrences)")
        code_repros = 0

        for ex in examples:
            if code_repros >= max_repros_per_code:
                break

            package_name = ex["package"]
            github_url = ex["github_url"]
            commit_sha = ex["commit_sha"]
            file_path = ex["file"]
            line = ex["line"]
            message = ex["message"]

            print(f"    Trying {package_name}/{file_path}:{line}...")

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                package_path = fetch_github_package(github_url, package_name, temp_path)
                if not package_path:
                    continue

                repro_name = f"{error_code}_{package_name}_{repro_count}"
                repro_path, verified = create_repro_with_claude(
                    package_path, file_path, line, repro_dir, repro_name, error_code, message
                )

                if verified and repro_path:
                    with open(repro_path, encoding="utf-8") as f:
                        repro_code = f.read()

                    pyrefly_url = generate_pyrefly_link(repro_code)
                    pyright_url = generate_pyright_link(repro_code)

                    verified_repros.append(VerifiedRepro(
                        package=package_name,
                        error_code=error_code,
                        message=message,
                        original_file=file_path,
                        original_line=line,
                        github_link=make_github_link(github_url, commit_sha, file_path, line),
                        repro_code=repro_code,
                        repro_path=repro_path,
                        pyrefly_url=pyrefly_url,
                        pyright_url=pyright_url,
                    ))
                    code_repros += 1
                    repro_count += 1
                    print(f"      VERIFIED: {repro_path.name}")

    # Generate report
    report_path = output_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Pyrefly False Positive Analysis\n\n")
        f.write(f"**Generated:** {datetime.now(timezone.utc).isoformat()}\n\n")
        f.write(f"**Projects Analyzed:** {len(all_data)}\n\n")
        f.write(f"**Verified Reproductions:** {len(verified_repros)}\n\n")

        # Summary table
        f.write("## Summary by Project\n\n")
        f.write("| Project | False Positives |\n")
        f.write("|---------|----------------|\n")
        total_fp = 0
        for pkg_data in all_data:
            fp_count = len(pkg_data.get("false_positives", []))
            total_fp += fp_count
            f.write(f"| {pkg_data.get('package_name', 'unknown')} | {fp_count} |\n")
        f.write(f"| **Total** | **{total_fp}** |\n\n")

        # Error code frequency
        f.write("## False Positive Error Codes by Frequency\n\n")
        f.write("| Error Code | Count | Packages |\n")
        f.write("|------------|-------|----------|\n")
        for code, examples in sorted_codes[:15]:
            packages = set(ex["package"] for ex in examples)
            f.write(f"| `{code}` | {len(examples)} | {', '.join(sorted(packages))} |\n")
        f.write("\n")

        # Verified reproductions
        f.write("## Verified Reproductions\n\n")
        f.write("Each reproduction below demonstrates a pyrefly false positive.\n")
        f.write("Click the sandbox links to verify in your browser.\n\n")

        for i, repro in enumerate(verified_repros, 1):
            f.write(f"### {i}. `{repro.error_code}` in {repro.package}\n\n")
            f.write(f"**Original:** [{repro.original_file}:{repro.original_line}]({repro.github_link})\n\n")
            f.write(f"**Error:** {repro.message}\n\n")
            f.write(f"**Sandbox Links:**\n")
            f.write(f"- [Pyrefly (shows error)]({repro.pyrefly_url})\n")
            f.write(f"- [Pyright (no error)]({repro.pyright_url})\n\n")
            f.write(f"**Reproduction:** `{repro.repro_path.name}`\n")
            f.write("```python\n")
            f.write(repro.repro_code)
            f.write("\n```\n\n")
            f.write("---\n\n")

    print(f"\nReport written to: {report_path}")
    print(f"Reproductions written to: {repro_dir}")
    return report_path


def main():
    parser = argparse.ArgumentParser(
        description="Analyze pyrefly false positives across Python packages"
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--batch", type=int, metavar="N",
        help="Run batch analysis on N packages from default list"
    )
    mode_group.add_argument(
        "--packages", nargs="+", metavar="NAME",
        help="Analyze specific packages by name"
    )
    mode_group.add_argument(
        "--analyze-cross", nargs="+", type=Path, metavar="FILE",
        help="Analyze existing intermediate files"
    )

    parser.add_argument(
        "--output", "-o", type=Path, default=Path("output"),
        help="Output directory (default: output)"
    )
    parser.add_argument(
        "--timeout", "-t", type=int, default=300,
        help="Timeout per type checker in seconds (default: 300)"
    )
    parser.add_argument(
        "--top-n", type=int, default=10,
        help="Number of top error codes to create repros for (default: 10)"
    )
    parser.add_argument(
        "--max-repros-per-code", type=int, default=3,
        help="Max repros per error code (default: 3)"
    )

    args = parser.parse_args()

    # Verify type checkers are available
    for checker in ["pyright", "pyrefly"]:
        if not is_type_checker_available(checker):
            print(f"ERROR: {checker} not found. Please install it first.")
            return 1

    # Load packages from JSON
    all_packages = load_packages()
    if not all_packages:
        return 1

    if args.batch:
        packages = all_packages[:args.batch]
        print(f"Running batch analysis on {len(packages)} packages...")
        intermediate_files = run_batch_analysis(packages, args.output, args.timeout)
        if intermediate_files:
            print("\nCreating verified reproductions...")
            analyze_and_create_repros(
                intermediate_files, args.output, args.max_repros_per_code, args.top_n
            )
        return 0

    if args.packages:
        packages = [
            p for p in all_packages
            if p["name"] in args.packages
        ]
        if not packages:
            print(f"ERROR: No matching packages found. Available: {[p['name'] for p in all_packages]}")
            return 1
        print(f"Running analysis on {len(packages)} packages...")
        intermediate_files = run_batch_analysis(packages, args.output, args.timeout)
        if intermediate_files:
            print("\nCreating verified reproductions...")
            analyze_and_create_repros(
                intermediate_files, args.output, args.max_repros_per_code, args.top_n
            )
        return 0

    if args.analyze_cross:
        print(f"Analyzing {len(args.analyze_cross)} intermediate files...")
        analyze_and_create_repros(
            args.analyze_cross, args.output, args.max_repros_per_code, args.top_n
        )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
