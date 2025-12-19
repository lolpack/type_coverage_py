#!/usr/bin/env python3
"""Daily runner for LSP benchmarks across type checkers.

This script:
1. Loads packages from the prioritized package report
2. Clones each package from GitHub
3. Runs the LSP benchmark against each type checker
4. Saves results to JSON for the web dashboard
"""

from __future__ import annotations

import argparse
import json
import subprocess
import shutil
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypedDict

# Add parent directories to path for imports
ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))


class LatencyMetrics(TypedDict, total=False):
    """Latency metrics from benchmark runs."""

    p50: float | None
    p95: float | None
    min: float | None
    max: float | None
    mean: float | None


class CheckerMetrics(TypedDict, total=False):
    """Metrics for a single type checker on a package."""

    ok: bool
    runs: int
    ok_count: int
    ok_pct: float
    found_count: int
    found_pct: float
    valid_count: int
    valid_pct: float
    errors: int
    latency_ms: LatencyMetrics | None
    error: str | None


class PackageResult(TypedDict):
    """Result of benchmarking a single package."""

    package_name: str
    github_url: str | None
    ranking: int | None
    error: str | None
    metrics: dict[str, CheckerMetrics]


class AggregateStats(TypedDict, total=False):
    """Aggregate statistics for a type checker."""

    packages_tested: int
    total_runs: int
    total_ok: int
    total_found: int
    total_valid: int
    avg_latency_ms: float | None
    min_latency_ms: float | None
    max_latency_ms: float | None
    success_rate: float


class BenchmarkOutput(TypedDict):
    """Complete benchmark output structure."""

    timestamp: str
    date: str
    type_checkers: list[str]
    package_count: int
    runs_per_package: int
    aggregate: dict[str, AggregateStats]
    results: list[PackageResult]


class PackageInfo(TypedDict):
    """Package information from the prioritized list."""

    name: str
    github_url: str | None
    download_count: int
    ranking: int


# Type for the benchmark runner function
BenchmarkRunner = Callable[[list[str]], int]

# Lazy-loaded benchmark runner
_benchmark_runner: BenchmarkRunner | None = None


