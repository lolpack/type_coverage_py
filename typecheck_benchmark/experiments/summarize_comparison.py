"""Merge compare_methodology shard outputs into a markdown report.

Usage:
  python -m typecheck_benchmark.experiments.summarize_comparison results/*.json
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

LABELS: dict[str, tuple[str, str]] = {
    "timing": ("poll (main)", "exact"),
    "env": ("shared env (main)", "per-package venv"),
    "tests": ("tests checked (before)", "tests excluded"),
    "deps": ("install (before)", "best-effort install"),
    "combo": ("PR 1 + 2", "mypy tests + best-effort installs"),
}
# Experiments whose files carry shared_*/isolated_* diagnostic fields
DIAGNOSTIC_EXPERIMENTS = ("env", "tests", "deps", "combo")


def load(paths: list[Path]) -> dict[str, dict[str, Any]]:
    """Group shard files by experiment, merging results in package order."""
    merged: dict[str, dict[str, Any]] = {}
    for p in paths:
        data = json.loads(p.read_text())
        exp = merged.setdefault(data["experiment"], {
            "versions": data["versions"], "checkers": data["checkers"],
            "pairs": data["pairs"], "results": [],
        })
        exp["results"].extend(data["results"])
    for exp in merged.values():
        exp["results"].sort(key=lambda r: r["index"])
    return merged


def _paired(results: list[dict[str, Any]], checker: str) -> list[tuple[str, float, float]]:
    rows = []
    for r in results:
        m = r.get("metrics", {}).get(checker)
        if m and m.get("ok"):
            rows.append((r["package"], m["a_mean"], m["b_mean"]))
    return rows


def _pct(a: float, b: float) -> str:
    return f"{(b - a) / a * 100:+.1f}%" if a else "n/a"


def _fastest(results: list[dict[str, Any]], checkers: list[str], key: str) -> tuple[Counter[str], dict[str, str]]:
    """Count which checker is fastest per package (only packages where all succeeded)."""
    wins: Counter[str] = Counter()
    per_pkg: dict[str, str] = {}
    for r in results:
        ms = r.get("metrics", {})
        if not all(ms.get(c, {}).get("ok") for c in checkers):
            continue
        ranked = sorted(checkers, key=lambda c: ms[c][key])
        # Count exact ties as ties rather than crediting list order
        best = "tie" if ms[ranked[0]][key] == ms[ranked[1]][key] else ranked[0]
        wins[best] += 1
        per_pkg[r["package"]] = best
    return wins, per_pkg


def summarize(name: str, exp: dict[str, Any]) -> str:
    a_label, b_label = LABELS[name]
    checkers: list[str] = exp["checkers"]
    results: list[dict[str, Any]] = exp["results"]
    lines = [f"## Experiment: {name}: {a_label} vs {b_label}", ""]
    lines.append(f"Versions: {', '.join(f'{k} {v}' for k, v in exp['versions'].items())}. "
                 f"{exp['pairs']} paired run(s) per checker per package, alternating order.")
    lines.append("")
    lines.append(f"| Checker | Pkgs | Mean {a_label} | Mean {b_label} | Δ mean | Median Δ per pkg | "
                 f"Total {a_label} | Total {b_label} |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for c in checkers:
        rows = _paired(results, c)
        if not rows:
            lines.append(f"| {c} | 0 | | | | | | |")
            continue
        a = [r[1] for r in rows]
        b = [r[2] for r in rows]
        deltas = [y - x for _, x, y in rows]
        lines.append(
            f"| {c} | {len(rows)} | {statistics.mean(a):.3f}s | {statistics.mean(b):.3f}s | "
            f"{_pct(statistics.mean(a), statistics.mean(b))} | {statistics.median(deltas) * 1000:+.0f} ms | "
            f"{sum(a):.1f}s | {sum(b):.1f}s |"
        )
    lines.append("")

    # Who is fastest per package, under each methodology
    wins_a, per_a = _fastest(results, checkers, "a_mean")
    wins_b, per_b = _fastest(results, checkers, "b_mean")
    flips = [(p, per_a[p], per_b[p]) for p in per_a if p in per_b and per_a[p] != per_b[p]]
    lines.append(f"**Fastest checker per package** (packages where every checker succeeded):")
    lines.append("")
    lines.append(f"| Checker | Wins under {a_label} | Wins under {b_label} |")
    lines.append("|---|---|---|")
    for c in [*checkers, "tie"]:
        lines.append(f"| {c} | {wins_a.get(c, 0)} | {wins_b.get(c, 0)} |")
    lines.append("")
    if flips:
        lines.append(f"Packages whose fastest checker changes ({len(flips)}): " +
                     ", ".join(f"{p} ({x}→{y})" for p, x, y in flips))
        lines.append("")

    if name in DIAGNOSTIC_EXPERIMENTS:
        lines.append("**Unresolved-import diagnostics** (warmup run, summed over packages where both arms ran):")
        lines.append("")
        lines.append(f"| Checker | {a_label} | {b_label} | Packages that differ |")
        lines.append("|---|---|---|---|")
        for c in checkers:
            s = i = 0
            differ: list[str] = []
            for r in results:
                m = r.get("metrics", {}).get(c)
                if not m or not (m.get("shared_warm_ok") and m.get("isolated_warm_ok")):
                    continue
                s += m["shared_unresolved_imports"]
                i += m["isolated_unresolved_imports"]
                if m["shared_unresolved_imports"] != m["isolated_unresolved_imports"]:
                    differ.append(f"{r['package']} ({m['shared_unresolved_imports']}→{m['isolated_unresolved_imports']})")
            lines.append(f"| {c} | {s} | {i} | {len(differ)} |")
        lines.append("")
        status_changes = []
        for r in results:
            for c in checkers:
                m = r.get("metrics", {}).get(c)
                if m and m.get("shared_warm_ok") != m.get("isolated_warm_ok"):
                    status_changes.append(
                        f"{r['package']}/{c}: shared {'ok' if m['shared_warm_ok'] else m.get('shared_error')}, "
                        f"venv {'ok' if m['isolated_warm_ok'] else m.get('isolated_error')}"
                    )
        if status_changes:
            lines.append("Success/failure changes: " + "; ".join(status_changes))
            lines.append("")

    # Per-package detail, largest relative changes first
    lines.append("<details><summary>Per-package detail</summary>")
    lines.append("")
    header = "| Package | Checker | " + a_label + " | " + b_label + " | Δ |"
    if name in DIAGNOSTIC_EXPERIMENTS:
        header += " Unresolved (shared→venv) | Diagnostics (shared→venv) |"
    lines.append(header)
    lines.append("|---|---|---|---|---|" + ("---|---|" if name in DIAGNOSTIC_EXPERIMENTS else ""))
    detail = []
    for r in results:
        for c in checkers:
            m = r.get("metrics", {}).get(c)
            if not m:
                continue
            if m.get("ok"):
                rel = abs(m["b_mean"] - m["a_mean"]) / m["a_mean"] if m["a_mean"] else 0
                row = f"| {r['package']} | {c} | {m['a_mean']:.3f}s | {m['b_mean']:.3f}s | {_pct(m['a_mean'], m['b_mean'])} |"
            else:
                rel = -1
                row = f"| {r['package']} | {c} | failed | failed | {m.get('error') or m.get('shared_error') or m.get('isolated_error') or ''} |"
            if name in DIAGNOSTIC_EXPERIMENTS:
                row += (f" {m.get('shared_unresolved_imports')}→{m.get('isolated_unresolved_imports')} |"
                        f" {m.get('shared_total_diagnostics')}→{m.get('isolated_total_diagnostics')} |")
            detail.append((rel, row))
    lines.extend(row for _, row in sorted(detail, key=lambda t: -t[0]))
    lines.append("")
    lines.append("</details>")
    lines.append("")
    return "\n".join(lines)


def _q(values: list[float], q: float) -> float:
    v = sorted(values)
    return v[min(len(v) - 1, int(q * len(v)))]


def summarize_runs(exp: dict[str, Any]) -> str:
    """1 measured run (what --runs 1 publishes) vs the median/mean of N."""
    checkers: list[str] = exp["checkers"]
    results: list[dict[str, Any]] = exp["results"]
    n = max((len(m["times"]) for r in results for c, m in r.get("metrics", {}).items()
             if not c.startswith("_") and m.get("ok")), default=0)
    lines = [f"## Experiment: runs: 1 measured run vs median of {n}", ""]
    lines.append(f"Versions: {', '.join(f'{k} {v}' for k, v in exp['versions'].items())}. "
                 f"Production config (per-package venv, exact timing), 1 warmup + {n} measured runs. "
                 f"\"1 run\" is the first measured run, i.e. what `--runs 1` publishes.")
    lines.append("")
    lines.append("**How far a single run is from the median of all runs** (per package):")
    lines.append("")
    lines.append("| Checker | Pkgs | Median error | Median abs error | p90 error | Max error | "
                 "Pkgs off >5% and >10ms | Pkgs off >10% and >10ms | "
                 f"Mean vs median of {n} differ >5% | Avg time, 1 run | Avg time, median of {n} |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    worst: list[tuple[float, str]] = []
    for c in checkers:
        errs: list[float] = []
        abs_errs: list[float] = []
        mean_vs_median = 0
        one: list[float] = []
        med: list[float] = []
        for r in results:
            m = r.get("metrics", {}).get(c)
            if not m or not m.get("ok") or len(m["times"]) < 2:
                continue
            t = m["times"]
            md = statistics.median(t)
            if md <= 0:
                continue
            e = abs(t[0] - md) / md
            errs.append(e)
            abs_errs.append(abs(t[0] - md))
            worst.append((e, f"{r['package']}/{c}: 1 run {t[0]:.3f}s vs median {md:.3f}s ({[round(x, 3) for x in t]})"))
            if abs(statistics.mean(t) - md) / md > 0.05:
                mean_vs_median += 1
            one.append(t[0])
            med.append(md)
        if not errs:
            lines.append(f"| {c} | 0 | | | | | | | | | |")
            continue
        lines.append(
            f"| {c} | {len(errs)} | {statistics.median(errs):.1%} | {statistics.median(abs_errs) * 1000:.0f} ms | "
            f"{_q(errs, 0.9):.1%} | {max(errs):.1%} | "
            f"{sum(e > 0.05 and a > 0.010 for e, a in zip(errs, abs_errs))} | "
            f"{sum(e > 0.10 and a > 0.010 for e, a in zip(errs, abs_errs))} | {mean_vs_median} | "
            f"{statistics.mean(one):.3f}s | {statistics.mean(med):.3f}s |"
        )
    lines.append("")

    # Does the fastest checker per package change between 1 run and median of N?
    def fastest(key: str) -> dict[str, str]:
        per: dict[str, str] = {}
        for r in results:
            ms = r.get("metrics", {})
            if not all(ms.get(c, {}).get("ok") for c in checkers):
                continue
            val = {c: (ms[c]["times"][0] if key == "one" else statistics.median(ms[c]["times"])) for c in checkers}
            ranked = sorted(checkers, key=lambda c: val[c])
            per[r["package"]] = "tie" if val[ranked[0]] == val[ranked[1]] else ranked[0]
        return per

    f1, fn = fastest("one"), fastest("median")
    flips = [(p, f1[p], fn[p]) for p in f1 if p in fn and f1[p] != fn[p]]
    lines.append(f"**Fastest checker per package:** differs between 1 run and median of {n} "
                 f"for {len(flips)} of {len(f1)} packages" + (": " + ", ".join(f"{p} ({a}→{b})" for p, a, b in flips) if flips else "."))
    lines.append("")
    lines.append("<details><summary>Largest single-run errors</summary>")
    lines.append("")
    for e, text in sorted(worst, reverse=True)[:25]:
        lines.append(f"- {e:.1%} {text}")
    lines.append("")
    lines.append("</details>")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    paths = [Path(p) for p in (argv if argv is not None else sys.argv[1:])]
    merged = load(paths)
    for name in ("timing", "env", "tests", "deps", "combo"):
        if name in merged:
            print(summarize(name, merged[name]))
    if "runs" in merged:
        print(summarize_runs(merged["runs"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
