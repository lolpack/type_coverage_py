"""Measure the effect of PR #165 (Linux peak RSS via GNU time).

Paired A/B on the same machine, checkout and venv, alternating order:
A = the runner on main (vendored as before_daily_runner), polling /proc for
VmHWM every 10ms. B = main plus #165, which runs each checker under
``/usr/bin/time -f %M`` and reads the child's peak RSS from it.

Records time, peak memory, success/failure, diagnostic counts, and the number
of source files mypy and zuban report checking.

Usage:
  python -m typecheck_benchmark.experiments.compare_prs \\
      --shard 0 --shards 4 --pairs 2 --output out.json
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

TOTAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "pyright": re.compile(r'"errorCount":\s*(\d+)'),
    "pyrefly": re.compile(r"INFO\s+([\d,]+)\s+errors?"),
    "ty": re.compile(r"Found\s+(\d+)\s+diagnostics?"),
    "mypy": re.compile(r"Found\s+(\d+)\s+errors?"),
    "zuban": re.compile(r"Found\s+(\d+)\s+errors?"),
}
# mypy and zuban: "Found 3 errors in 2 files (checked 960 source files)"
# or "Success: no issues found in 960 source files"
CHECKED_FILES = re.compile(r"(?:checked|found in)\s+([\d,]+)\s+source files?")

Runner = Callable[[bool], dict[str, Any]]


def parse_output(checker: str, output: str) -> tuple[int | None, int | None]:
    """Return (total diagnostics, checked source files) where reported."""
    m = TOTAL_PATTERNS[checker].search(output)
    total = int(m.group(1).replace(",", "")) if m else None
    if total is None and checker in ("mypy", "zuban") and "Success: no issues" in output:
        total = 0
    checked = None
    if checker in ("mypy", "zuban"):
        c = CHECKED_FILES.search(output)
        checked = int(c.group(1).replace(",", "")) if c else None
    return total, checked


def run_captured(module: Any, checker: str, path: Path, paths: list[Path] | None,
                 timeout: int, venv: Path) -> tuple[dict[str, Any], str, int | None]:
    """Run *module*.run_checker capturing output and the raw exit code."""
    stash: dict[str, Any] = {}
    real = module.run_process_with_timeout

    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = real(*args, **kwargs)
        stash["out"] = result.get("stdout", "") + result.get("stderr", "")
        stash["rc"] = result.get("returncode")
        return result

    with patch.object(module, "run_process_with_timeout", wrapper):
        m = module.run_checker(checker, path, paths, timeout, capture_output=True, venv=venv)
    return m, stash.get("out", ""), stash.get("rc")


def resolve_check_paths(package_path: Path, pkg: dict[str, Any]) -> list[Path] | None:
    raw = pkg.get("check_paths")
    if not raw:
        return None
    existing = [package_path / p for p in raw if (package_path / p).exists()]
    return existing or None


def paired_runs(a: Runner, b: Runner, pairs: int) -> dict[str, Any]:
    times: dict[str, list[float]] = {"a": [], "b": []}
    mem: dict[str, list[float]] = {"a": [], "b": []}
    for i in range(pairs):
        order = [("a", a), ("b", b)] if i % 2 == 0 else [("b", b), ("a", a)]
        for label, fn in order:
            m = fn(False)
            if not m.get("ok"):
                return {"ok": False, "failed_arm": label, "error": m.get("error_message")}
            times[label].append(m["execution_time_s"])
            mem[label].append(m.get("peak_memory_mb", 0.0))
    return {"ok": True, "a_times": times["a"], "b_times": times["b"],
            "a_mem_runs": mem["a"], "b_mem_runs": mem["b"],
            "a_mean": statistics.mean(times["a"]), "b_mean": statistics.mean(times["b"]),
            "a_mem": statistics.mean(mem["a"]), "b_mem": statistics.mean(mem["b"])}


def compare(path: Path, paths: list[Path] | None, checkers: list[str], timeout: int,
            pairs: int, venv: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for checker in checkers:
        print(f"    {checker}...", flush=True)
        entry: dict[str, Any] = {}
        for arm, module in (("a", before), ("b", new)):
            m, output, rc = run_captured(module, checker, path, paths, timeout, venv)
            total, checked = parse_output(checker, output)
            entry[f"{arm}_warm_ok"] = bool(m.get("ok"))
            entry[f"{arm}_error"] = m.get("error_message")
            entry[f"{arm}_returncode"] = rc
            entry[f"{arm}_warm_mem"] = m.get("peak_memory_mb", 0.0)
            entry[f"{arm}_total_diagnostics"] = total
            entry[f"{arm}_checked_files"] = checked
        if not (entry["a_warm_ok"] and entry["b_warm_ok"]):
            entry["ok"] = False
            out[checker] = entry
            print(f"      failed: A={entry['a_error']} (rc {entry['a_returncode']}) "
                  f"B={entry['b_error']} (rc {entry['b_returncode']})")
            continue

        def run_a(capture: bool, c: str = checker) -> dict[str, Any]:
            return before.run_checker(c, path, paths, timeout, capture_output=capture, venv=venv)

        def run_b(capture: bool, c: str = checker) -> dict[str, Any]:
            return new.run_checker(c, path, paths, timeout, capture_output=capture, venv=venv)

        entry.update(paired_runs(run_a, run_b, pairs))
        out[checker] = entry
        if entry["ok"]:
            print(f"      A {entry['a_mean']:.3f}s {entry['a_mem']:.0f}MB "
                  f"files={entry['a_checked_files']} diags={entry['a_total_diagnostics']}  "
                  f"B {entry['b_mean']:.3f}s {entry['b_mem']:.0f}MB "
                  f"files={entry['b_checked_files']} diags={entry['b_total_diagnostics']}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    parser.add_argument("--pairs", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=new.DEFAULT_TIMEOUT)
    parser.add_argument("--checkers", nargs="+", default=new.DEFAULT_TYPE_CHECKERS)
    parser.add_argument("--package-names", nargs="+", default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    all_packages = new.load_install_envs()
    packages = all_packages
    if args.package_names:
        packages = [p for p in packages if p["name"] in set(args.package_names)]
    mine = [p for i, p in enumerate(packages) if i % args.shards == args.shard]
    checkers = [c for c in args.checkers if new.is_type_checker_available(c)]
    versions = {k: v for k, v in new.get_type_checker_versions().items() if k in checkers}
    print(f"shard {args.shard}/{args.shards}  {len(mine)} packages  checkers: {versions}", flush=True)

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        for pkg in mine:
            index = next(i for i, p in enumerate(all_packages) if p["name"] == pkg["name"])
            print(f"[{index + 1}] {pkg['name']}", flush=True)
            path = new.clone_package(pkg["github_url"], pkg["name"], temp)
            if path is None:
                results.append({"package": pkg["name"], "index": index, "error": "clone failed"})
                continue
            venv = new.create_package_venv(temp / f"{pkg['name']}-venv")
            try:
                if venv is None:
                    results.append({"package": pkg["name"], "index": index, "error": "venv creation failed"})
                    continue
                install_ok = new.install_deps(path, pkg, new.venv_python(venv))
                metrics = compare(path, resolve_check_paths(path, pkg), checkers,
                                  args.timeout, args.pairs, venv)
                results.append({"package": pkg["name"], "index": index,
                                "install_ok": install_ok, "metrics": metrics})
            finally:
                shutil.rmtree(path, ignore_errors=True)
                if venv is not None:
                    shutil.rmtree(venv, ignore_errors=True)
            _write(args, versions, checkers, results)
    _write(args, versions, checkers, results)
    return 0


def _write(args: argparse.Namespace, versions: dict[str, str], checkers: list[str],
           results: list[dict[str, Any]]) -> None:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({
            "shard": args.shard, "shards": args.shards, "pairs": args.pairs,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": sys.platform, "versions": versions, "checkers": checkers,
            "results": results,
        }, f, indent=2)


if __name__ == "__main__":
    sys.exit(main())