def get_benchmark_runner() -> BenchmarkRunner:
    """Get the benchmark runner function, loading it lazily."""
    global _benchmark_runner
    if _benchmark_runner is not None:
        return _benchmark_runner

    import importlib.util

    benchmark_path = ROOT_DIR / "lsp" / "lsp_benchmark.py"

    if not benchmark_path.exists():
        raise ImportError(f"Benchmark module not found at {benchmark_path}")

    spec = importlib.util.spec_from_file_location("lsp_benchmark", benchmark_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {benchmark_path}")

    module = importlib.util.module_from_spec(spec)
    # Register the module in sys.modules BEFORE exec_module
    # This is required for dataclasses to work properly
    sys.modules["lsp_benchmark"] = module
    spec.loader.exec_module(module)
    runner: BenchmarkRunner = module.main
    _benchmark_runner = runner
    return runner


# GitHub URL mapping for known packages
KNOWN_GITHUB_URLS: dict[str, str] = {
    "requests": "https://github.com/psf/requests",
    "numpy": "https://github.com/numpy/numpy",
    "pandas": "https://github.com/pandas-dev/pandas",
    "click": "https://github.com/pallets/click",
    "flask": "https://github.com/pallets/flask",
    "django": "https://github.com/django/django",
    "fastapi": "https://github.com/fastapi/fastapi",
    "pydantic": "https://github.com/pydantic/pydantic",
    "httpx": "https://github.com/encode/httpx",
    "aiohttp": "https://github.com/aio-libs/aiohttp",
    "boto3": "https://github.com/boto/boto3",
    "botocore": "https://github.com/boto/botocore",
    "urllib3": "https://github.com/urllib3/urllib3",
    "certifi": "https://github.com/certifi/python-certifi",
    "idna": "https://github.com/kjd/idna",
    "charset-normalizer": "https://github.com/Ousret/charset_normalizer",
    "typing-extensions": "https://github.com/python/typing_extensions",
    "packaging": "https://github.com/pypa/packaging",
    "setuptools": "https://github.com/pypa/setuptools",
    "wheel": "https://github.com/pypa/wheel",
    "pip": "https://github.com/pypa/pip",
    "six": "https://github.com/benjaminp/six",
    "python-dateutil": "https://github.com/dateutil/dateutil",
    "pyyaml": "https://github.com/yaml/pyyaml",
    "attrs": "https://github.com/python-attrs/attrs",
    "cryptography": "https://github.com/pyca/cryptography",
    "cffi": "https://github.com/python-cffi/cffi",
    "jinja2": "https://github.com/pallets/jinja",
    "markupsafe": "https://github.com/pallets/markupsafe",
    "sqlalchemy": "https://github.com/sqlalchemy/sqlalchemy",
    "pillow": "https://github.com/python-pillow/Pillow",
    "pytest": "https://github.com/pytest-dev/pytest",
    "scipy": "https://github.com/scipy/scipy",
    "matplotlib": "https://github.com/matplotlib/matplotlib",
    "scikit-learn": "https://github.com/scikit-learn/scikit-learn",
    "tensorflow": "https://github.com/tensorflow/tensorflow",
    "torch": "https://github.com/pytorch/pytorch",
    "transformers": "https://github.com/huggingface/transformers",
    "rich": "https://github.com/Textualize/rich",
    "typer": "https://github.com/tiangolo/typer",
    "uvicorn": "https://github.com/encode/uvicorn",
    "starlette": "https://github.com/encode/starlette",
    "redis": "https://github.com/redis/redis-py",
    "celery": "https://github.com/celery/celery",
    "homeassistant": "https://github.com/home-assistant/core",
}

# Type checker LSP commands
# Note: Indexing is disabled for pyrefly to ensure fast cold-start benchmarks
TYPE_CHECKER_COMMANDS: dict[str, str] = {
    "pyright": "pyright-langserver --stdio",
    "pyrefly": "pyrefly lsp --indexing-mode none",
    "ty": "ty server",
    "zuban": "zubanls",
}

DEFAULT_TYPE_CHECKERS: list[str] = ["pyright", "pyrefly", "ty", "zuban"]


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
        {
            "name": "requests",
            "github_url": "https://github.com/psf/requests",
            "ranking": 1,
            "download_count": 0,
        },
        {
            "name": "flask",
            "github_url": "https://github.com/pallets/flask",
            "ranking": 2,
            "download_count": 0,
        },
        {
            "name": "django",
            "github_url": "https://github.com/django/django",
            "ranking": 3,
            "download_count": 0,
        },
        {
            "name": "fastapi",
            "github_url": "https://github.com/fastapi/fastapi",
            "ranking": 4,
            "download_count": 0,
        },
        {
            "name": "pydantic",
            "github_url": "https://github.com/pydantic/pydantic",
            "ranking": 5,
            "download_count": 0,
        },
        {
            "name": "numpy",
            "github_url": "https://github.com/numpy/numpy",
            "ranking": 6,
            "download_count": 0,
        },
        {
            "name": "pandas",
            "github_url": "https://github.com/pandas-dev/pandas",
            "ranking": 7,
            "download_count": 0,
        },
        {
            "name": "click",
            "github_url": "https://github.com/pallets/click",
            "ranking": 8,
            "download_count": 0,
        },
        {
            "name": "httpx",
            "github_url": "https://github.com/encode/httpx",
            "ranking": 9,
            "download_count": 0,
        },
        {
            "name": "aiohttp",
            "github_url": "https://github.com/aio-libs/aiohttp",
            "ranking": 10,
            "download_count": 0,
        },
    ]


def resolve_github_url(package_name: str, package_data: dict[str, Any]) -> str | None:
    """Resolve GitHub URL from package info.

    Args:
        package_name: Name of the package.
        package_data: Package metadata dictionary.

    Returns:
        GitHub URL if found, None otherwise.
    """
    # Check known mappings first
    normalized_name = package_name.lower()
    if normalized_name in KNOWN_GITHUB_URLS:
        return KNOWN_GITHUB_URLS[normalized_name]

    # Try PyPI API to get project URLs
    return _fetch_github_url_from_pypi(package_name)


def _fetch_github_url_from_pypi(package_name: str) -> str | None:
    """Fetch GitHub URL from PyPI API.

    Args:
        package_name: Name of the package on PyPI.

    Returns:
        GitHub URL if found, None otherwise.
    """
    try:
        url = f"https://pypi.org/pypi/{package_name}/json"
        with urllib.request.urlopen(url, timeout=10) as response:
            data: dict[str, Any] = json.loads(response.read().decode())
            urls = data.get("info", {}).get("project_urls") or {}

            # Check common keys for GitHub
            github_keys = [
                "Source",
                "Repository",
                "Source Code",
                "Homepage",
                "Code",
                "GitHub",
            ]
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


