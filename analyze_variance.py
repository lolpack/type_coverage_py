#!/usr/bin/env python3
"""
Analyze day-to-day variance in go-to-definition success rates.
Since symbols/files are randomly selected each day, this shows measurement stability.
"""

import json
import glob
from collections import defaultdict
from typing import Dict, List, Tuple
import statistics
import matplotlib.pyplot as plt
import numpy as np


def load_benchmarks_with_dates(benchmark_dir: str) -> Tuple[Dict[str, Dict[str, Dict[str, float]]], List[str]]:
    """
    Load all LSP benchmark files preserving date information.

    Returns:
        (data dict, sorted list of dates)
        data: date -> package_name -> lsp_name -> success_rate
    """
    benchmark_files = sorted(glob.glob(f"{benchmark_dir}/*.json"))

    data_by_date = {}
    dates = []

    for filepath in benchmark_files:
        # Extract date from filename
        filename = filepath.split('/')[-1]
        if filename == 'latest.json':
            continue

        date = filename.replace('benchmark_', '').replace('.json', '')
        dates.append(date)

        with open(filepath, 'r') as f:
            file_data = json.load(f)

        data_by_date[date] = {}

        for package_result in file_data.get('results', []):
            package_name = package_result['package_name']
            data_by_date[date][package_name] = {}

            metrics = package_result.get('metrics', {})
            for lsp_name, lsp_data in metrics.items():
                if lsp_data.get('ok'):
                    valid_pct = lsp_data.get('valid_pct', 0)
                    data_by_date[date][package_name][lsp_name] = valid_pct

    return data_by_date, sorted(dates)


def analyze_variance(data_by_date: Dict[str, Dict[str, Dict[str, float]]]) -> Dict[str, Dict[str, Dict[str, float]]]:
    """
    Calculate variance statistics for each package-LSP combination.

    Returns:
        package -> lsp -> {mean, std, cv, min, max, range}
    """
    # Reorganize data: package -> lsp -> [values_over_time]
    package_lsp_values = defaultdict(lambda: defaultdict(list))

    for date, packages in data_by_date.items():
        for package_name, lsps in packages.items():
            for lsp_name, value in lsps.items():
                package_lsp_values[package_name][lsp_name].append(value)

    # Calculate statistics
    variance_stats = {}
    for package_name, lsps in package_lsp_values.items():
        variance_stats[package_name] = {}
        for lsp_name, values in lsps.items():
            if len(values) > 1:
                mean = statistics.mean(values)
                std = statistics.stdev(values)
                cv = (std / mean * 100) if mean > 0 else 0  # Coefficient of variation
                variance_stats[package_name][lsp_name] = {
                    'mean': mean,
                    'std': std,
                    'cv': cv,
                    'min': min(values),
                    'max': max(values),
                    'range': max(values) - min(values),
                    'n': len(values)
                }

    return variance_stats


def print_variance_report(variance_stats: Dict[str, Dict[str, Dict[str, float]]]) -> None:
    """
    Print a detailed variance report.
    """
    print("\n" + "="*120)
    print("DAY-TO-DAY VARIANCE ANALYSIS")
    print("="*120)
    print("\nMetrics:")
    print("  - Std Dev: Standard deviation of success rates across days")
    print("  - CV: Coefficient of Variation (std/mean * 100) - normalized variance measure")
    print("  - Range: Difference between max and min observed success rates")
    print("\n")

    # Get all LSPs
    all_lsps = set()
    for lsps in variance_stats.values():
        all_lsps.update(lsps.keys())
    lsp_names = sorted(all_lsps)

    # Print header
    print(f"{'Package':<25} {'LSP':<10} {'Mean%':>8} {'Std':>8} {'CV%':>8} {'Range%':>8} {'Min%':>8} {'Max%':>8} {'Days':>6}")
    print("-" * 120)

    # Sort packages by average variance (across all LSPs)
    def avg_cv(pkg):
        cvs = [stats['cv'] for stats in variance_stats[pkg].values()]
        return statistics.mean(cvs) if cvs else 0

    for package_name in sorted(variance_stats.keys(), key=avg_cv, reverse=True):
        lsp_stats = variance_stats[package_name]
        for lsp_name in sorted(lsp_stats.keys()):
            stats = lsp_stats[lsp_name]
            print(f"{package_name:<25} {lsp_name:<10} {stats['mean']:>7.2f}% {stats['std']:>7.2f}% "
                  f"{stats['cv']:>7.2f}% {stats['range']:>7.2f}% {stats['min']:>7.2f}% "
                  f"{stats['max']:>7.2f}% {stats['n']:>6}")
        print()

    print("="*120)


