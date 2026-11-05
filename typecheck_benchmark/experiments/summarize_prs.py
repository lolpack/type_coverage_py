"""Merge compare_prs shard outputs into a markdown report.

Usage:
  python -m typecheck_benchmark.experiments.summarize_prs results/*.json
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

A = "main"
B = "#165"


def load(paths: list[Path]) -> dict[str, Any]:
    merged: dict[str, Any] = {"results": []}
    for p in paths:
        data = json.loads(p.read_text())
        merged.update({k: data[k] for k in ("versions", "checkers", "pairs")})
        merged["results"].extend(data["results"])
    merged["results"].sort(key=lambda r: r["index"])
    return merged


def _pct(a: float, b: float) -> str:
    return f"{(b - a) / a * 100:+.1f}%" if a else "n/a"


def _ok_rows(results: list[dict[str, Any]], checker: str) -> list[tuple[str, dict[str, Any]]]:
    return [(r["package"], m) for r in results
            if (m := r.get("metrics", {}).get(checker)) and m.get("ok")]


def _fastest(results: list[dict[str, Any]], checkers: list[str], key: str) -> tuple[Counter[str], dict[str, str]]:
    wins: Counter[str] = Counter()
    per_pkg: dict[str, str] = {}
    for r in results:
        ms = r.get("metrics", {})
        if not all(ms.get(c, {}).get("ok") for c in checkers):
            continue
        ranked = sorted(checkers, key=lambda c: ms[c][key])
        best = "tie" if ms[ranked[0]][key] == ms[ranked[1]][key] else ranked[0]
        wins[best] += 1
        per_pkg[r["package"]] = best
    return wins, per_pkg


def _status(m: dict[str, Any], arm: str) -> str:
    if m.get(f"{arm}_warm_ok"):
        return f"ok (rc {m.get(f'{arm}_returncode')})"
    return f"{m.get(f'{arm}_error')} (rc {m.get(f'{arm}_returncode')})"


def summarize(exp: dict[str, Any]) -> str:
    checkers: list[str] = exp["checkers"]
    results: list[dict[str, Any]] = exp["results"]
    lines = [f"## {A} vs {B}", ""]
    lines.append(f"Versions: {', '.join(f'{k} {v}' for k, v in exp['versions'].items())}. "
                 f"{exp['pairs']} paired run(s) per checker per package, alternating order, same venv.")
    lines.append("")

    lines.append("### Time and peak memory (packages where both arms succeeded)")
    lines.append("")
    lines.append(f"| Checker | Pkgs | Mean time {A} | Mean time {B} | Δ | "
                 f"Mean mem {A} | Mean mem {B} | Δ | Median mem Δ per pkg |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for c in checkers:
        rows = _ok_rows(results, c)
        if not rows:
            lines.append(f"| {c} | 0 | | | | | | | |")
            continue
        ta = statistics.mean(m["a_mean"] for _, m in rows)
        tb = statistics.mean(m["b_mean"] for _, m in rows)
        ma = statistics.mean(m["a_mem"] for _, m in rows)
        mb = statistics.mean(m["b_mem"] for _, m in rows)
        dm = statistics.median(m["b_mem"] - m["a_mem"] for _, m in rows)
        lines.append(f"| {c} | {len(rows)} | {ta:.3f}s | {tb:.3f}s | {_pct(ta, tb)} | "
                     f"{ma:.0f} MB | {mb:.0f} MB | {_pct(ma, mb)} | {dm:+.1f} MB |")
    lines.append("")
    zero_a = [f"{p}/{c}" for c in checkers for p, m in _ok_rows(results, c) if 0 in m["a_mem_runs"]]
    zero_b = [f"{p}/{c}" for c in checkers for p, m in _ok_rows(results, c) if 0 in m["b_mem_runs"]]
    lines.append(f"Runs with no memory reading (0 MB): {A} {len(zero_a)}, {B} {len(zero_b)}."
                 + (f" {A}: {', '.join(zero_a)}" if zero_a else ""))
    lines.append("")

    # A shared floor (the same reading for most checkers on a package) means the
    # measurement picked up memory that isn't the checker's own.
    def _shared(arm: str) -> list[str]:
        out = []
        for r in results:
            mems = sorted(m[f"{arm}_mem"] for m in r.get("metrics", {}).values() if m.get("ok"))
            same = max((sum(1 for y in mems if abs(y - x) <= 1) for x in mems), default=0)
            if same >= 3:
                out.append(r["package"])
        return out
    shared_a, shared_b = _shared("a"), _shared("b")
    lines.append(f"Packages where 3+ checkers report the same peak memory (within 1 MB): "
                 f"{A} {len(shared_a)}, {B} {len(shared_b)}."
                 + (f" {B}: {', '.join(shared_b)}" if shared_b else ""))
    lines.append("")

    wins_a, per_a = _fastest(results, checkers, "a_mean")
    wins_b, per_b = _fastest(results, checkers, "b_mean")
    lines.append("### Fastest checker per package (packages where every checker succeeded in both arms)")
    lines.append("")
    lines.append(f"| Checker | Wins {A} | Wins {B} |")
    lines.append("|---|---|---|")
    for c in [*checkers, "tie"]:
        lines.append(f"| {c} | {wins_a.get(c, 0)} | {wins_b.get(c, 0)} |")
    lines.append("")
    flips = [(p, per_a[p], per_b[p]) for p in per_a if p in per_b and per_a[p] != per_b[p]]
    if flips:
        lines.append(f"Fastest checker changes ({len(flips)}): " +
                     ", ".join(f"{p} ({x}→{y})" for p, x, y in flips))
        lines.append("")

    lines.append("### Success/failure changes")
    lines.append("")
    changes = [(r["package"], c, m) for r in results for c in checkers
               if (m := r.get("metrics", {}).get(c)) and m.get("a_warm_ok") != m.get("b_warm_ok")]
    if changes:
        lines.append(f"| Package | Checker | {A} | {B} |")
        lines.append("|---|---|---|---|")
        for p, c, m in changes:
            lines.append(f"| {p} | {c} | {_status(m, 'a')} | {_status(m, 'b')} |")
    else:
        lines.append("None.")
    lines.append("")
    odd = [f"{r['package']}/{c} (rc {m.get('a_returncode')})" for r in results for c in checkers
           if (m := r.get("metrics", {}).get(c)) and m.get("a_warm_ok")
           and m.get("a_returncode") not in (0, 1)]
    if odd:
        lines.append(f"Counted as success on {A} despite exit code other than 0/1: {', '.join(odd)}")
        lines.append("")

    lines.append("### Files checked by zuban and mypy")
    lines.append("")
    lines.append(f"| Package | mypy {B} | zuban {A} | zuban {B} | zuban time {A} → {B} | zuban diags {A} → {B} |")
    lines.append("|---|---|---|---|---|---|")
    for r in results:
        z = r.get("metrics", {}).get("zuban")
        my = r.get("metrics", {}).get("mypy") or {}
        if not z:
            continue
        if z.get("a_checked_files") == z.get("b_checked_files") and z.get("a_warm_ok") == z.get("b_warm_ok"):
            continue
        t = f"{z['a_mean']:.3f}s → {z['b_mean']:.3f}s" if z.get("ok") else "failed"
        lines.append(f"| {r['package']} | {my.get('b_checked_files')} | {z.get('a_checked_files')} | "
                     f"{z.get('b_checked_files')} | {t} | "
                     f"{z.get('a_total_diagnostics')} → {z.get('b_total_diagnostics')} |")
    lines.append("")
    lines.append("Only packages where zuban's file count or status changed are listed.")
    lines.append("")

    lines.append("<details><summary>Per-package detail</summary>")
    lines.append("")
    lines.append(f"| Package | Checker | Time {A} | Time {B} | Δ | Mem {A} | Mem {B} | Δ |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        if "error" in r:
            lines.append(f"| {r['package']} | | {r['error']} | | | | | |")
            continue
        for c in checkers:
            m = r.get("metrics", {}).get(c)
            if not m:
                continue
            if m.get("ok"):
                lines.append(f"| {r['package']} | {c} | {m['a_mean']:.3f}s | {m['b_mean']:.3f}s | "
                             f"{_pct(m['a_mean'], m['b_mean'])} | {m['a_mem']:.0f} MB | {m['b_mem']:.0f} MB | "
                             f"{_pct(m['a_mem'], m['b_mem'])} |")
            else:
                lines.append(f"| {r['package']} | {c} | {_status(m, 'a')} | {_status(m, 'b')} | "
                             f"{m.get('error') or ''} | | | |")
    lines.append("")
    lines.append("</details>")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    paths = [Path(p) for p in (argv if argv is not None else sys.argv[1:])]
    print(summarize(load(paths)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
