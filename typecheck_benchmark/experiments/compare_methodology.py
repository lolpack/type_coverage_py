"""Measure the effect of each benchmark methodology change in isolation.

Two experiments, each a paired A/B on the same machine and the same checkout
so hardware noise between runners doesn't swamp the effect:

  timing  Shared environment (as on main).  A = main's runner (100ms poll
          loop), B = new runner (exact wait).  Isolates the timing fix.
  env     Exact timing in both arms.  A = shared environment with each
          checker's default discovery (as on main), B = fresh per-package
          venv passed explicitly.  Isolates the environment fix.

The shared environment on main accumulates every earlier package's installs.
To reproduce that faithfully while sharding across runners, every shard walks
the full package list in order: packages outside the shard are installed into
the shared environment (and their checkout deleted) without being benchmarked.

Measured runs alternate A/B order (AB, BA, AB, ...) to cancel drift.

Usage:
  python -m typecheck_benchmark.experiments.compare_methodology \\
      --experiment env --shard 0 --shards 3 --pairs 2 --output out.json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

from typecheck_benchmark import daily_runner as new
from typecheck_benchmark.experiments import legacy_daily_runner as legacy

# Per-checker patterns for unresolved-import diagnostics in default output.
UNRESOLVED_PATTERNS: dict[str, re.Pattern[str]] = {
    "pyright": re.compile(r'"rule":\s*"reportMissingImports"'),
    "pyrefly": re.compile(r"\[(?:missing-import|import-error)\]"),
    "ty": re.compile(r"unresolved-import"),
    "mypy": re.compile(r"\[import-not-found\]"),
    "zuban": re.compile(r"\[import-not-found\]"),
}

# Per-checker patterns for the total diagnostic count.
TOTAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "pyright": re.compile(r'"errorCount":\s*(\d+)'),
    "pyrefly": re.compile(r"INFO\s+([\d,]+)\s+errors?"),
    "ty": re.compile(r"Found\s+(\d+)\s+diagnostics?"),
    "mypy": re.compile(r"Found\s+(\d+)\s+errors?"),
    "zuban": re.compile(r"Found\s+(\d+)\s+errors?"),
}

Runner = Callable[[bool], new.TimingMetrics]


def count_diagnostics(checker: str, output: str) -> tuple[int, int | None]:
    """Return (unresolved import diagnostics, total diagnostics or None)."""
    unresolved = len(UNRESOLVED_PATTERNS[checker].findall(output))
    m = TOTAL_PATTERNS[checker].search(output)
    total = int(m.group(1).replace(",", "")) if m else None
    if total is None and checker in ("mypy", "zuban") and "Success: no issues" in output:
        total = 0
    return unresolved, total


def run_new_captured(
    checker: str, path: Path, paths: list[Path] | None, timeout: int, venv: Path | None,
) -> tuple[new.TimingMetrics, str]:
    """Run the new runner capturing output so diagnostics can be counted."""
    stash: dict[str, str] = {}
    real = new.run_process_with_timeout

    def wrapper(*args: Any, **kwargs: Any) -> new.ProcessResult:
        result = real(*args, **kwargs)
        stash["out"] = result.get("stdout", "") + result.get("stderr", "")
        return result

    with patch.object(new, "run_process_with_timeout", wrapper):
        m = new.run_checker(checker, path, paths, timeout, capture_output=True, venv=venv)
    return m, stash.get("out", "")


def resolve_check_paths(package_path: Path, pkg: dict[str, Any]) -> list[Path] | None:
    raw = pkg.get("check_paths")
    if not raw:
        return None
    existing = [package_path / p for p in raw if (package_path / p).exists()]
    return existing or None


def paired_runs(
    a: Runner, b: Runner, pairs: int,
) -> dict[str, Any]:
    """Run *pairs* measured A/B pairs, alternating order. Stops on failure."""
    times_a: list[float] = []
    times_b: list[float] = []
    mem_a: list[float] = []
    mem_b: list[float] = []
    for i in range(pairs):
        order = [("a", a), ("b", b)] if i % 2 == 0 else [("b", b), ("a", a)]
        for label, fn in order:
            m = fn(False)
            if not m.get("ok"):
                return {"ok": False, "failed_arm": label, "error": m.get("error_message")}
            (times_a if label == "a" else times_b).append(m["execution_time_s"])
            (mem_a if label == "a" else mem_b).append(m.get("peak_memory_mb", 0.0))
    return {
        "ok": True,
        "a_times": times_a,
        "b_times": times_b,
        "a_mean": statistics.mean(times_a),
        "b_mean": statistics.mean(times_b),
        "a_mem": statistics.mean(mem_a),
        "b_mem": statistics.mean(mem_b),
    }


def install_only(pkg: dict[str, Any], temp: Path) -> None:
    """Reproduce main's side effects on the shared env without benchmarking."""
    path = new.clone_package(pkg["github_url"], pkg["name"], temp)
    if path is None:
        return
    new.install_deps(path, pkg)
    shutil.rmtree(path, ignore_errors=True)


