#!/usr/bin/env python3
"""Backfill script to add ok_rate to existing benchmark JSON files.

This script:
1. Finds all benchmark JSON files in the results directory
2. Recalculates aggregate stats to include ok_rate
3. Updates the files in place
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def calculate_ok_rate_from_results(
    results: list[dict[str, Any]],
    type_checkers: list[str],
) -> dict[str, float]:
    """Calculate ok_rate for each type checker from results.

    Args:
        results: List of package benchmark results.
        type_checkers: List of type checker names.

    Returns:
        Dictionary mapping checker names to ok_rate percentages.
    """
    ok_rates: dict[str, float] = {}

    for checker in type_checkers:
        ok_counts: list[int] = []
        total_runs = 0

        for result in results:
            if result.get("error"):
                continue

            metrics = result.get("metrics", {}).get(checker, {})
            if not metrics.get("ok"):
                continue

            runs = metrics.get("runs", 0)
            total_runs += runs
            ok_counts.append(metrics.get("ok_count", 0))

        ok_rate = (sum(ok_counts) / total_runs * 100) if total_runs > 0 else 0.0
        ok_rates[checker] = ok_rate

    return ok_rates


def backfill_file(file_path: Path) -> bool:
    """Backfill ok_rate in a single benchmark JSON file.

    Args:
        file_path: Path to the JSON file to update.

    Returns:
        True if file was updated, False if it already has ok_rate or failed.
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)

        # Check if any aggregate stats already have ok_rate
        aggregate = data.get("aggregate", {})
        has_ok_rate = any("ok_rate" in stats for stats in aggregate.values())

        if has_ok_rate:
            print(f"  ✓ {file_path.name}: Already has ok_rate, skipping")
            return False

        # Calculate ok_rate for each type checker
        type_checkers = data.get("type_checkers", [])
        results = data.get("results", [])

        ok_rates = calculate_ok_rate_from_results(results, type_checkers)

        # Update aggregate stats with ok_rate
        for checker, ok_rate in ok_rates.items():
            if checker in aggregate:
                aggregate[checker]["ok_rate"] = ok_rate

        # Save updated data
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(f"  ✓ {file_path.name}: Added ok_rate for {len(ok_rates)} checkers")
        return True

    except Exception as e:
        print(f"  ✗ {file_path.name}: Error - {e}")
        return False


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success).
    """
    # Find results directory
    script_dir = Path(__file__).parent
    results_dir = script_dir / "results"

    if not results_dir.exists():
        print(f"Error: Results directory not found at {results_dir}")
        return 1

    # Find all benchmark JSON files
    json_files = list(results_dir.glob("benchmark_*.json"))
    latest_file = results_dir / "latest.json"

    if latest_file.exists():
        json_files.append(latest_file)

    if not json_files:
        print(f"No benchmark JSON files found in {results_dir}")
        return 0

    print(f"Found {len(json_files)} JSON file(s) to process\n")

    # Process each file
    updated_count = 0
    for json_file in sorted(json_files):
        if backfill_file(json_file):
            updated_count += 1

    print(f"\n✓ Complete! Updated {updated_count} file(s)")
    return 0


if __name__ == "__main__":
    exit(main())