def find_type_checker_command(checker: str) -> str | None:
    """Find the command to run a type checker's LSP server.

    Args:
        checker: Name of the type checker.

    Returns:
        Command string if available, None otherwise.
    """
    if checker not in TYPE_CHECKER_COMMANDS:
        return None

    cmd_parts = TYPE_CHECKER_COMMANDS[checker].split()
    executable = cmd_parts[0]

    # Check if the command exists
    which_cmd = "where" if sys.platform == "win32" else "which"
    result = subprocess.run(
        [which_cmd, executable],
        capture_output=True,
    )

    if result.returncode == 0:
        return TYPE_CHECKER_COMMANDS[checker]

    return None


def run_benchmark_for_package(
    package_path: Path,
    package_name: str,
    type_checkers: list[str],
    runs: int = 5,
    seed: int | None = None,
) -> dict[str, CheckerMetrics]:
    """Run the LSP benchmark for a package across all type checkers.

    All type checkers are run in a single benchmark invocation to ensure
    they are tested on the exact same files and positions for fairness.

    Args:
        package_path: Path to the package directory.
        package_name: Name of the package.
        type_checkers: List of type checker names to run.
        runs: Number of benchmark runs per checker.
        seed: Random seed for reproducibility.

    Returns:
        Dictionary mapping checker names to their metrics.
    """
    results: dict[str, CheckerMetrics] = {}

    # Find available type checkers and their commands
    available_checkers: list[tuple[str, str]] = []
    for checker in type_checkers:
        cmd = find_type_checker_command(checker)
        if not cmd:
            print(f"    Skipping {checker}: command not found")
            results[checker] = {
                "ok": False,
                "error": "Type checker not installed",
                "latency_ms": None,
            }
        else:
            available_checkers.append((checker, cmd))

    if not available_checkers:
        return results

    # Run all available checkers together in a single benchmark call
    # This ensures they all get the exact same test cases for fairness
    print(f"    Running {', '.join(c[0] for c in available_checkers)} together...")
    benchmark_results = _run_checkers_together(
        available_checkers, package_path, runs, seed
    )
    results.update(benchmark_results)

    return results


def _run_checkers_together(
    checkers: list[tuple[str, str]],
    package_path: Path,
    runs: int,
    seed: int | None,
) -> dict[str, CheckerMetrics]:
    """Run multiple type checkers together in a single benchmark.

    This ensures all checkers are tested on the exact same files and positions.

    Args:
        checkers: List of (checker_name, command) tuples.
        package_path: Path to the package directory.
        runs: Number of benchmark runs.
        seed: Random seed for reproducibility.

    Returns:
        Dictionary mapping checker names to their metrics.
    """
    results: dict[str, CheckerMetrics] = {}

    try:
        benchmark_runner = get_benchmark_runner()

        # Build args for all checkers
        checker_names = [name for name, _ in checkers]
        args = [
            "--root",
            str(package_path),
            "--servers",
            ",".join(checker_names),  # Comma-separated list of servers
            "--runs",
            str(runs),
            "--didopen-warmup-ms",
            "100",
        ]

        # Add command for each checker
        for checker, cmd in checkers:
            args.extend([f"--{checker}-cmd", cmd])

        # Disable indexing for pyright if it's in the list
        if any(name == "pyright" for name, _ in checkers):
            args.append("--pyright-disable-indexing")

        if seed is not None:
            args.extend(["--seed", str(seed)])

        # Create a temp file for JSON output
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as tmp:
            tmp_path = Path(tmp.name)

        args.extend(["--json", str(tmp_path)])

        # Run the benchmark with all checkers together
        benchmark_runner(args)

        # Read and parse results for all checkers
        if tmp_path.exists():
            try:
                with open(tmp_path, encoding="utf-8") as f:
                    benchmark_data: dict[str, Any] = json.load(f)

                for checker, _ in checkers:
                    results[checker] = _parse_benchmark_results(
                        benchmark_data, checker, runs
                    )
            finally:
                tmp_path.unlink(missing_ok=True)
        else:
            for checker, _ in checkers:
                results[checker] = {
                    "ok": False,
                    "error": "No output file generated",
                    "latency_ms": None,
                }

    except Exception as e:
        print(f"    Error running benchmark: {e}")
        for checker, _ in checkers:
            results[checker] = {
                "ok": False,
                "error": str(e),
                "latency_ms": None,
            }

    return results