def bench_timing(
    pkg: dict[str, Any], path: Path, checkers: list[str], timeout: int, pairs: int,
) -> dict[str, Any]:
    new.install_deps(path, pkg)
    paths = resolve_check_paths(path, pkg)
    out: dict[str, Any] = {}
    for checker in checkers:
        print(f"    {checker}...", flush=True)
        warm, _ = run_new_captured(checker, path, paths, timeout, None)
        if not warm.get("ok"):
            out[checker] = {"ok": False, "error": warm.get("error_message")}
            print(f"      failed: {warm.get('error_message')}")
            continue

        def poll(capture: bool, c: str = checker) -> new.TimingMetrics:
            return legacy.run_checker(c, path, paths, timeout, capture_output=capture)  # type: ignore[return-value]

        def exact(capture: bool, c: str = checker) -> new.TimingMetrics:
            return new.run_checker(c, path, paths, timeout, capture_output=capture)

        r = paired_runs(poll, exact, pairs)
        out[checker] = r
        if r["ok"]:
            print(f"      poll {r['a_mean']:.3f}s  exact {r['b_mean']:.3f}s")
    return out


def bench_env(
    pkg: dict[str, Any], path: Path, temp: Path, checkers: list[str], timeout: int, pairs: int,
) -> dict[str, Any]:
    shared_ok = new.install_deps(path, pkg)
    venv = new.create_package_venv(temp / f"{pkg['name']}-venv")
    if venv is None:
        return {"_error": "venv creation failed"}
    isolated_ok = new.install_deps(path, pkg, new.venv_python(venv))
    paths = resolve_check_paths(path, pkg)
    out: dict[str, Any] = {"_install": {"shared_ok": shared_ok, "isolated_ok": isolated_ok}}
    try:
        for checker in checkers:
            print(f"    {checker}...", flush=True)
            entry: dict[str, Any] = {}
            for arm, v in (("shared", None), ("isolated", venv)):
                m, output = run_new_captured(checker, path, paths, timeout, v)
                unresolved, total = count_diagnostics(checker, output)
                entry[f"{arm}_warm_ok"] = bool(m.get("ok"))
                entry[f"{arm}_error"] = m.get("error_message")
                entry[f"{arm}_unresolved_imports"] = unresolved
                entry[f"{arm}_total_diagnostics"] = total
            if not (entry["shared_warm_ok"] and entry["isolated_warm_ok"]):
                entry["ok"] = False
                out[checker] = entry
                print(f"      failed: shared={entry['shared_error']} isolated={entry['isolated_error']}")
                continue

            def shared(capture: bool, c: str = checker) -> new.TimingMetrics:
                return new.run_checker(c, path, paths, timeout, capture_output=capture)

            def isolated(capture: bool, c: str = checker) -> new.TimingMetrics:
                return new.run_checker(c, path, paths, timeout, capture_output=capture, venv=venv)

            entry.update(paired_runs(shared, isolated, pairs))
            out[checker] = entry
            if entry["ok"]:
                print(
                    f"      shared {entry['a_mean']:.3f}s ({entry['shared_unresolved_imports']} unresolved)  "
                    f"isolated {entry['b_mean']:.3f}s ({entry['isolated_unresolved_imports']} unresolved)"
                )
    finally:
        shutil.rmtree(venv, ignore_errors=True)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--experiment", choices=["timing", "env"], required=True)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    parser.add_argument("--pairs", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=new.DEFAULT_TIMEOUT)
    parser.add_argument("--checkers", nargs="+", default=new.DEFAULT_TYPE_CHECKERS)
    parser.add_argument("--package-names", nargs="+", default=None,
                        help="Only benchmark these (others are still installed in order)")
    parser.add_argument("--install-envs", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    packages = new.load_install_envs(args.install_envs)
    checkers = [c for c in args.checkers if new.is_type_checker_available(c)]
    versions = {k: v for k, v in new.get_type_checker_versions().items() if k in checkers}
    print(f"Experiment: {args.experiment}  shard {args.shard}/{args.shards}  checkers: {versions}")

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        selected = set(args.package_names) if args.package_names else None
        last_selected = max(
            (i for i, p in enumerate(packages)
             if (selected is None and i % args.shards == args.shard)
             or (selected is not None and p["name"] in selected)),
            default=-1,
        )
        for i, pkg in enumerate(packages):
            if i > last_selected:
                break
            mine = (pkg["name"] in selected) if selected is not None else (i % args.shards == args.shard)
            if not mine:
                print(f"[{i + 1}/{len(packages)}] {pkg['name']} (install only)", flush=True)
                install_only(pkg, temp)
                continue
            print(f"[{i + 1}/{len(packages)}] {pkg['name']}", flush=True)
            path = new.clone_package(pkg["github_url"], pkg["name"], temp)
            if path is None:
                results.append({"package": pkg["name"], "index": i, "error": "clone failed"})
                continue
            try:
                if args.experiment == "timing":
                    metrics = bench_timing(pkg, path, checkers, args.timeout, args.pairs)
                else:
                    metrics = bench_env(pkg, path, temp, checkers, args.timeout, args.pairs)
            finally:
                shutil.rmtree(path, ignore_errors=True)
            results.append({"package": pkg["name"], "index": i, "metrics": metrics})
            # Write incrementally so a job timeout still leaves partial data
            _write(args, versions, checkers, results)

    _write(args, versions, checkers, results)
    return 0


def _write(args: argparse.Namespace, versions: dict[str, str], checkers: list[str], results: list[dict[str, Any]]) -> None:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({
            "experiment": args.experiment,
            "shard": args.shard,
            "shards": args.shards,
            "pairs": args.pairs,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": sys.platform,
            "versions": versions,
            "checkers": checkers,
            "results": results,
        }, f, indent=2)


if __name__ == "__main__":
    sys.exit(main())
