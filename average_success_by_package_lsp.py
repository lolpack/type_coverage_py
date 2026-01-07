#!/usr/bin/env python3
"""
Calculate average go-to-definition success rate over all dates by package and LSP.
"""

import json
import glob
from collections import defaultdict
from typing import Dict, List
import statistics


def load_all_benchmarks(benchmark_dir: str) -> Dict[str, Dict[str, List[float]]]:
    """
    Load all LSP benchmark files and collect success rates by package and LSP.

    Returns:
        Dict mapping package_name -> lsp_name -> [success_rates]
    """
    benchmark_files = sorted(glob.glob(f"{benchmark_dir}/*.json"))

    print(f"Found {len(benchmark_files)} benchmark files")
    if benchmark_files:
        print(f"Date range: {benchmark_files[0].split('/')[-1]} to {benchmark_files[-1].split('/')[-1]}")

    # Structure: package_name -> lsp_name -> list of success rates
    package_lsp_scores: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

    for filepath in benchmark_files:
        with open(filepath, 'r') as f:
            data = json.load(f)

        for package_result in data.get('results', []):
            package_name = package_result['package_name']

            # Get success rates from each LSP for this package
            metrics = package_result.get('metrics', {})
            for lsp_name, lsp_data in metrics.items():
                if lsp_data.get('ok'):
                    # valid_pct is the success rate for go-to-definition
                    valid_pct = lsp_data.get('valid_pct', 0)
                    package_lsp_scores[package_name][lsp_name].append(valid_pct)

    return package_lsp_scores


def print_detailed_table(package_lsp_scores: Dict[str, Dict[str, List[float]]]) -> None:
    """
    Print a detailed table showing average success rates and number of measurements.
    """
    # Get all unique LSPs
    all_lsps = set()
    for lsp_dict in package_lsp_scores.values():
        all_lsps.update(lsp_dict.keys())
    lsp_names = sorted(all_lsps)

    print("\n" + "="*120)
    print("AVERAGE GO-TO-DEFINITION SUCCESS RATE BY PACKAGE AND LSP")
    print("="*120)
    print("\nFormat: avg% (n measurements)\n")

    # Create header
    header = f"{'Package':<25}"
    for lsp in lsp_names:
        header += f"{lsp:>20}"
    print(header)
    print("-" * 120)

    # Collect data for overall averages
    lsp_all_scores = {lsp: [] for lsp in lsp_names}

    # Print each row
    for package_name in sorted(package_lsp_scores.keys()):
        line = f"{package_name:<25}"
        for lsp in lsp_names:
            if lsp in package_lsp_scores[package_name]:
                scores = package_lsp_scores[package_name][lsp]
                avg = statistics.mean(scores) if scores else 0
                n = len(scores)
                lsp_all_scores[lsp].append(avg)
                line += f"{avg:>7.2f}% ({n:>4}){' ':>5}"
            else:
                line += f"{'N/A':>20}"
        print(line)

    # Print summary statistics
    print("-" * 120)
    print(f"{'OVERALL AVERAGE':<25}", end="")
    for lsp in lsp_names:
        if lsp_all_scores[lsp]:
            overall_avg = statistics.mean(lsp_all_scores[lsp])
            total_n = sum(len(package_lsp_scores[pkg][lsp])
                         for pkg in package_lsp_scores if lsp in package_lsp_scores[pkg])
            print(f"{overall_avg:>7.2f}% ({total_n:>4}){' ':>5}", end="")
        else:
            print(f"{'N/A':>20}", end="")
    print()

    print("="*120)


def create_csv(package_lsp_scores: Dict[str, Dict[str, List[float]]], output_file: str) -> None:
    """
    Create a CSV file with the results.
    """
    # Get all unique LSPs
    all_lsps = set()
    for lsp_dict in package_lsp_scores.values():
        all_lsps.update(lsp_dict.keys())
    lsp_names = sorted(all_lsps)

    with open(output_file, 'w') as f:
        # Write header
        f.write('package,' + ','.join(lsp_names) + '\n')

        # Write data rows
        for package_name in sorted(package_lsp_scores.keys()):
            row = [package_name]
            for lsp in lsp_names:
                if lsp in package_lsp_scores[package_name]:
                    scores = package_lsp_scores[package_name][lsp]
                    avg = statistics.mean(scores) if scores else 0
                    row.append(f"{avg:.2f}")
                else:
                    row.append("N/A")
            f.write(','.join(row) + '\n')

    print(f"\nCSV output saved to: {output_file}")