def _parse_benchmark_results(
    benchmark_data: dict[str, Any],
    checker: str,
    runs: int,
) -> CheckerMetrics:
    """Parse benchmark results from JSON data.

    Args:
        benchmark_data: Raw benchmark output data.
        checker: Name of the type checker.
        runs: Number of runs performed.

    Returns:
        Parsed metrics dictionary.
    """
    summary = benchmark_data.get("summary", {}).get(checker, {})
    latency = summary.get("latency_ms", {})

    return {
        "ok": True,
        "runs": runs,
        "ok_count": summary.get("ok", 0),
        "ok_pct": summary.get("ok_pct", 0.0),
        "found_count": summary.get("found", 0),
        "found_pct": summary.get("found_pct", 0.0),
        "valid_count": summary.get("valid", 0),
        "valid_pct": summary.get("valid_pct", 0.0),
        "errors": summary.get("errors", 0),
        "latency_ms": {
            "p50": latency.get("p50"),
            "p95": latency.get("p95"),
            "min": latency.get("min"),
            "max": latency.get("max"),
            "mean": latency.get("mean"),
        },
    }


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
        latencies: list[float] = []
        valid_counts: list[int] = []
        found_counts: list[int] = []
        ok_counts: list[int] = []
        total_runs = 0
        packages_tested = 0

        for result in results:
            if result.get("error"):
                continue

            metrics = result.get("metrics", {}).get(checker, {})
            if not metrics.get("ok"):
                continue

            packages_tested += 1
            runs = metrics.get("runs", 0)
            total_runs += runs

            ok_counts.append(metrics.get("ok_count", 0))
            found_counts.append(metrics.get("found_count", 0))
            valid_counts.append(metrics.get("valid_count", 0))

            latency = metrics.get("latency_ms") or {}
            mean_latency = latency.get("mean")
            if mean_latency is not None:
                latencies.append(float(mean_latency))

        avg_latency: float | None = None
        min_latency: float | None = None
        max_latency: float | None = None

        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            min_latency = min(latencies)
            max_latency = max(latencies)

        success_rate = (sum(valid_counts) / total_runs * 100) if total_runs > 0 else 0.0

        stats[checker] = {
            "packages_tested": packages_tested,
            "total_runs": total_runs,
            "total_ok": sum(ok_counts),
            "total_found": sum(found_counts),
            "total_valid": sum(valid_counts),
            "avg_latency_ms": avg_latency,
            "min_latency_ms": min_latency,
            "max_latency_ms": max_latency,
            "success_rate": success_rate,
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
            print(f"  {checker}: No successful benchmarks")
            continue

        latency = s.get("avg_latency_ms")
        latency_str = f"{latency:.1f}ms" if latency else "N/A"

        print(f"  {checker}:")
        print(f"    Packages tested: {s.get('packages_tested', 0)}")
        print(f"    Total runs: {s.get('total_runs', 0)}")
        print(
            f"    Valid definitions: {s.get('total_valid', 0)} "
            f"({s.get('success_rate', 0):.1f}%)"
        )
        print(f"    Avg latency: {latency_str}")


def run_daily_benchmark(
    package_limit: int = 10,
    type_checkers: list[str] | None = None,
    runs_per_package: int = 5,
    output_dir: Path | None = None,
    seed: int | None = None,
) -> Path:
    """Run the daily benchmark suite.

    Args:
        package_limit: Maximum number of packages to benchmark.
        type_checkers: List of type checker names to use.
        runs_per_package: Number of benchmark runs per package.
        output_dir: Directory to write results to.
        seed: Random seed for reproducibility.

    Returns:
        Path to the output JSON file.
    """
    if type_checkers is None:
        type_checkers = DEFAULT_TYPE_CHECKERS.copy()

    if output_dir is None:
        output_dir = ROOT_DIR / "lsp" / "benchmark" / "results"

    output_dir.mkdir(parents=True, exist_ok=True)

    packages = load_prioritized_packages(limit=package_limit)

    _print_benchmark_header(packages, type_checkers, runs_per_package)

    all_results = _run_all_benchmarks(packages, type_checkers, runs_per_package, seed)

    # Compute aggregate statistics
    aggregate_stats = compute_aggregate_stats(all_results, type_checkers)

    # Save results
    output_file = _save_results(
        all_results,
        aggregate_stats,
        type_checkers,
        len(packages),
        runs_per_package,
        output_dir,
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
    runs_per_package: int,
) -> None:
    """Print the benchmark header."""
    print("=" * 70)
    print("LSP Benchmark Daily Runner")
    print("=" * 70)
    print(f"Packages to benchmark: {len(packages)}")
    print(f"Type checkers: {', '.join(type_checkers)}")
    print(f"Runs per package: {runs_per_package}")
    print("=" * 70)


def _run_all_benchmarks(
    packages: list[PackageInfo],
    type_checkers: list[str],
    runs_per_package: int,
    seed: int | None,
) -> list[PackageResult]:
    """Run benchmarks for all packages.

    Args:
        packages: List of packages to benchmark.
        type_checkers: List of type checkers to use.
        runs_per_package: Number of runs per package.
        seed: Random seed for reproducibility.

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
                package, github_url, temp_path, type_checkers, runs_per_package, seed
            )
            all_results.append(result)

    return all_results


def _benchmark_single_package(
    package: PackageInfo,
    github_url: str | None,
    temp_path: Path,
    type_checkers: list[str],
    runs_per_package: int,
    seed: int | None,
) -> PackageResult:
    """Benchmark a single package.

    Args:
        package: Package information.
        github_url: GitHub URL for the package.
        temp_path: Temporary directory for cloning.
        type_checkers: List of type checkers to use.
        runs_per_package: Number of runs per package.
        seed: Random seed for reproducibility.

    Returns:
        Package result dictionary.
    """
    package_name = package["name"]

    if not github_url:
        print("  Skipping: No GitHub URL found")
        return {
            "package_name": package_name,
            "github_url": None,
            "ranking": package.get("ranking"),
            "error": "No GitHub URL found",
            "metrics": {},
        }

    package_path = fetch_github_package(github_url, package_name, temp_path)
    if not package_path:
        return {
            "package_name": package_name,
            "github_url": github_url,
            "ranking": package.get("ranking"),
            "error": "Failed to clone repository",
            "metrics": {},
        }

    print(f"  Running benchmarks ({runs_per_package} runs each)...")

    try:
        metrics = run_benchmark_for_package(
            package_path,
            package_name,
            type_checkers,
            runs=runs_per_package,
            seed=seed,
        )

        return {
            "package_name": package_name,
            "github_url": github_url,
            "ranking": package.get("ranking"),
            "error": None,
            "metrics": metrics,
        }
    finally:
        # Cleanup package directory
        shutil.rmtree(package_path, ignore_errors=True)


def _save_results(
    results: list[PackageResult],
    aggregate_stats: dict[str, AggregateStats],
    type_checkers: list[str],
    package_count: int,
    runs_per_package: int,
    output_dir: Path,
) -> Path:
    """Save benchmark results to JSON files.

    Args:
        results: List of package results.
        aggregate_stats: Aggregate statistics.
        type_checkers: List of type checkers used.
        package_count: Number of packages benchmarked.
        runs_per_package: Number of runs per package.
        output_dir: Directory to write to.

    Returns:
        Path to the dated output file.
    """
    timestamp = datetime.now(timezone.utc)
    date_str = timestamp.strftime("%Y-%m-%d")
    output_file = output_dir / f"benchmark_{date_str}.json"

    output_data: BenchmarkOutput = {
        "timestamp": timestamp.isoformat(),
        "date": date_str,
        "type_checkers": type_checkers,
        "package_count": package_count,
        "runs_per_package": runs_per_package,
        "aggregate": aggregate_stats,
        "results": results,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    # Also save as latest.json for the web page
    latest_file = output_dir / "latest.json"
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
        description="Run daily LSP benchmarks across type checkers"
    )
    parser.add_argument(
        "--packages",
        "-p",
        type=int,
        default=None,
        help="Number of packages to benchmark (default: all prioritized packages)",
    )
    parser.add_argument(
        "--checkers",
        "-c",
        nargs="+",
        default=DEFAULT_TYPE_CHECKERS,
        help=f"Type checkers to benchmark (default: {' '.join(DEFAULT_TYPE_CHECKERS)})",
    )
    parser.add_argument(
        "--runs",
        "-r",
        type=int,
        default=100,
        help="Number of runs per package (default: 100)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output directory for results",
    )
    parser.add_argument(
        "--seed",
        "-s",
        type=int,
        default=None,
        help="Random seed for reproducibility",
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
        type_checkers=args.checkers,
        runs_per_package=args.runs,
        output_dir=args.output,
        seed=args.seed,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
