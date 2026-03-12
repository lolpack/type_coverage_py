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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypedDict

# Add parent directories to path for imports
ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))


def get_type_checker_versions() -> dict[str, str]:
    """Get version strings for all type checkers.

    Returns:
        Dictionary mapping type checker names to version strings.
    """
    import re
    
    versions: dict[str, str] = {}

    version_commands = {
        "pyright": ["pyright", "--version"],
        "pyrefly": ["pyrefly", "--version"],
        "ty": ["ty", "--version"],
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
                match = re.search(r'\d+\.\d+\.\d+', output)
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
    ok_rate: float
    success_rate: float


class BenchmarkOutput(TypedDict, total=False):
    """Complete benchmark output structure."""

    timestamp: str
    date: str
    type_checkers: list[str]
    type_checker_versions: dict[str, str]
    package_count: int
    runs_per_package: int
    aggregate: dict[str, AggregateStats]
    results: list[PackageResult]
    os: str


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


# Type checker LSP commands
TYPE_CHECKER_COMMANDS: dict[str, str] = {
    "pyright": "pyright-langserver --stdio",
    "pyrefly": "pyrefly lsp",
    "ty": "ty server",
    "zuban": "zubanls",
}

DEFAULT_TYPE_CHECKERS: list[str] = ["pyright", "pyrefly", "ty", "zuban"]


def load_packages_from_install_envs(
    limit: int | None = None,
    package_names: list[str] | None = None,
) -> list[PackageInfo]:
    """Load packages from typecheck_benchmark/install_envs.json.

    This is the single source of truth for which packages to benchmark,
    shared with the typecheck benchmark.

    Args:
        limit: Maximum number of packages to return.
        package_names: If provided, only return packages with these names.

    Returns:
        List of package information dictionaries.
    """
    install_envs_file = ROOT_DIR / "typecheck_benchmark" / "install_envs.json"
    if not install_envs_file.exists():
        print(f"Error: {install_envs_file} not found")
        return []

    with open(install_envs_file, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    packages: list[PackageInfo] = []
    name_filter = {n.lower() for n in package_names} if package_names else None

    for i, pkg in enumerate(data.get("packages", [])):
        github_url = pkg.get("github_url", "")
        if not github_url:
            continue
        name = pkg.get("name") or github_url.rstrip("/").split("/")[-1]

        if name_filter and name.lower() not in name_filter:
            continue

        packages.append({
            "name": name,
            "github_url": github_url,
            "download_count": 0,
            "ranking": i + 1,
        })

    if name_filter:
        found = {p["name"].lower() for p in packages}
        for n in package_names or []:
            if n.lower() not in found:
                print(f"Warning: package '{n}' not found in install_envs.json — skipping")

    if limit:
        packages = packages[:limit]

    return packages


def _load_install_env_config(package_name: str) -> dict[str, Any]:
    """Load the install config for a single package from install_envs.json.

    Args:
        package_name: Name of the package.

    Returns:
        The package's config dict from install_envs.json, or empty dict.
    """
    install_envs_file = ROOT_DIR / "typecheck_benchmark" / "install_envs.json"
    if not install_envs_file.exists():
        return {}

    with open(install_envs_file, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    for pkg in data.get("packages", []):
        github_url = pkg.get("github_url", "")
        if not github_url:
            continue
        name = pkg.get("name") or github_url.rstrip("/").split("/")[-1]
        if name.lower() == package_name.lower():
            return pkg

    return {}


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
            "--timeout",
            "10",  # 10 second timeout - timeouts don't count toward latency stats
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

        ok_rate = (sum(ok_counts) / total_runs * 100) if total_runs > 0 else 0.0
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
            "ok_rate": ok_rate,
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
    package_limit: int | None = None,
    package_names: list[str] | None = None,
    type_checkers: list[str] | None = None,
    runs_per_package: int = 100,
    output_dir: Path | None = None,
    seed: int | None = None,
    os_name: str | None = None,
    install_deps: bool = False,
) -> Path:
    """Run the daily benchmark suite.

    Args:
        package_limit: Maximum number of packages to benchmark.
        package_names: Specific package names to benchmark (overrides package_limit).
        type_checkers: List of type checker names to use.
        runs_per_package: Number of benchmark runs per package.
        output_dir: Directory to write results to.
        seed: Random seed for reproducibility.
        os_name: OS name to include in output filename (e.g., ubuntu, macos, windows).
        install_deps: Whether to pip-install each package's dependencies before benchmarking.

    Returns:
        Path to the output JSON file.
    """
    if type_checkers is None:
        type_checkers = DEFAULT_TYPE_CHECKERS.copy()

    if output_dir is None:
        output_dir = ROOT_DIR / "lsp" / "benchmark" / "results"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load packages from install_envs.json (single source of truth)
    packages = load_packages_from_install_envs(
        limit=package_limit,
        package_names=package_names,
    )
    if not packages:
        print("Warning: No packages found to benchmark")
        return output_dir / "empty.json"

    _print_benchmark_header(packages, type_checkers, runs_per_package)

    # Get type checker versions
    type_checker_versions = get_type_checker_versions()
    print("\nType Checker Versions:")
    for name, version in type_checker_versions.items():
        print(f"  {name}: {version}")
    print()

    all_results = _run_all_benchmarks(packages, type_checkers, runs_per_package, seed, install_deps)

    # Compute aggregate statistics
    aggregate_stats = compute_aggregate_stats(all_results, type_checkers)

    # Save results
    output_file = _save_results(
        all_results,
        aggregate_stats,
        type_checkers,
        type_checker_versions,
        len(packages),
        runs_per_package,
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
    install_deps: bool = False,
) -> list[PackageResult]:
    """Run benchmarks for all packages.

    Args:
        packages: List of packages to benchmark.
        type_checkers: List of type checkers to use.
        runs_per_package: Number of runs per package.
        seed: Random seed for reproducibility.
        install_deps: Whether to install each package's dependencies.

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
                package, github_url, temp_path, type_checkers, runs_per_package, seed,
                install_deps,
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
    install_deps: bool = False,
) -> PackageResult:
    """Benchmark a single package.

    Args:
        package: Package information.
        github_url: GitHub URL for the package.
        temp_path: Temporary directory for cloning.
        type_checkers: List of type checkers to use.
        runs_per_package: Number of runs per package.
        seed: Random seed for reproducibility.
        install_deps: Whether to install the package's dependencies.

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

    if install_deps:
        env_config = _load_install_env_config(package_name)
        has_install = env_config.get("install", False)
        has_dep_list = bool(env_config.get("deps"))
        if has_install or has_dep_list:
            from typecheck_benchmark.daily_runner import install_deps as tc_install_deps
            tc_install_deps(package_path, env_config)
        else:
            print(f"  No install config in install_envs.json for {package_name}")

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
    except Exception as e:
        print(f"  Error running benchmarks: {e}")
        return {
            "package_name": package_name,
            "github_url": github_url,
            "ranking": package.get("ranking"),
            "error": f"Benchmark failed: {e}",
            "metrics": {},
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
    runs_per_package: int,
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
        runs_per_package: Number of runs per package.
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
        "runs_per_package": runs_per_package,
        "aggregate": aggregate_stats,
        "results": results,
    }

    # Add OS to output if specified
    if os_name:
        output_data["os"] = os_name

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
    parser.add_argument(
        "--os-name",
        type=str,
        default=None,
        help="OS name to include in output filename (e.g., ubuntu, macos, windows)",
    )
    parser.add_argument(
        "--install-deps",
        action="store_true",
        default=False,
        help="Install each package's dependencies before benchmarking",
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
        runs_per_package=args.runs,
        output_dir=args.output,
        seed=args.seed,
        os_name=args.os_name,
        install_deps=args.install_deps,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
