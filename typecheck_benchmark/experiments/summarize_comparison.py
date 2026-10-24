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
}


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

    if name == "env":
        lines.append("**Unresolved-import diagnostics** (warmup run, summed over packages where both arms ran):")
        lines.append("")
        lines.append("| Checker | Shared env | Per-package venv | Packages that differ |")
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
    if name == "env":
        header += " Unresolved (shared→venv) | Diagnostics (shared→venv) |"
    lines.append(header)
    lines.append("|---|---|---|---|---|" + ("---|---|" if name == "env" else ""))
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
            if name == "env":
                row += (f" {m.get('shared_unresolved_imports')}→{m.get('isolated_unresolved_imports')} |"
                        f" {m.get('shared_total_diagnostics')}→{m.get('isolated_total_diagnostics')} |")
            detail.append((rel, row))
    lines.extend(row for _, row in sorted(detail, key=lambda t: -t[0]))
    lines.append("")
    lines.append("</details>")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    paths = [Path(p) for p in (argv if argv is not None else sys.argv[1:])]
    merged = load(paths)
    for name in ("timing", "env"):
        if name in merged:
            print(summarize(name, merged[name]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