def print_lsp_variance_summary(variance_stats: Dict[str, Dict[str, Dict[str, float]]]) -> None:
    """
    Print summary statistics by LSP showing which LSPs have more stable measurements.
    """
    print("\n" + "="*100)
    print("LSP VARIANCE SUMMARY (Measurement Stability)")
    print("="*100)
    print("\nLower CV% = More stable/consistent measurements across days\n")

    # Collect all CVs and stds per LSP
    lsp_cvs = defaultdict(list)
    lsp_stds = defaultdict(list)
    lsp_ranges = defaultdict(list)

    for package_stats in variance_stats.values():
        for lsp_name, stats in package_stats.items():
            lsp_cvs[lsp_name].append(stats['cv'])
            lsp_stds[lsp_name].append(stats['std'])
            lsp_ranges[lsp_name].append(stats['range'])

    # Print summary
    print(f"{'LSP':<12} {'Avg CV%':>10} {'Avg Std':>10} {'Avg Range':>12} {'Packages':>10}")
    print("-" * 100)

    for lsp in sorted(lsp_cvs.keys(), key=lambda x: statistics.mean(lsp_cvs[x])):
        avg_cv = statistics.mean(lsp_cvs[lsp])
        avg_std = statistics.mean(lsp_stds[lsp])
        avg_range = statistics.mean(lsp_ranges[lsp])
        n_packages = len(lsp_cvs[lsp])

        print(f"{lsp:<12} {avg_cv:>9.2f}% {avg_std:>9.2f}% {avg_range:>11.2f}% {n_packages:>10}")

    print("\nInterpretation:")
    print("  - LSPs with lower CV% have more consistent/stable measurements")
    print("  - This indicates either more deterministic behavior or less sensitivity to random file/symbol selection")
    print("="*100)


def identify_high_variance_cases(variance_stats: Dict[str, Dict[str, Dict[str, float]]],
                                  threshold_cv: float = 10.0) -> None:
    """
    Identify package-LSP combinations with high variance.
    """
    print("\n" + "="*100)
    print(f"HIGH VARIANCE CASES (CV > {threshold_cv}%)")
    print("="*100)
    print("\nThese combinations show significant day-to-day variation in success rates,")
    print("suggesting sensitivity to random file/symbol selection.\n")

    high_variance = []
    for package_name, lsp_stats in variance_stats.items():
        for lsp_name, stats in lsp_stats.items():
            if stats['cv'] > threshold_cv:
                high_variance.append((package_name, lsp_name, stats))

    if not high_variance:
        print(f"No cases found with CV > {threshold_cv}%")
    else:
        print(f"{'Package':<25} {'LSP':<10} {'Mean%':>8} {'CV%':>8} {'Std%':>8} {'Range%':>8}")
        print("-" * 100)

        # Sort by CV descending
        for package_name, lsp_name, stats in sorted(high_variance, key=lambda x: x[2]['cv'], reverse=True):
            print(f"{package_name:<25} {lsp_name:<10} {stats['mean']:>7.2f}% {stats['cv']:>7.2f}% "
                  f"{stats['std']:>7.2f}% {stats['range']:>7.2f}%")

    print("="*100)