def print_per_package_stats(package_lsp_scores: Dict[str, Dict[str, List[float]]]) -> None:
    """
    Print detailed statistics for each package showing variability across dates.
    """
    print("\n" + "="*100)
    print("PER-PACKAGE STATISTICS (showing variability across dates)")
    print("="*100)

    for package_name in sorted(package_lsp_scores.keys()):
        print(f"\n{package_name}:")
        print("-" * 80)

        for lsp_name in sorted(package_lsp_scores[package_name].keys()):
            scores = package_lsp_scores[package_name][lsp_name]
            if scores:
                avg = statistics.mean(scores)
                std = statistics.stdev(scores) if len(scores) > 1 else 0
                min_score = min(scores)
                max_score = max(scores)
                n = len(scores)

                print(f"  {lsp_name:>10}: avg={avg:6.2f}%, std={std:5.2f}%, "
                      f"range=[{min_score:6.2f}%, {max_score:6.2f}%], n={n}")


def print_lsp_comparison_summary(package_lsp_scores: Dict[str, Dict[str, List[float]]]) -> None:
    """
    Print a summary comparing LSP performance.
    """
    # Get all unique LSPs
    all_lsps = set()
    for lsp_dict in package_lsp_scores.values():
        all_lsps.update(lsp_dict.keys())
    lsp_names = sorted(all_lsps)

    print("\n" + "="*100)
    print("LSP COMPARISON SUMMARY")
    print("="*100)

    lsp_stats = {}
    for lsp in lsp_names:
        all_scores = []
        for package_scores in package_lsp_scores.values():
            if lsp in package_scores:
                all_scores.extend(package_scores[lsp])

        if all_scores:
            lsp_stats[lsp] = {
                'avg': statistics.mean(all_scores),
                'median': statistics.median(all_scores),
                'std': statistics.stdev(all_scores) if len(all_scores) > 1 else 0,
                'min': min(all_scores),
                'max': max(all_scores),
                'n_measurements': len(all_scores),
                'n_packages': len([pkg for pkg in package_lsp_scores if lsp in package_lsp_scores[pkg]])
            }

    # Print summary
    print(f"\n{'LSP':<12} {'Avg%':>8} {'Median%':>8} {'Std':>8} {'Min%':>8} {'Max%':>8} {'Packages':>10} {'Measurements':>14}")
    print("-" * 100)

    # Sort by average success rate (descending)
    for lsp in sorted(lsp_stats.keys(), key=lambda x: lsp_stats[x]['avg'], reverse=True):
        stats_data = lsp_stats[lsp]
        print(f"{lsp:<12} {stats_data['avg']:>7.2f}% {stats_data['median']:>7.2f}% "
              f"{stats_data['std']:>7.2f}% {stats_data['min']:>7.2f}% {stats_data['max']:>7.2f}% "
              f"{stats_data['n_packages']:>10} {stats_data['n_measurements']:>14}")

    print("="*100)


def main() -> None:
    """
    Main function.
    """
    BENCHMARK_DIR = "lsp/benchmark/results"
    OUTPUT_CSV = "average_success_by_package_lsp.csv"

    print("Loading all benchmark data...")
    package_lsp_scores = load_all_benchmarks(BENCHMARK_DIR)

    print(f"\nFound {len(package_lsp_scores)} unique packages")

    # Print the main table
    print_detailed_table(package_lsp_scores)

    # Print LSP comparison summary
    print_lsp_comparison_summary(package_lsp_scores)

    # Print per-package statistics
    print_per_package_stats(package_lsp_scores)

    # Save to CSV
    create_csv(package_lsp_scores, OUTPUT_CSV)

    print("\n" + "="*100)
    print("Analysis complete!")
    print("="*100)


if __name__ == "__main__":
    main()
