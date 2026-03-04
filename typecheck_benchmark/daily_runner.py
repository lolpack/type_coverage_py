#!/usr/bin/env python3
"""Daily runner for type checker timing benchmarks.

This script measures execution time and memory usage of type checkers
(pyright, pyrefly, ty, mypy, zuban) across popular Python packages.

It does NOT measure error counts or false positives/negatives -- only
wall-clock latency and peak RSS memory per type checker per package.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import resource
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence, TypedDict

ROOT_DIR: Path = Path(__file__).parent

# The 5 type checkers to benchmark
DEFAULT_TYPE_CHECKERS: list[str] = ["pyright", "pyrefly", "ty", "mypy", "zuban"]

# Timeout per type checker invocation (seconds)
DEFAULT_TIMEOUT: int = 300

# Max RSS before killing (MB). Ubuntu CI has 7GB; 4GB leaves headroom.
DEFAULT_MEMORY_LIMIT_MB: int = 4096


# ---------------------------------------------------------------------------
# TypedDicts for structured output
# ---------------------------------------------------------------------------


class TimingMetrics(TypedDict, total=False):
    """Timing metrics for a single type checker run on a single package."""

    ok: bool
    execution_time_s: float
    peak_memory_mb: float
    error_message: str | None


class PackageResult(TypedDict, total=False):
    """Result of benchmarking a single package."""

    package_name: str
    github_url: str | None
    error: str | None
    metrics: dict[str, TimingMetrics]


class AggregateStats(TypedDict, total=False):
    """Aggregate statistics for one type checker across all packages."""

    packages_tested: int
    packages_failed: int
    avg_execution_time_s: float
    p50_execution_time_s: float
    p90_execution_time_s: float
    p95_execution_time_s: float
    max_execution_time_s: float
    total_execution_time_s: float
    avg_peak_memory_mb: float
    p90_peak_memory_mb: float
    p95_peak_memory_mb: float
    max_peak_memory_mb: float


class BenchmarkOutput(TypedDict):
    """Top-level JSON output."""

    timestamp: str
    date: str
    type_checkers: list[str]
    type_checker_versions: dict[str, str]
    package_count: int
    aggregate: dict[str, AggregateStats]
    results: list[PackageResult]


class ProcessResult(TypedDict, total=False):
    """Result from a subprocess run."""

    stdout: str
    stderr: str
    returncode: int
    timed_out: bool
    execution_time_s: float
    peak_memory_mb: float
    oom_killed: bool


# ---------------------------------------------------------------------------
# Subprocess execution with memory monitoring
# ---------------------------------------------------------------------------


def _monitor_memory_linux(
    pid: int,
    peak_kb: list[int],
    stop_event: threading.Event,
    memory_limit_kb: int = 0,
    killed: list[bool] | None = None,
) -> None:
    """Poll /proc/{pid}/status for VmHWM (peak RSS) on Linux."""
    status_path = f"/proc/{pid}/status"
    while not stop_event.is_set():
        try:
            vm_hwm = 0
            vm_rss = 0
            with open(status_path) as f:
                for line in f:
                    if line.startswith("VmHWM:"):
                        vm_hwm = int(line.split()[1])
                    elif line.startswith("VmRSS:"):
                        vm_rss = int(line.split()[1])
            if vm_hwm > peak_kb[0]:
                peak_kb[0] = vm_hwm
            if memory_limit_kb > 0 and vm_rss > memory_limit_kb:
                if killed is not None:
                    killed[0] = True
                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
                break
        except (FileNotFoundError, ProcessLookupError, OSError):
            break
        stop_event.wait(0.01)


def _get_peak_memory_macos(pid: int) -> float:
    """Get peak memory for a process on macOS using ps."""
    try:
        result = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip()) / 1024  # KB -> MB
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return 0.0


def run_process_with_timeout(
    cmd: list[str],
    cwd: Path,
    timeout: int,
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
) -> ProcessResult:
    """Run a process with timeout and memory monitoring.

    Returns timing and memory information.
    """
    start_time = time.time()

    kwargs: dict[str, Any] = {
        "cwd": cwd,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if sys.platform != "win32":
        kwargs["start_new_session"] = True

    process = subprocess.Popen(cmd, **kwargs)

    # Memory monitoring thread (Linux only for /proc-based monitoring)
    peak_kb: list[int] = [0]
    killed: list[bool] = [False]
    stop_event = threading.Event()
    monitor_thread: threading.Thread | None = None
    if sys.platform == "linux":
        memory_limit_kb = memory_limit_mb * 1024 if memory_limit_mb > 0 else 0
        monitor_thread = threading.Thread(
            target=_monitor_memory_linux,
            args=(process.pid, peak_kb, stop_event, memory_limit_kb, killed),
            daemon=True,
        )
        monitor_thread.start()

    # Read stdout/stderr in background threads
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    def _read_stdout() -> None:
        try:
            stdout_chunks.append(process.stdout.read())  # type: ignore[union-attr]
        except (ValueError, OSError):
            pass

    def _read_stderr() -> None:
        try:
            stderr_chunks.append(process.stderr.read())  # type: ignore[union-attr]
        except (ValueError, OSError):
            pass

    reader_out = threading.Thread(target=_read_stdout, daemon=True)
    reader_err = threading.Thread(target=_read_stderr, daemon=True)
    reader_out.start()
    reader_err.start()

    # Poll until process exits, timeout, or OOM kill
    deadline = start_time + timeout
    while True:
        if process.poll() is not None:
            break
        if killed[0]:
            break
        if time.time() >= deadline:
            break
        time.sleep(0.1)

    execution_time = time.time() - start_time
    timed_out = False
    oom_killed = killed[0]

    if process.poll() is None and not oom_killed:
        timed_out = True
        if sys.platform != "win32":
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
        else:
            process.kill()

    # Close pipes so reader threads unblock
    for pipe in (process.stdout, process.stderr):
        try:
            pipe.close()  # type: ignore[union-attr]
        except OSError:
            pass

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass

    stop_event.set()
    if monitor_thread is not None:
        monitor_thread.join(timeout=2)

    reader_out.join(timeout=5)
    reader_err.join(timeout=5)

    # Compute peak memory
    if sys.platform == "linux":
        peak_memory_mb = round(peak_kb[0] / 1024, 1)
    elif sys.platform == "darwin":
        # On macOS, use getrusage for child processes
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        peak_memory_mb = round(usage.ru_maxrss / (1024 * 1024), 1)  # bytes -> MB
    else:
        peak_memory_mb = 0.0

    if oom_killed or timed_out:
        return {
            "stdout": "",
            "stderr": "",
            "returncode": -1,
            "timed_out": timed_out,
            "execution_time_s": round(execution_time, 2),
            "peak_memory_mb": peak_memory_mb,
            "oom_killed": oom_killed,
        }

    return {
        "stdout": stdout_chunks[0] if stdout_chunks else "",
        "stderr": stderr_chunks[0] if stderr_chunks else "",
        "returncode": process.returncode,
        "timed_out": False,
        "execution_time_s": round(execution_time, 2),
        "peak_memory_mb": peak_memory_mb,
        "oom_killed": False,
    }


# ---------------------------------------------------------------------------
# Package loading from install_envs.json
# ---------------------------------------------------------------------------


def load_install_envs(
    install_envs_file: Path | None = None,
) -> list[dict[str, Any]]:
    """Load packages from install_envs.json.

    Returns only packages that have install: true or a non-empty deps list.
    """
    if install_envs_file is None:
        install_envs_file = ROOT_DIR / "install_envs.json"

    if not install_envs_file.exists():
        print(f"Error: {install_envs_file} not found")
        return []

    with open(install_envs_file, encoding="utf-8") as f:
        data = json.load(f)

    packages: list[dict[str, Any]] = []
    for pkg in data.get("packages", []):
        github_url = pkg.get("github_url", "")
        if not github_url:
            continue
        # Only include packages that have install config
        has_install = pkg.get("install", False)
        has_deps = bool(pkg.get("deps"))
        if not has_install and not has_deps:
            continue
        # Derive name from explicit field or github URL
        name = pkg.get("name") or github_url.rstrip("/").split("/")[-1]
        packages.append({**pkg, "name": name})

    return packages


# ---------------------------------------------------------------------------
# Type checker version detection
# ---------------------------------------------------------------------------


def get_type_checker_versions() -> dict[str, str]:
    """Get version strings for all type checkers."""
    versions: dict[str, str] = {}
    version_commands: dict[str, list[str]] = {
        "pyright": ["pyright", "--version"],
        "pyrefly": ["pyrefly", "--version"],
        "ty": ["ty", "--version"],
        "mypy": ["mypy", "--version"],
        "zuban": ["zuban", "--version"],
    }
    for name, cmd in version_commands.items():
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            output = result.stdout.strip() or result.stderr.strip()
            if output:
                match = re.search(r"\d+\.\d+\.\d+", output)
                if match:
                    versions[name] = match.group(0)
                else:
                    parts = output.split()
                    versions[name] = parts[1] if len(parts) > 1 else parts[0]
            else:
                versions[name] = "unknown"
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            versions[name] = "not installed"
    return versions


# ---------------------------------------------------------------------------
# Type checker availability
# ---------------------------------------------------------------------------


def is_type_checker_available(checker: str) -> bool:
    """Check if a type checker binary is available on PATH."""
    if checker == "mypy":
        result = subprocess.run(
            [sys.executable, "-c", "import mypy"],
            capture_output=True,
        )
        return result.returncode == 0

    cmd_map: dict[str, str] = {
        "pyright": "pyright",
        "pyrefly": "pyrefly",
        "ty": "ty",
        "zuban": "zuban",
    }
    binary = cmd_map.get(checker)
    if not binary:
        return False
    which_cmd = "where" if sys.platform == "win32" else "which"
    result = subprocess.run([which_cmd, binary], capture_output=True)
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Cloning and dependency installation
# ---------------------------------------------------------------------------


def clone_package(
    github_url: str,
    name: str,
    dest: Path,
    timeout: int = 180,
) -> Path | None:
    """Shallow-clone a GitHub repository."""
    target = dest / name
    try:
        print(f"  Cloning {github_url}...")
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", github_url, str(target)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            print(f"  Failed to clone: {result.stderr[:200]}")
            return None
        return target
    except subprocess.TimeoutExpired:
        print(f"  Timeout cloning {github_url}")
        return None
    except Exception as e:
        print(f"  Error cloning: {e}")
        return None


def install_deps(package_path: Path, env_config: dict[str, Any]) -> bool:
    """Install dependencies for a package."""
    install_self = env_config.get("install", False)
    deps = env_config.get("deps", [])
    install_env = env_config.get("install_env", {})

    env = os.environ.copy()
    env.update(install_env)

    if install_self:
        print(f"  Installing package (pip install -e .)")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", "."],
                cwd=package_path,
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
            )
            if result.returncode != 0:
                print(f"  Warning: pip install -e . failed: {result.stderr[:200]}")
                return False
        except subprocess.TimeoutExpired:
            print(f"  Warning: pip install -e . timed out")
            return False

    if deps:
        print(f"  Installing deps: {', '.join(deps[:5])}{'...' if len(deps) > 5 else ''}")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install"] + deps,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                print(f"  Warning: pip install deps failed: {result.stderr[:200]}")
                return False
        except subprocess.TimeoutExpired:
            print(f"  Warning: pip install deps timed out")
            return False

    return True


# ---------------------------------------------------------------------------
# Type checker runners (timing-only -- we don't parse error output)
# ---------------------------------------------------------------------------
# Dummy config methodology:
# Many packages ship their own type checker configs (mypy.ini, pyrightconfig.json,
# pyproject.toml [tool.*] sections, etc.) that can change strictness, enable/disable
# checks, or alter behavior in ways that skew benchmark comparisons.
#
# To ensure consistent benchmarking across packages, we write minimal config files
# that embed the check_paths (from install_envs.json) directly into each checker's
# native config format, then pass the config via CLI flag to override package-level
# config.  This means paths are NOT passed as CLI arguments — they live in the config:
#
#   pyright  -- pyrightconfig.json with "include": [paths] (written in-place)
#   mypy     -- [mypy] section with files = path1, path2 via --config-file
#   ty       -- [src] include = [paths] in ty.benchmark.toml via --config-file
#   pyrefly  -- project_includes = [paths] in pyrefly.benchmark.toml via --config
#   zuban    -- [mypy] section with files = path1, path2 via --config-file
# ---------------------------------------------------------------------------


def _write_dummy_pyright_config(
    package_path: Path, check_paths: list[str] | None = None,
) -> None:
    """Write minimal pyrightconfig.json for consistent benchmarking."""
    config = {
        "include": check_paths or ["."],
        "exclude": [],
        "typeCheckingMode": "basic",
        "useLibraryCodeForTypes": True,
    }
    with open(package_path / "pyrightconfig.json", "w", encoding="utf-8") as f:
        json.dump(config, f)


def _write_dummy_mypy_config(
    package_path: Path, check_paths: list[str] | None = None,
) -> Path:
    """Write minimal mypy config for consistent benchmarking."""
    config_path = package_path / "mypy.benchmark.ini"
    with open(config_path, "w", encoding="utf-8") as f:
        f.write("[mypy]\n")
        if check_paths:
            f.write(f"files = {', '.join(check_paths)}\n")
    return config_path


def _write_dummy_ty_config(
    package_path: Path, check_paths: list[str] | None = None,
) -> Path:
    """Write minimal ty.toml for consistent benchmarking."""
    config_path = package_path / "ty.benchmark.toml"
    with open(config_path, "w", encoding="utf-8") as f:
        if check_paths:
            f.write("[src]\n")
            paths_toml = ", ".join(f'"{p}"' for p in check_paths)
            f.write(f"include = [{paths_toml}]\n")
    return config_path


def _write_dummy_pyrefly_config(
    package_path: Path, check_paths: list[str] | None = None,
) -> Path:
    """Write minimal pyrefly.toml for consistent benchmarking."""
    config_path = package_path / "pyrefly.benchmark.toml"
    with open(config_path, "w", encoding="utf-8") as f:
        if check_paths:
            paths_toml = ", ".join(f'"{p}"' for p in check_paths)
            f.write(f"project_includes = [{paths_toml}]\n")
    return config_path


def _write_dummy_zuban_config(
    package_path: Path, check_paths: list[str] | None = None,
) -> Path:
    """Write minimal mypy-style config for zuban benchmarking."""
    config_path = package_path / "mypy.benchmark.ini"
    with open(config_path, "w", encoding="utf-8") as f:
        f.write("[mypy]\n")
        if check_paths:
            f.write(f"files = {', '.join(check_paths)}\n")
    return config_path


def run_checker(
    checker: str,
    package_path: Path,
    check_paths: list[Path] | None,
    timeout: int,
) -> TimingMetrics:
    """Run a single type checker and return timing metrics only."""
    # Convert absolute check_paths to relative strings from package root
    rel_paths: list[str] | None = None
    if check_paths:
        rel_paths = [
            str(p.relative_to(package_path)) if p.is_absolute() else str(p)
            for p in check_paths
        ]

    if checker == "pyright":
        _write_dummy_pyright_config(package_path, rel_paths)
        cmd = ["pyright", "--outputjson"]
        cwd = package_path
    elif checker == "pyrefly":
        config_path = _write_dummy_pyrefly_config(package_path, rel_paths)
        cmd = ["pyrefly", "check", "--config", str(config_path)]
        cwd = package_path
    elif checker == "ty":
        config_path = _write_dummy_ty_config(package_path, rel_paths)
        cmd = ["ty", "check", "--config-file", str(config_path)]
        cwd = package_path
    elif checker == "mypy":
        config_path = _write_dummy_mypy_config(package_path, rel_paths)
        cmd = [sys.executable, "-m", "mypy", "--config-file", str(config_path)]
        # mypy needs explicit paths if no files= in config; when check_paths
        # are embedded in the config via files=, we still pass "." so mypy
        # has a target (it requires at least one positional arg or files=).
        if not rel_paths:
            cmd.append(str(package_path))
        cwd = package_path
    elif checker == "zuban":
        config_path = _write_dummy_zuban_config(package_path, rel_paths)
        cmd = ["zuban", "check", "--config-file", str(config_path)]
        if not rel_paths:
            cmd.append(".")
        cwd = package_path
    else:
        return {
            "ok": False,
            "execution_time_s": 0.0,
            "peak_memory_mb": 0.0,
            "error_message": f"Unknown checker: {checker}",
        }

    result = run_process_with_timeout(cmd, cwd=cwd, timeout=timeout)

    if result["timed_out"] or result.get("oom_killed"):
        msg = "OOM killed" if result.get("oom_killed") else "Timeout"
        peak = result.get("peak_memory_mb", 0)
        if result.get("oom_killed") and peak > 0:
            msg = f"OOM killed ({peak:.0f}MB)"
        return {
            "ok": False,
            "execution_time_s": result["execution_time_s"],
            "peak_memory_mb": result.get("peak_memory_mb", 0.0),
            "error_message": msg,
        }

    return {
        "ok": True,
        "execution_time_s": result["execution_time_s"],
        "peak_memory_mb": result.get("peak_memory_mb", 0.0),
    }


# ---------------------------------------------------------------------------
# Aggregate statistics
# ---------------------------------------------------------------------------


def compute_percentile(values: Sequence[float | int], percentile: float) -> float:
    """Compute the given percentile of a list of values."""
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
    """Compute aggregate timing statistics across all packages."""
    stats: dict[str, AggregateStats] = {}

    for checker in type_checkers:
        times: list[float] = []
        memories: list[float] = []
        packages_tested = 0
        packages_failed = 0

        for result in results:
            if result.get("error"):
                continue
            metrics = result.get("metrics", {}).get(checker)
            if not metrics:
                continue
            if not metrics.get("ok"):
                packages_failed += 1
                continue
            packages_tested += 1
            times.append(metrics["execution_time_s"])
            mem = metrics.get("peak_memory_mb", 0.0)
            if mem > 0:
                memories.append(mem)

        stats[checker] = {
            "packages_tested": packages_tested,
            "packages_failed": packages_failed,
            "avg_execution_time_s": round(sum(times) / len(times), 2) if times else 0.0,
            "p50_execution_time_s": round(compute_percentile(times, 50), 2),
            "p90_execution_time_s": round(compute_percentile(times, 90), 2),
            "p95_execution_time_s": round(compute_percentile(times, 95), 2),
            "max_execution_time_s": round(max(times), 2) if times else 0.0,
            "total_execution_time_s": round(sum(times), 2),
            "avg_peak_memory_mb": round(sum(memories) / len(memories), 1) if memories else 0.0,
            "p90_peak_memory_mb": round(compute_percentile(memories, 90), 1),
            "p95_peak_memory_mb": round(compute_percentile(memories, 95), 1),
            "max_peak_memory_mb": round(max(memories), 1) if memories else 0.0,
        }

    return stats


# ---------------------------------------------------------------------------
# Main benchmark orchestration
# ---------------------------------------------------------------------------


def run_benchmark(
    package_limit: int | None = None,
    package_names: list[str] | None = None,
    type_checkers: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    output_dir: Path | None = None,
    os_name: str | None = None,
    install_envs_file: Path | None = None,
) -> Path:
    """Run the full benchmark suite.

    Args:
        package_limit: Max packages to benchmark.
        package_names: Specific package names to benchmark.
        type_checkers: Type checkers to run.
        timeout: Per-checker timeout in seconds.
        output_dir: Where to write JSON results.
        os_name: OS name for filename (ubuntu, macos, windows).
        install_envs_file: Path to install_envs.json.

    Returns:
        Path to the dated output JSON file.
    """
    if type_checkers is None:
        type_checkers = DEFAULT_TYPE_CHECKERS.copy()
    if output_dir is None:
        output_dir = ROOT_DIR / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load packages
    packages = load_install_envs(install_envs_file)
    if not packages:
        print("Error: No packages found in install_envs.json")
        return output_dir / "empty.json"

    if package_names:
        name_set = set(package_names)
        packages = [p for p in packages if p["name"] in name_set]
        if not packages:
            print(f"Warning: None of the specified packages found: {package_names}")
            return output_dir / "empty.json"
    elif package_limit:
        packages = packages[:package_limit]

    # Header
    print("=" * 70)
    print("Type Checker Timing Benchmark")
    print("=" * 70)
    print(f"Packages: {len(packages)}")
    print(f"Type checkers: {', '.join(type_checkers)}")
    print(f"Timeout: {timeout}s per checker")
    print("=" * 70)

    # Versions
    versions = get_type_checker_versions()
    print("\nType Checker Versions:")
    for name, version in versions.items():
        if name in type_checkers:
            print(f"  {name}: {version}")
    print()

    # Run benchmarks
    all_results = _run_all(packages, type_checkers, timeout)

    # Aggregate
    aggregate = compute_aggregate_stats(all_results, type_checkers)

    # Save
    output_file = _save_results(
        all_results, aggregate, type_checkers, versions, len(packages),
        output_dir, os_name,
    )

    # Print summary
    print("\n" + "=" * 70)
    print("Benchmark Complete!")
    print("=" * 70)
    _print_summary(aggregate, type_checkers)
    print(f"\nResults saved to: {output_file}")

    return output_file


def _run_all(
    packages: list[dict[str, Any]],
    type_checkers: list[str],
    timeout: int,
) -> list[PackageResult]:
    """Run benchmarks for all packages."""
    all_results: list[PackageResult] = []

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        for i, pkg in enumerate(packages, 1):
            name = pkg["name"]
            github_url = pkg.get("github_url", "")

            print(f"\n[{i}/{len(packages)}] {name}")

            result = _benchmark_package(pkg, temp_path, type_checkers, timeout)
            all_results.append(result)

    return all_results


def _benchmark_package(
    pkg: dict[str, Any],
    temp_path: Path,
    type_checkers: list[str],
    timeout: int,
) -> PackageResult:
    """Benchmark a single package: clone, install deps, run checkers."""
    name = pkg["name"]
    github_url = pkg.get("github_url", "")

    if not github_url:
        return {
            "package_name": name,
            "github_url": None,
            "error": "No GitHub URL",
            "metrics": {},
        }

    # Clone
    package_path = clone_package(github_url, name, temp_path)
    if not package_path:
        return {
            "package_name": name,
            "github_url": github_url,
            "error": "Failed to clone",
            "metrics": {},
        }

    # Install deps
    success = install_deps(package_path, pkg)
    if not success:
        print(f"  Warning: dependency installation had issues, continuing anyway")

    # Resolve check_paths
    resolved_paths: list[Path] | None = None
    raw_check_paths = pkg.get("check_paths")
    if raw_check_paths:
        resolved_paths = [package_path / p for p in raw_check_paths]
        existing = [p for p in resolved_paths if p.exists()]
        if existing:
            resolved_paths = existing
            rel = [str(p.relative_to(package_path)) for p in resolved_paths]
            print(f"  Checking: {rel}")
        else:
            print(f"  Warning: check_paths don't exist, using full repo")
            resolved_paths = None

    # Run type checkers
    metrics: dict[str, TimingMetrics] = {}
    for checker in type_checkers:
        if not is_type_checker_available(checker):
            print(f"    Skipping {checker}: not installed")
            metrics[checker] = {
                "ok": False,
                "execution_time_s": 0.0,
                "peak_memory_mb": 0.0,
                "error_message": "Not installed",
            }
            continue

        print(f"    Running {checker}...")
        m = run_checker(checker, package_path, resolved_paths, timeout)
        metrics[checker] = m

        if m.get("ok"):
            peak = m.get("peak_memory_mb", 0)
            mem_str = f", {peak:.0f}MB" if peak > 0 else ""
            print(f"      {m['execution_time_s']:.1f}s{mem_str}")
        else:
            print(f"      Failed: {m.get('error_message', 'Unknown')}")

    # Cleanup cloned repo
    shutil.rmtree(package_path, ignore_errors=True)

    return {
        "package_name": name,
        "github_url": github_url,
        "error": None,
        "metrics": metrics,
    }


def _save_results(
    results: list[PackageResult],
    aggregate: dict[str, AggregateStats],
    type_checkers: list[str],
    versions: dict[str, str],
    package_count: int,
    output_dir: Path,
    os_name: str | None = None,
) -> Path:
    """Save benchmark results to JSON."""
    timestamp = datetime.now(timezone.utc)
    date_str = timestamp.strftime("%Y-%m-%d")

    if os_name:
        output_file = output_dir / f"benchmark_{date_str}_{os_name}.json"
        latest_file = output_dir / f"latest-{os_name}.json"
    else:
        output_file = output_dir / f"benchmark_{date_str}.json"
        latest_file = output_dir / "latest.json"

    output_data: dict[str, Any] = {
        "timestamp": timestamp.isoformat(),
        "date": date_str,
        "type_checkers": type_checkers,
        "type_checker_versions": {k: v for k, v in versions.items() if k in type_checkers},
        "package_count": package_count,
        "aggregate": aggregate,
        "results": results,
    }
    if os_name:
        output_data["os"] = os_name

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)
    with open(latest_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print(f"  {output_file}")
    print(f"  {latest_file}")
    return output_file


def _print_summary(
    stats: dict[str, AggregateStats],
    type_checkers: list[str],
) -> None:
    """Print a summary table."""
    print(f"\n{'Checker':<12} {'Pkgs':>5} {'Avg Time':>9} {'P95 Time':>9} {'Max Time':>9} {'Avg Mem':>8} {'Max Mem':>8}")
    print("-" * 70)
    for checker in type_checkers:
        s = stats.get(checker, {})
        if s.get("packages_tested", 0) == 0:
            print(f"{checker:<12} {'N/A':>5}")
            continue
        avg_mem = s.get("avg_peak_memory_mb", 0)
        max_mem = s.get("max_peak_memory_mb", 0)
        print(
            f"{checker:<12} "
            f"{s.get('packages_tested', 0):>5} "
            f"{s.get('avg_execution_time_s', 0):>8.1f}s "
            f"{s.get('p95_execution_time_s', 0):>8.1f}s "
            f"{s.get('max_execution_time_s', 0):>8.1f}s "
            f"{avg_mem:>7.0f}M "
            f"{max_mem:>7.0f}M"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run type checker timing benchmarks across packages",
    )
    parser.add_argument(
        "--packages", "-p", type=int, default=None,
        help="Max number of packages to benchmark (default: all with install config)",
    )
    parser.add_argument(
        "--package-names", "-n", nargs="+", default=None,
        help="Specific package names to benchmark",
    )
    parser.add_argument(
        "--checkers", "-c", nargs="+", default=DEFAULT_TYPE_CHECKERS,
        help=f"Type checkers to benchmark (default: {' '.join(DEFAULT_TYPE_CHECKERS)})",
    )
    parser.add_argument(
        "--timeout", "-t", type=int, default=DEFAULT_TIMEOUT,
        help=f"Timeout per type checker in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Output directory for results",
    )
    parser.add_argument(
        "--os-name", type=str, default=None,
        help="OS name for output filename (e.g., ubuntu, macos, windows)",
    )
    parser.add_argument(
        "--install-envs", type=Path, default=None,
        help="Path to install_envs.json (default: typecheck_benchmark/install_envs.json)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)
    run_benchmark(
        package_limit=args.packages,
        package_names=args.package_names,
        type_checkers=args.checkers,
        timeout=args.timeout,
        output_dir=args.output,
        os_name=args.os_name,
        install_envs_file=args.install_envs,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