def plot_variance_over_time(data_by_date: Dict[str, Dict[str, Dict[str, float]]],
                             dates: List[str],
                             output_file: str) -> None:
    """
    Create time series plots showing variance over time for selected packages.
    """
    # Select interesting packages to visualize (high and low variance)
    selected_packages = ['click', 'wagtail', 'scipy', 'ixnetwork-restpy', 'requests', 'transformers']

    # Get LSP names
    first_date = dates[0]
    first_package = list(data_by_date[first_date].keys())[0]
    lsp_names = sorted(data_by_date[first_date][first_package].keys())

    fig, axes = plt.subplots(2, 3, figsize=(20, 12))
    fig.suptitle('Go-to-Definition Success Rate Over Time by Package and LSP',
                 fontsize=16, fontweight='bold')

    lsp_colors = {
        'pyright': '#4285F4',
        'pyrefly': '#34A853',
        'ty': '#FBBC05',
        'zuban': '#EA4335'
    }

    for idx, package_name in enumerate(selected_packages):
        if idx >= 6:
            break

        ax = axes[idx // 3, idx % 3]

        for lsp_name in lsp_names:
            values = []
            plot_dates = []
            for date in dates:
                if package_name in data_by_date[date]:
                    if lsp_name in data_by_date[date][package_name]:
                        values.append(data_by_date[date][package_name][lsp_name])
                        plot_dates.append(date)

            if values:
                color = lsp_colors.get(lsp_name, '#666666')
                ax.plot(range(len(values)), values, marker='o', label=lsp_name,
                       color=color, alpha=0.7, linewidth=2)

        ax.set_title(package_name, fontsize=12, fontweight='bold')
        ax.set_xlabel('Day Index', fontsize=10)
        ax.set_ylabel('Success Rate (%)', fontsize=10)
        ax.set_ylim(0, 105)
        ax.grid(True, alpha=0.3)
        ax.legend(loc='best', fontsize=9)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"\nTime series plot saved to: {output_file}")
    plt.close(fig)


def plot_variance_distribution(variance_stats: Dict[str, Dict[str, Dict[str, float]]],
                               output_file: str) -> None:
    """
    Create box plots showing distribution of variance by LSP.
    """
    # Collect CVs per LSP
    lsp_cvs = defaultdict(list)
    lsp_stds = defaultdict(list)

    for package_stats in variance_stats.values():
        for lsp_name, stats in package_stats.items():
            lsp_cvs[lsp_name].append(stats['cv'])
            lsp_stds[lsp_name].append(stats['std'])

    lsp_names = sorted(lsp_cvs.keys())

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle('Distribution of Variance Across Packages by LSP', fontsize=14, fontweight='bold')

    # Plot 1: Coefficient of Variation
    cv_data = [lsp_cvs[lsp] for lsp in lsp_names]
    bp1 = ax1.boxplot(cv_data, labels=lsp_names, patch_artist=True)

    colors = ['#4285F4', '#34A853', '#FBBC05', '#EA4335']
    for patch, color in zip(bp1['boxes'], colors[:len(lsp_names)]):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)

    ax1.set_ylabel('Coefficient of Variation (%)', fontsize=11)
    ax1.set_xlabel('LSP', fontsize=11)
    ax1.set_title('Measurement Stability (Lower = More Stable)', fontsize=12)
    ax1.grid(True, alpha=0.3, axis='y')

    # Plot 2: Standard Deviation
    std_data = [lsp_stds[lsp] for lsp in lsp_names]
    bp2 = ax2.boxplot(std_data, labels=lsp_names, patch_artist=True)

    for patch, color in zip(bp2['boxes'], colors[:len(lsp_names)]):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)

    ax2.set_ylabel('Standard Deviation (%)', fontsize=11)
    ax2.set_xlabel('LSP', fontsize=11)
    ax2.set_title('Absolute Variance', fontsize=12)
    ax2.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Variance distribution plot saved to: {output_file}")
    plt.close(fig)


def main() -> None:
    """
    Main function.
    """
    BENCHMARK_DIR = "lsp/benchmark/results"

    print("Loading benchmark data with date information...")
    data_by_date, dates = load_benchmarks_with_dates(BENCHMARK_DIR)
    print(f"  Loaded {len(dates)} dates: {dates[0]} to {dates[-1]}")

    print("\nCalculating variance statistics...")
    variance_stats = analyze_variance(data_by_date)

    # Print detailed variance report
    print_variance_report(variance_stats)

    # Print LSP variance summary
    print_lsp_variance_summary(variance_stats)

    # Identify high variance cases
    identify_high_variance_cases(variance_stats, threshold_cv=10.0)

    # Create visualizations
    print("\nGenerating variance visualizations...")
    plot_variance_over_time(data_by_date, dates, 'variance_over_time.png')
    plot_variance_distribution(variance_stats, 'variance_distribution_by_lsp.png')

    print("\n" + "="*100)
    print("Variance analysis complete!")
    print("="*100)


if __name__ == "__main__":
    main()
