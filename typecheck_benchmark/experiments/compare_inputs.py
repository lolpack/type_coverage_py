"""Measure the effect of the checker-input changes, one at a time.

Paired A/B on the same machine and checkout, alternating order:

  tests  #2: one venv per package, installed as before. A = previous runner
         (tests checked by four checkers), B = new runner (tests excluded for
         every checker).
  deps   #3: A = previous install behavior and config, B = best-effort install
         (deps installed even if the package's own install fails, aiohttp via
         its runtime deps). Both checked by the new runner.
  combo  A = PR 1 + PR 2 as they stand (install and runner), B = this branch
         (mypy checks test code too, best-effort installs). Separate venvs.

Output fields follow the env experiment's naming (shared_* = arm A,
isolated_* = arm B) so summarize_comparison can report them.

Usage:
  python -m typecheck_benchmark.experiments.compare_inputs \\
      --experiment tests --shard 0 --shards 4 --pairs 2 --output out.json
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
from typecheck_benchmark.experiments import before_daily_runner as before

BEFORE_ENVS = Path(__file__).parent / "before_install_envs.json"

UNRESOLVED_PATTERNS: dict[str, re.Pattern[str]] = {
    "pyright": re.compile(r'"rule":\s*"reportMissingImports"'),
    "pyrefly": re.compile(r"\[(?:missing-import|import-error)\]"),
    "ty": re.compile(r"unresolved-import"),
    "mypy": re.compile(r"\[import-not-found\]"),
    "zuban": re.compile(r"\[import-not-found\]"),
}
TOTAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "pyright": re.compile(r'"errorCount":\s*(\d+)'),
    "pyrefly": re.compile(r"INFO\s+([\d,]+)\s+errors?"),
    "ty": re.compile(r"Found\s+(\d+)\s+diagnostics?"),
    "mypy": re.compile(r"Found\s+(\d+)\s+errors?"),
    "zuban": re.compile(r"Found\s+(\d+)\s+errors?"),
}

Runner = Callable[[bool], dict[str, Any]]


def count_diagnostics(checker: str, output: str) -> tuple[int, int | None]:
    unresolved = len(UNRESOLVED_PATTERNS[checker].findall(output))
    m = TOTAL_PATTERNS[checker].search(output)
    total = int(m.group(1).replace(",", "")) if m else None
    if total is None and checker in ("mypy", "zuban") and "Success: no issues" in output:
        total = 0
    return unresolved, total


def run_captured(module: Any, checker: str, path: Path, paths: list[Path] | None,
                 timeout: int, venv: Path) -> tuple[dict[str, Any], str]:
    """Run *module*.run_checker capturing output so diagnostics can be counted."""
    stash: dict[str, str] = {}
    real = module.run_process_with_timeout

    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = real(*args, **kwargs)
        stash["out"] = result.get("stdout", "") + result.get("stderr", "")
        return result

    with patch.object(module, "run_process_with_timeout", wrapper):
        m = module.run_checker(checker, path, paths, timeout, capture_output=True, venv=venv)
    return m, stash.get("out", "")


def resolve_check_paths(package_path: Path, pkg: dict[str, Any]) -> list[Path] | None:
    raw = pkg.get("check_paths")
    if not raw:
        return None
    existing = [package_path / p for p in raw if (package_path / p).exists()]
    return existing or None


def paired_runs(a: Runner, b: Runner, pairs: int) -> dict[str, Any]:
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
    return {"ok": True, "a_times": times_a, "b_times": times_b,
            "a_mean": statistics.mean(times_a), "b_mean": statistics.mean(times_b),
            "a_mem": statistics.mean(mem_a), "b_mem": statistics.mean(mem_b)}


def compare(
    path: Path, paths: list[Path] | None, checkers: list[str], timeout: int, pairs: int,
    arm_a: tuple[Any, Path], arm_b: tuple[Any, Path],
) -> dict[str, Any]:
    """Run every checker under arm A and arm B: (runner module, venv) each."""
    out: dict[str, Any] = {}
    for checker in checkers:
        print(f"    {checker}...", flush=True)
        entry: dict[str, Any] = {}
        for prefix, (module, venv) in (("shared", arm_a), ("isolated", arm_b)):
            m, output = run_captured(module, checker, path, paths, timeout, venv)
            unresolved, total = count_diagnostics(checker, output)
            entry[f"{prefix}_warm_ok"] = bool(m.get("ok"))
            entry[f"{prefix}_error"] = m.get("error_message")
            entry[f"{prefix}_unresolved_imports"] = unresolved
            entry[f"{prefix}_total_diagnostics"] = total
        if not (entry["shared_warm_ok"] and entry["isolated_warm_ok"]):
            entry["ok"] = False
            out[checker] = entry
            print(f"      failed: A={entry['shared_error']} B={entry['isolated_error']}")
            continue

        def run_a(capture: bool, c: str = checker) -> dict[str, Any]:
            return arm_a[0].run_checker(c, path, paths, timeout, capture_output=capture, venv=arm_a[1])

        def run_b(capture: bool, c: str = checker) -> dict[str, Any]:
            return arm_b[0].run_checker(c, path, paths, timeout, capture_output=capture, venv=arm_b[1])

        entry.update(paired_runs(run_a, run_b, pairs))
        out[checker] = entry
        if entry["ok"]:
            print(f"      A {entry['a_mean']:.3f}s ({entry['shared_unresolved_imports']} unresolved, "
                  f"{entry['shared_total_diagnostics']} diags)  "
                  f"B {entry['b_mean']:.3f}s ({entry['isolated_unresolved_imports']} unresolved, "
                  f"{entry['isolated_total_diagnostics']} diags)")
    return out


def bench_tests(pkg: dict[str, Any], old_pkg: dict[str, Any], path: Path, temp: Path,
                checkers: list[str], timeout: int, pairs: int) -> dict[str, Any]:
    venv = new.create_package_venv(temp / f"{pkg['name']}-venv")
    if venv is None:
        return {"_error": "venv creation failed"}
    try:
        ok = before.install_deps(path, old_pkg, new.venv_python(venv))
        result = compare(path, resolve_check_paths(path, pkg), checkers, timeout, pairs,
                         (before, venv), (new, venv))
        result["_install"] = {"shared_ok": ok, "isolated_ok": ok}
        return result
    finally:
        shutil.rmtree(venv, ignore_errors=True)


def bench_deps(pkg: dict[str, Any], old_pkg: dict[str, Any], path: Path, temp: Path,
               checkers: list[str], timeout: int, pairs: int) -> dict[str, Any]:
    venv_a = new.create_package_venv(temp / f"{pkg['name']}-venv-a")
    venv_b = new.create_package_venv(temp / f"{pkg['name']}-venv-b")
    if venv_a is None or venv_b is None:
        return {"_error": "venv creation failed"}
    try:
        ok_a = before.install_deps(path, old_pkg, new.venv_python(venv_a))
        ok_b = new.install_deps(path, pkg, new.venv_python(venv_b))
        result = compare(path, resolve_check_paths(path, pkg), checkers, timeout, pairs,
                         (new, venv_a), (new, venv_b))
        result["_install"] = {"shared_ok": ok_a, "isolated_ok": ok_b}
        return result
    finally:
        shutil.rmtree(venv_a, ignore_errors=True)
        shutil.rmtree(venv_b, ignore_errors=True)


def bench_combo(pkg: dict[str, Any], old_pkg: dict[str, Any], path: Path, temp: Path,
                checkers: list[str], timeout: int, pairs: int) -> dict[str, Any]:
    venv_a = new.create_package_venv(temp / f"{pkg['name']}-venv-a")
    venv_b = new.create_package_venv(temp / f"{pkg['name']}-venv-b")
    if venv_a is None or venv_b is None:
        return {"_error": "venv creation failed"}
    try:
        ok_a = before.install_deps(path, old_pkg, new.venv_python(venv_a))
        ok_b = new.install_deps(path, pkg, new.venv_python(venv_b))
        result = compare(path, resolve_check_paths(path, pkg), checkers, timeout, pairs,
                         (before, venv_a), (new, venv_b))
        result["_install"] = {"shared_ok": ok_a, "isolated_ok": ok_b}
        return result
    finally:
        shutil.rmtree(venv_a, ignore_errors=True)
        shutil.rmtree(venv_b, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--experiment", choices=["tests", "deps", "combo"], required=True)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    parser.add_argument("--pairs", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=new.DEFAULT_TIMEOUT)
    parser.add_argument("--checkers", nargs="+", default=new.DEFAULT_TYPE_CHECKERS)
    parser.add_argument("--package-names", nargs="+", default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    packages = new.load_install_envs()
    old_by_name = {p["name"]: p for p in new.load_install_envs(BEFORE_ENVS)}
    if args.package_names:
        packages = [p for p in packages if p["name"] in set(args.package_names)]
    mine = [p for i, p in enumerate(packages) if i % args.shards == args.shard]
    checkers = [c for c in args.checkers if new.is_type_checker_available(c)]
    versions = {k: v for k, v in new.get_type_checker_versions().items() if k in checkers}
    print(f"Experiment: {args.experiment}  shard {args.shard}/{args.shards}  "
          f"{len(mine)} packages  checkers: {versions}", flush=True)
    bench = {"tests": bench_tests, "deps": bench_deps, "combo": bench_combo}[args.experiment]

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        for pkg in mine:
            index = next(i for i, p in enumerate(new.load_install_envs()) if p["name"] == pkg["name"])
            print(f"[{index + 1}] {pkg['name']}", flush=True)
            path = new.clone_package(pkg["github_url"], pkg["name"], temp)
            if path is None:
                results.append({"package": pkg["name"], "index": index, "error": "clone failed"})
                continue
            try:
                metrics = bench(pkg, old_by_name.get(pkg["name"], pkg), path, temp,
                                checkers, args.timeout, args.pairs)
            finally:
                shutil.rmtree(path, ignore_errors=True)
            results.append({"package": pkg["name"], "index": index, "metrics": metrics})
            _write(args, versions, checkers, results)
    _write(args, versions, checkers, results)
    return 0


def _write(args: argparse.Namespace, versions: dict[str, str], checkers: list[str],
           results: list[dict[str, Any]]) -> None:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({
            "experiment": args.experiment, "shard": args.shard, "shards": args.shards,
            "pairs": args.pairs, "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": sys.platform, "versions": versions, "checkers": checkers,
            "results": results,
        }, f, indent=2)


if __name__ == "__main__":
    sys.exit(main())
