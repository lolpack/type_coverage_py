#!/usr/bin/env python3
"""Daily runner for type checker error benchmarks.

This script:
1. Loads packages from the prioritized package report
2. Clones each package from GitHub
3. Runs type checkers (pyright, pyrefly, ty, mypy, zuban) on each package
4. Counts errors reported by each type checker
5. Saves results to JSON for the web dashboard
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

# Add parent directories to path for imports
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Default type checkers to benchmark
DEFAULT_TYPE_CHECKERS: list[str] = ["pyright", "pyrefly", "ty", "mypy", "zuban"]

# Default timeouts (in seconds)
DEFAULT_TIMEOUT = 300  # 5 minutes for most checkers
SLOW_CHECKER_TIMEOUT = 300  # 5 minutes for pyright and mypy


class ErrorMetrics(TypedDict, total=False):
    """Error metrics for a type checker run."""

    ok: bool
    error_count: int
    warning_count: int
    info_count: int
    files_checked: int
    execution_time_s: float
    error_message: str | None


class PackageResult(TypedDict, total=False):
    """Result of type checking a single package."""

    package_name: str
    github_url: str | None
    ranking: int | None
    error: str | None
    metrics: dict[str, ErrorMetrics]
    has_py_typed: bool
    configured_checkers: dict[str, bool]


class AggregateStats(TypedDict, total=False):
    """Aggregate statistics for a type checker."""

    packages_tested: int
    total_errors: int
    total_warnings: int
    avg_errors_per_package: float
    p95_errors: int
    min_errors: int
    max_errors: int
    avg_execution_time_s: float
    p95_execution_time_s: float


class BenchmarkOutput(TypedDict):
    """Complete benchmark output structure."""

    timestamp: str
    date: str
    type_checkers: list[str]
    type_checker_versions: dict[str, str]
    package_count: int
    aggregate: dict[str, AggregateStats]
    results: list[PackageResult]


class PackageInfo(TypedDict, total=False):
    """Package information from the benchmark list."""

    name: str
    github_url: str | None
    download_count: int
    ranking: int
    has_py_typed: bool
    configured_checkers: dict[str, bool]  # Which type checkers are configured


class ProcessResult(TypedDict):
    """Result from running a subprocess with timeout."""

    stdout: str
    stderr: str
    returncode: int
    timed_out: bool
    execution_time_s: float


def run_process_with_timeout(
    cmd: list[str],
    cwd: Path,
    timeout: int,
) -> ProcessResult:
    """Run a process synchronously with proper timeout and cleanup.

    This function ensures the process and all its children are properly
    terminated if a timeout occurs.

    Args:
        cmd: Command and arguments to run.
        cwd: Working directory for the process.
        timeout: Timeout in seconds.

    Returns:
        ProcessResult with stdout, stderr, returncode, and timing info.
    """
    start_time = time.time()

    # Use start_new_session on Unix to create a new process group
    # This allows us to kill the entire process tree on timeout
    kwargs: dict[str, Any] = {
        "cwd": cwd,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }

    if sys.platform != "win32":
        kwargs["start_new_session"] = True

    process = subprocess.Popen(cmd, **kwargs)

    try:
        stdout, stderr = process.communicate(timeout=timeout)
        execution_time = time.time() - start_time
        return {
            "stdout": stdout or "",
            "stderr": stderr or "",
            "returncode": process.returncode,
            "timed_out": False,
            "execution_time_s": round(execution_time, 2),
        }
    except subprocess.TimeoutExpired:
        execution_time = time.time() - start_time
        # Kill the process group (all children) on Unix
        if sys.platform != "win32":
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
        else:
            process.kill()

        # Wait for process to fully terminate
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

        return {
            "stdout": "",
            "stderr": "",
            "returncode": -1,
            "timed_out": True,
            "execution_time_s": round(execution_time, 2),
        }


def get_type_checker_versions() -> dict[str, str]:
    """Get version strings for all type checkers.

    Returns:
        Dictionary mapping type checker names to version strings.
    """
    versions: dict[str, str] = {}

    version_commands = {
        "pyright": ["pyright", "--version"],
        "pyrefly": ["pyrefly", "--version"],
        "ty": ["ty", "--version"],
        "mypy": ["python -m mypy", "--version"],
        "zuban": ["zuban", "--version"],
    }

    for name, cmd in version_commands.items():
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = result.stdout.strip() or result.stderr.strip()
            if output:
                # Try to find a semver-like pattern (e.g., 1.2.3, 0.0.4)
                match = re.search(r"\d+\.\d+\.\d+", output)
                if match:
                    versions[name] = match.group(0)
                else:
                    # Fallback: take the second word (after the name)
                    parts = output.split()
                    version = parts[1] if len(parts) > 1 else parts[0] if parts else "unknown"
                    versions[name] = version
            else:
                versions[name] = "unknown"
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            versions[name] = "not installed"

    return versions


def load_benchmark_packages(
    limit: int | None = None,
    packages_file: Path | None = None,
) -> list[PackageInfo]:
    """Load packages from the benchmark package JSON file.

    Args:
        limit: Maximum number of packages to return.
        packages_file: Path to the benchmark packages JSON file.

    Returns:
        List of package information dictionaries.
    """
    if packages_file is None:
        packages_file = ROOT_DIR / "type_checker_benchmark" / "benchmark_packages.json"

    if not packages_file.exists():
        print(f"Warning: {packages_file} not found, using fallback packages")
        fallback = get_fallback_packages()
        return fallback[:limit] if limit else fallback

    with open(packages_file, encoding="utf-8") as f:
        data = json.load(f)

    packages: list[PackageInfo] = []
    for i, pkg in enumerate(data.get("packages", []), 1):
        github_url = pkg.get("github_url")
        if not github_url:
            print(f"Warning: No GitHub URL for {pkg['name']}, skipping")
            continue

        # Extract configured checkers
        configured_checkers = {}
        for checker, info in pkg.get("type_checkers", {}).items():
            configured_checkers[checker] = info.get("detected", False)

        packages.append(
            {
                "name": pkg["name"],
                "github_url": github_url,
                "download_count": 0,
                "ranking": i,
                "has_py_typed": pkg.get("has_py_typed", False),
                "configured_checkers": configured_checkers,
            }
        )

    if limit:
        packages = packages[:limit]

    return packages


def load_prioritized_packages(
    limit: int | None = None,
    packages_file: Path | None = None,
) -> list[PackageInfo]:
    """Load packages from the prioritized package report.

    Args:
        limit: Maximum number of packages to return.
        packages_file: Path to the package report JSON file.

    Returns:
        List of package information dictionaries.
    """
    if packages_file is None:
        packages_file = ROOT_DIR / "prioritized" / "package_report.json"

    if not packages_file.exists():
        print(f"Warning: {packages_file} not found, using fallback packages")
        fallback = get_fallback_packages()
        return fallback[:limit] if limit else fallback

    with open(packages_file, encoding="utf-8") as f:
        package_data: dict[str, Any] = json.load(f)

    packages: list[PackageInfo] = []
    for name, data in package_data.items():
        github_url = resolve_github_url(name, data)
        if github_url:
            packages.append(
                {
                    "name": name,
                    "github_url": github_url,
                    "download_count": data.get("DownloadCount", 0),
                    "ranking": data.get("DownloadRanking", 999),
                }
            )

    packages.sort(key=lambda x: x.get("ranking", 999))

    if limit:
        packages = packages[:limit]

    return packages


def get_fallback_packages() -> list[PackageInfo]:
    """Get fallback list of popular packages with GitHub URLs.

    Returns:
        List of package information for well-known packages.
    """
    return [
        {"name": "requests", "github_url": "https://github.com/psf/requests", "ranking": 1, "download_count": 0},
        {"name": "flask", "github_url": "https://github.com/pallets/flask", "ranking": 2, "download_count": 0},
        {"name": "django", "github_url": "https://github.com/django/django", "ranking": 3, "download_count": 0},
        {"name": "fastapi", "github_url": "https://github.com/fastapi/fastapi", "ranking": 4, "download_count": 0},
        {"name": "pydantic", "github_url": "https://github.com/pydantic/pydantic", "ranking": 5, "download_count": 0},
        {"name": "numpy", "github_url": "https://github.com/numpy/numpy", "ranking": 6, "download_count": 0},
        {"name": "pandas", "github_url": "https://github.com/pandas-dev/pandas", "ranking": 7, "download_count": 0},
        {"name": "click", "github_url": "https://github.com/pallets/click", "ranking": 8, "download_count": 0},
        {"name": "httpx", "github_url": "https://github.com/encode/httpx", "ranking": 9, "download_count": 0},
        {"name": "aiohttp", "github_url": "https://github.com/aio-libs/aiohttp", "ranking": 10, "download_count": 0},
    ]


def resolve_github_url(package_name: str, package_data: dict[str, Any]) -> str | None:
    """Resolve GitHub URL from package info.

    Args:
        package_name: Name of the package.
        package_data: Package metadata dictionary.

    Returns:
        GitHub URL if found, None otherwise.
    """
    # Try PyPI API to get project URLs
    return _fetch_github_url_from_pypi(package_name)


def _fetch_github_url_from_pypi(package_name: str) -> str | None:
    """Fetch GitHub URL from PyPI API.

    Args:
        package_name: Name of the package on PyPI.

    Returns:
        GitHub URL if found, None otherwise.
    """
    import urllib.request

    try:
        url = f"https://pypi.org/pypi/{package_name}/json"
        with urllib.request.urlopen(url, timeout=10) as response:
            data: dict[str, Any] = json.loads(response.read().decode())
            urls = data.get("info", {}).get("project_urls") or {}

            # Check common keys for GitHub
            github_keys = ["Source", "Repository", "Source Code", "Homepage", "Code", "GitHub"]
            for key in github_keys:
                if key in urls and "github.com" in urls[key]:
                    return urls[key].rstrip("/")

            # Check home_page field
            home_page = data.get("info", {}).get("home_page", "")
            if home_page and "github.com" in home_page:
                return home_page.rstrip("/")

    except Exception as e:
        print(f"  Warning: Could not fetch PyPI data for {package_name}: {e}")

    return None


def fetch_github_package(
    github_url: str,
    package_name: str,
    temp_dir: Path,
    timeout: int = 180,
) -> Path | None:
    """Clone a GitHub repository for benchmarking.

    Args:
        github_url: URL of the GitHub repository.
        package_name: Name to use for the cloned directory.
        temp_dir: Directory to clone into.
        timeout: Timeout in seconds for the clone operation.

    Returns:
        Path to the cloned repository, or None on failure.
    """
    target_path = temp_dir / package_name

    try:
        print(f"  Cloning {github_url}...")
        result = subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--quiet",
                github_url,
                str(target_path),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            print(f"  Failed to clone: {result.stderr}")
            return None

        return target_path
    except subprocess.TimeoutExpired:
        print(f"  Timeout cloning {github_url}")
        return None
    except Exception as e:
        print(f"  Error cloning {github_url}: {e}")
        return None


def is_type_checker_available(checker: str) -> bool:
    """Check if a type checker is available.

    Args:
        checker: Name of the type checker.

    Returns:
        True if the type checker is available, False otherwise.
    """
    # For mypy, check if it can be imported as a module
    if checker == "mypy":
        result = subprocess.run(
            [sys.executable, "-c", "import mypy"],
            capture_output=True,
        )
        return result.returncode == 0

    cmd_map = {
        "pyright": "pyright",
        "pyrefly": "pyrefly",
        "ty": "ty",
        "zuban": "zuban",
    }

    if checker not in cmd_map:
        return False

    which_cmd = "where" if sys.platform == "win32" else "which"
    result = subprocess.run(
        [which_cmd, cmd_map[checker]],
        capture_output=True,
    )
    return result.returncode == 0


def run_pyright(package_path: Path, timeout: int = SLOW_CHECKER_TIMEOUT) -> ErrorMetrics:
    """Run Pyright on a package and count errors.

    Args:
        package_path: Path to the package directory.
        timeout: Timeout in seconds (default: 5 minutes).

    Returns:
        Error metrics dictionary.
    """
    result = run_process_with_timeout(
        ["pyright", "--outputjson", str(package_path)],
        cwd=package_path,
        timeout=timeout,
    )

    if result["timed_out"]:
        return {
            "ok": False,
            "error_count": 0,
            "warning_count": 0,
            "info_count": 0,
            "files_checked": 0,
            "execution_time_s": result["execution_time_s"],
            "error_message": "Timeout",
        }

    try:
        output = json.loads(result["stdout"])
        summary = output.get("summary", {})
        return {
            "ok": True,
            "error_count": summary.get("errorCount", 0),
            "warning_count": summary.get("warningCount", 0),
            "info_count": summary.get("informationCount", 0),
            "files_checked": summary.get("filesAnalyzed", 0),
            "execution_time_s": result["execution_time_s"],
        }
    except json.JSONDecodeError:
        # Fallback: parse text output
        stdout = result["stdout"]
        error_count = len(re.findall(r"error:", stdout, re.IGNORECASE))
        warning_count = len(re.findall(r"warning:", stdout, re.IGNORECASE))
        return {
            "ok": True,
            "error_count": error_count,
            "warning_count": warning_count,
            "info_count": 0,
            "files_checked": 0,
            "execution_time_s": result["execution_time_s"],
        }
    except Exception as e:
        return {
            "ok": False,
            "error_count": 0,
            "warning_count": 0,
            "info_count": 0,
            "files_checked": 0,
            "execution_time_s": result["execution_time_s"],
            "error_message": str(e),
        }


def run_pyrefly(package_path: Path, timeout: int = DEFAULT_TIMEOUT) -> ErrorMetrics:
    """Run Pyrefly on a package and count errors.

    Args:
        package_path: Path to the package directory.
        timeout: Timeout in seconds.

    Returns:
        Error metrics dictionary.
    """
    result = run_process_with_timeout(
        ["pyrefly", "check", str(package_path)],
        cwd=package_path,
        timeout=timeout,
    )

    if result["timed_out"]:
        return {
            "ok": False,
            "error_count": 0,
            "warning_count": 0,
            "info_count": 0,
            "files_checked": 0,
            "execution_time_s": result["execution_time_s"],
            "error_message": "Timeout",
        }

    # Pyrefly outputs errors in format:
    # ERROR message [error-code]
    # INFO X errors
    output = result["stdout"] + result["stderr"]
    error_count = len(re.findall(r"^ERROR\s+", output, re.MULTILINE))
    warning_count = len(re.findall(r"^WARNING\s+", output, re.MULTILINE))

    # Try to find "INFO X errors" pattern at the end
    found_match = re.search(r"INFO\s+(\d+)\s+errors?", output, re.IGNORECASE)
    if found_match:
        error_count = int(found_match.group(1))

    return {
        "ok": True,
        "error_count": error_count,
        "warning_count": warning_count,
        "info_count": 0,
        "files_checked": 0,
        "execution_time_s": result["execution_time_s"],
    }


def run_ty(package_path: Path, timeout: int = DEFAULT_TIMEOUT) -> ErrorMetrics:
    """Run ty on a package and count errors.

    Args:
        package_path: Path to the package directory.
        timeout: Timeout in seconds.

    Returns:
        Error metrics dictionary.
    """
    result = run_process_with_timeout(
        ["ty", "check", str(package_path)],
        cwd=package_path,
        timeout=timeout,
    )

    if result["timed_out"]:
        return {
            "ok": False,
            "error_count": 0,
            "warning_count": 0,
            "info_count": 0,
            "files_checked": 0,
            "execution_time_s": result["execution_time_s"],
            "error_message": "Timeout",
        }

    # ty outputs errors in format:
    # error[error-code]: message
    # Found X diagnostics
    output = result["stdout"] + result["stderr"]

    # Count error and warning patterns
    error_count = len(re.findall(r"^error\[", output, re.MULTILINE))
    warning_count = len(re.findall(r"^warning\[", output, re.MULTILINE))

    # Try to find summary line "Found X diagnostics"
    found_match = re.search(r"Found\s+(\d+)\s+diagnostics?", output, re.IGNORECASE)
    if found_match:
        error_count = int(found_match.group(1))

    return {
        "ok": True,
        "error_count": error_count,
        "warning_count": warning_count,
        "info_count": 0,
        "files_checked": 0,
        "execution_time_s": result["execution_time_s"],
    }


def run_mypy(package_path: Path, timeout: int = SLOW_CHECKER_TIMEOUT) -> ErrorMetrics:
    """Run mypy on a package and count errors.

    Args:
        package_path: Path to the package directory.
        timeout: Timeout in seconds (default: 5 minutes).

    Returns:
        Error metrics dictionary.
    """
    # Run mypy on the package using python -m mypy
    # since the mypy executable might not be in PATH
    result = run_process_with_timeout(
        [sys.executable, "-m", "mypy", str(package_path)],
        cwd=package_path,
        timeout=timeout,
    )

    if result["timed_out"]:
        return {
            "ok": False,
            "error_count": 0,
            "warning_count": 0,
            "info_count": 0,
            "files_checked": 0,
            "execution_time_s": result["execution_time_s"],
            "error_message": "Timeout",
        }

    output = result["stdout"] + result["stderr"]

    # Count mypy error lines (format: file.py:line: error: message)
    error_count = len(re.findall(r":\s*error:", output, re.IGNORECASE))
    warning_count = len(re.findall(r":\s*warning:", output, re.IGNORECASE))
    note_count = len(re.findall(r":\s*note:", output, re.IGNORECASE))

    return {
        "ok": True,
        "error_count": error_count,
        "warning_count": warning_count,
        "info_count": note_count,
        "files_checked": 0,
        "execution_time_s": result["execution_time_s"],
    }


def run_zuban(package_path: Path, timeout: int = DEFAULT_TIMEOUT) -> ErrorMetrics:
    """Run Zuban on a package and count errors.

    Args:
        package_path: Path to the package directory.
        timeout: Timeout in seconds.

    Returns:
        Error metrics dictionary.
    """
    # zuban needs to run from within the package directory
    # and uses "." to check the current directory
    result = run_process_with_timeout(
        ["zuban", "check", "."],
        cwd=package_path,
        timeout=timeout,
    )

    if result["timed_out"]:
        return {
            "ok": False,
            "error_count": 0,
            "warning_count": 0,
            "info_count": 0,
            "files_checked": 0,
            "execution_time_s": result["execution_time_s"],
            "error_message": "Timeout",
        }

    output = result["stdout"] + result["stderr"]

    # zuban uses mypy-like output format:
    # file.py:line: error: message
    # Found X errors in Y files (checked Z source files)
    error_count = len(re.findall(r":\s*error:", output, re.IGNORECASE))
    warning_count = len(re.findall(r":\s*warning:", output, re.IGNORECASE))

    # Try to find summary line "Found X errors"
    found_match = re.search(r"Found\s+(\d+)\s+errors?", output, re.IGNORECASE)
    if found_match:
        error_count = int(found_match.group(1))

    return {
        "ok": True,
        "error_count": error_count,
        "warning_count": warning_count,
        "info_count": 0,
        "files_checked": 0,
        "execution_time_s": result["execution_time_s"],
    }


# Map of type checker names to their runner functions
TYPE_CHECKER_RUNNERS = {
    "pyright": run_pyright,
    "pyrefly": run_pyrefly,
    "ty": run_ty,
    "mypy": run_mypy,
    "zuban": run_zuban,
}


def run_type_checkers_for_package(
    package_path: Path,
    package_name: str,
    type_checkers: list[str],
    timeout: int = 300,
) -> dict[str, ErrorMetrics]:
    """Run all type checkers on a package.

    Args:
        package_path: Path to the package directory.
        package_name: Name of the package.
        type_checkers: List of type checker names to run.
        timeout: Timeout in seconds for each type checker.

    Returns:
        Dictionary mapping checker names to their metrics.
    """
    results: dict[str, ErrorMetrics] = {}

    for checker in type_checkers:
        if not is_type_checker_available(checker):
            print(f"    Skipping {checker}: not installed")
            results[checker] = {
                "ok": False,
                "error_count": 0,
                "warning_count": 0,
                "info_count": 0,
                "files_checked": 0,
                "execution_time_s": 0,
                "error_message": "Type checker not installed",
            }
            continue

        runner = TYPE_CHECKER_RUNNERS.get(checker)
        if not runner:
            print(f"    Skipping {checker}: no runner available")
            continue

        print(f"    Running {checker}...")
        metrics = runner(package_path, timeout)
        results[checker] = metrics

        if metrics.get("ok"):
            print(f"      {metrics.get('error_count', 0)} errors, "
                  f"{metrics.get('warning_count', 0)} warnings "
                  f"({metrics.get('execution_time_s', 0):.1f}s)")
        else:
            print(f"      Failed: {metrics.get('error_message', 'Unknown error')}")

    return results


def compute_percentile(values: list[float | int], percentile: float) -> float:
    """Compute the given percentile of a list of values.

    Args:
        values: List of numeric values.
        percentile: Percentile to compute (0-100).

    Returns:
        The percentile value, or 0 if values is empty.
    """
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = (percentile / 100) * (len(sorted_values) - 1)
    lower = int(index)
    upper = lower + 1
    if upper >= len(sorted_values):
        return float(sorted_values[-1])
    fraction = index - lower
    return sorted_values[lower] + fraction * (sorted_values[upper] - sorted_values[lower])


def compute_aggregate_stats(
    results: list[PackageResult],
    type_checkers: list[str],
) -> dict[str, AggregateStats]:
    """Compute aggregate statistics across all packages.

    Args:
        results: List of package benchmark results.
        type_checkers: List of type checker names.

    Returns:
        Dictionary mapping checker names to aggregate statistics.
    """
    stats: dict[str, AggregateStats] = {}

    for checker in type_checkers:
        error_counts: list[int] = []
        warning_counts: list[int] = []
        execution_times: list[float] = []
        packages_tested = 0

        for result in results:
            if result.get("error"):
                continue

            metrics = result.get("metrics", {}).get(checker, {})
            if not metrics.get("ok"):
                continue

            packages_tested += 1
            error_counts.append(metrics.get("error_count", 0))
            warning_counts.append(metrics.get("warning_count", 0))
            exec_time = metrics.get("execution_time_s")
            if exec_time is not None:
                execution_times.append(exec_time)

        total_errors = sum(error_counts)
        total_warnings = sum(warning_counts)
        avg_errors = total_errors / len(error_counts) if error_counts else 0.0
        avg_time = sum(execution_times) / len(execution_times) if execution_times else 0.0
        p95_errors = compute_percentile(error_counts, 95)
        p95_time = compute_percentile(execution_times, 95)

        stats[checker] = {
            "packages_tested": packages_tested,
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "avg_errors_per_package": round(avg_errors, 2),
            "p95_errors": round(p95_errors),
            "min_errors": min(error_counts) if error_counts else 0,
            "max_errors": max(error_counts) if error_counts else 0,
            "avg_execution_time_s": round(avg_time, 2),
            "p95_execution_time_s": round(p95_time, 2),
        }

    return stats


def print_summary(stats: dict[str, AggregateStats], type_checkers: list[str]) -> None:
    """Print a summary of the benchmark results.

    Args:
        stats: Aggregate statistics dictionary.
        type_checkers: List of type checker names.
    """
    print("\nAggregate Results:")
    print("-" * 70)

    for checker in type_checkers:
        s = stats.get(checker, {})
        if s.get("packages_tested", 0) == 0:
            print(f"  {checker}: No successful checks")
            continue

        print(f"  {checker}:")
        print(f"    Packages tested: {s.get('packages_tested', 0)}")
        print(f"    Total errors: {s.get('total_errors', 0)}")
        print(f"    Total warnings: {s.get('total_warnings', 0)}")
        print(f"    Avg errors/package: {s.get('avg_errors_per_package', 0):.1f}")
        print(f"    P95 errors: {s.get('p95_errors', 0)}")
        print(f"    Avg execution time: {s.get('avg_execution_time_s', 0):.1f}s")
        print(f"    P95 execution time: {s.get('p95_execution_time_s', 0):.1f}s")


def run_daily_benchmark(
    package_limit: int | None = None,
    package_names: list[str] | None = None,
    type_checkers: list[str] | None = None,
    timeout: int = 300,
    output_dir: Path | None = None,
    os_name: str | None = None,
) -> Path:
    """Run the daily benchmark suite.

    Args:
        package_limit: Maximum number of packages to benchmark.
        package_names: Specific package names to benchmark (overrides package_limit).
        type_checkers: List of type checker names to use.
        timeout: Timeout in seconds for each type checker.
        output_dir: Directory to write results to.
        os_name: OS name to include in output filename (e.g., ubuntu, macos, windows).

    Returns:
        Path to the output JSON file.
    """
    if type_checkers is None:
        type_checkers = DEFAULT_TYPE_CHECKERS.copy()

    if output_dir is None:
        output_dir = ROOT_DIR / "type_checker_benchmark" / "results"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load packages - either by name or by limit
    if package_names:
        all_packages = load_benchmark_packages(limit=None)
        packages = [p for p in all_packages if p["name"] in package_names]
        if not packages:
            print(f"Warning: None of the specified packages found: {package_names}")
            print(f"Available packages: {[p['name'] for p in all_packages[:20]]}...")
            return output_dir / "empty.json"
    else:
        packages = load_benchmark_packages(limit=package_limit)

    _print_benchmark_header(packages, type_checkers, timeout)

    # Get type checker versions
    type_checker_versions = get_type_checker_versions()
    print("\nType Checker Versions:")
    for name, version in type_checker_versions.items():
        print(f"  {name}: {version}")
    print()

    all_results = _run_all_benchmarks(packages, type_checkers, timeout)

    # Compute aggregate statistics
    aggregate_stats = compute_aggregate_stats(all_results, type_checkers)

    # Save results
    output_file = _save_results(
        all_results,
        aggregate_stats,
        type_checkers,
        type_checker_versions,
        len(packages),
        output_dir,
        os_name,
    )

    print("\n" + "=" * 70)
    print("Benchmark Complete!")
    print("=" * 70)
    print_summary(aggregate_stats, type_checkers)
    print(f"\nResults saved to:")
    print(f"  {output_file}")

    return output_file


def _print_benchmark_header(
    packages: list[PackageInfo],
    type_checkers: list[str],
    timeout: int,
) -> None:
    """Print the benchmark header."""
    print("=" * 70)
    print("Type Checker Error Benchmark")
    print("=" * 70)
    print(f"Packages to check: {len(packages)}")
    print(f"Type checkers: {', '.join(type_checkers)}")
    print(f"Timeout per checker: {timeout}s")
    print("=" * 70)


def _run_all_benchmarks(
    packages: list[PackageInfo],
    type_checkers: list[str],
    timeout: int,
) -> list[PackageResult]:
    """Run benchmarks for all packages.

    Args:
        packages: List of packages to benchmark.
        type_checkers: List of type checkers to use.
        timeout: Timeout in seconds for each type checker.

    Returns:
        List of package results.
    """
    all_results: list[PackageResult] = []

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        for i, package in enumerate(packages, 1):
            package_name = package["name"]
            github_url = package.get("github_url")

            print(f"\n[{i}/{len(packages)}] Processing {package_name}")

            result = _benchmark_single_package(
                package, github_url, temp_path, type_checkers, timeout
            )
            all_results.append(result)

    return all_results


def _benchmark_single_package(
    package: PackageInfo,
    github_url: str | None,
    temp_path: Path,
    type_checkers: list[str],
    timeout: int,
) -> PackageResult:
    """Benchmark a single package.

    Args:
        package: Package information.
        github_url: GitHub URL for the package.
        temp_path: Temporary directory for cloning.
        type_checkers: List of type checkers to use.
        timeout: Timeout in seconds for each type checker.

    Returns:
        Package result dictionary.
    """
    package_name = package["name"]
    has_py_typed = package.get("has_py_typed", False)
    configured_checkers = package.get("configured_checkers", {})

    # Print configured checkers info
    configured = [tc for tc, detected in configured_checkers.items() if detected]
    if configured:
        print(f"  Configured type checkers: {', '.join(configured)}")
    if has_py_typed:
        print(f"  Has py.typed marker")

    if not github_url:
        print("  Skipping: No GitHub URL found")
        return {
            "package_name": package_name,
            "github_url": None,
            "ranking": package.get("ranking"),
            "error": "No GitHub URL found",
            "metrics": {},
            "has_py_typed": has_py_typed,
            "configured_checkers": configured_checkers,
        }

    package_path = fetch_github_package(github_url, package_name, temp_path)
    if not package_path:
        return {
            "package_name": package_name,
            "github_url": github_url,
            "ranking": package.get("ranking"),
            "error": "Failed to clone repository",
            "metrics": {},
            "has_py_typed": has_py_typed,
            "configured_checkers": configured_checkers,
        }

    print(f"  Running type checkers...")

    try:
        metrics = run_type_checkers_for_package(
            package_path,
            package_name,
            type_checkers,
            timeout=timeout,
        )

        return {
            "package_name": package_name,
            "github_url": github_url,
            "ranking": package.get("ranking"),
            "error": None,
            "metrics": metrics,
            "has_py_typed": has_py_typed,
            "configured_checkers": configured_checkers,
        }
    finally:
        # Cleanup package directory
        shutil.rmtree(package_path, ignore_errors=True)


def _save_results(
    results: list[PackageResult],
    aggregate_stats: dict[str, AggregateStats],
    type_checkers: list[str],
    type_checker_versions: dict[str, str],
    package_count: int,
    output_dir: Path,
    os_name: str | None = None,
) -> Path:
    """Save benchmark results to JSON files.

    Args:
        results: List of package results.
        aggregate_stats: Aggregate statistics.
        type_checkers: List of type checkers used.
        type_checker_versions: Version strings for each type checker.
        package_count: Number of packages benchmarked.
        output_dir: Directory to write to.
        os_name: OS name to include in filename (e.g., ubuntu, macos, windows).

    Returns:
        Path to the dated output file.
    """
    timestamp = datetime.now(timezone.utc)
    date_str = timestamp.strftime("%Y-%m-%d")

    # Build filename with optional OS suffix
    if os_name:
        output_file = output_dir / f"benchmark_{date_str}_{os_name}.json"
        latest_file = output_dir / f"latest-{os_name}.json"
    else:
        output_file = output_dir / f"benchmark_{date_str}.json"
        latest_file = output_dir / "latest.json"

    output_data: BenchmarkOutput = {
        "timestamp": timestamp.isoformat(),
        "date": date_str,
        "type_checkers": type_checkers,
        "type_checker_versions": type_checker_versions,
        "package_count": package_count,
        "aggregate": aggregate_stats,
        "results": results,
    }

    # Add OS to output if specified
    if os_name:
        output_data["os"] = os_name  # type: ignore[typeddict-unknown-key]

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    # Also save as latest.json (or latest-{os}.json) for the web page
    with open(latest_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print(f"  {latest_file}")

    return output_file


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Command-line arguments (uses sys.argv if None).

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Run type checker error benchmarks across packages"
    )
    parser.add_argument(
        "--packages",
        "-p",
        type=int,
        default=None,
        help="Number of packages to benchmark (default: all prioritized packages)",
    )
    parser.add_argument(
        "--package-names",
        "-n",
        nargs="+",
        default=None,
        help="Specific package names to benchmark (overrides --packages)",
    )
    parser.add_argument(
        "--checkers",
        "-c",
        nargs="+",
        default=DEFAULT_TYPE_CHECKERS,
        help=f"Type checkers to benchmark (default: {' '.join(DEFAULT_TYPE_CHECKERS)})",
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
        help="Output directory for results",
    )
    parser.add_argument(
        "--os-name",
        type=str,
        default=None,
        help="OS name to include in output filename (e.g., ubuntu, macos, windows)",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Command-line arguments.

    Returns:
        Exit code (0 for success).
    """
    args = parse_args(argv)

    run_daily_benchmark(
        package_limit=args.packages,
        package_names=args.package_names,
        type_checkers=args.checkers,
        timeout=args.timeout,
        output_dir=args.output,
        os_name=args.os_name,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
