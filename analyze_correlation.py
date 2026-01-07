#!/usr/bin/env python3
"""
Analyze correlation between type coverage and LSP go-to-definition success rates.
"""

import json
import glob
from pathlib import Path
from typing import Dict, List, Tuple
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats


def load_lsp_benchmarks(benchmark_dir: str) -> Dict[str, float]:
    """
    Load all LSP benchmark files and compute average success rate across all LSPs per package.

    Returns:
        Dict mapping package_name -> average_success_rate_across_lsps
    """
    benchmark_files = glob.glob(f"{benchmark_dir}/*.json")

    # Aggregate all runs for each package across all files
    package_lsp_scores: Dict[str, List[float]] = {}

    for filepath in benchmark_files:
        with open(filepath, 'r') as f:
            data = json.load(f)

        for package_result in data.get('results', []):
            package_name = package_result['package_name']

            if package_name not in package_lsp_scores:
                package_lsp_scores[package_name] = []

            # Get success rates from all LSPs for this package
            metrics = package_result.get('metrics', {})
            for lsp_name, lsp_data in metrics.items():
                if lsp_data.get('ok'):
                    # valid_pct is the success rate for go-to-definition
                    valid_pct = lsp_data.get('valid_pct', 0)
                    package_lsp_scores[package_name].append(valid_pct)

    # Compute average success rate across all LSPs and all runs
    package_avg_success: Dict[str, float] = {}
    for package_name, scores in package_lsp_scores.items():
        if scores:
            package_avg_success[package_name] = np.mean(scores)

    return package_avg_success


def load_type_coverage(coverage_file: str) -> Dict[str, Dict[str, float]]:
    """
    Load type coverage data from package report.

    Returns:
        Dict mapping package_name -> {
            'pyright_coverage': float,
            'param_coverage_with_stubs': float,
            'return_coverage_with_stubs': float
        }
    """
    with open(coverage_file, 'r') as f:
        data = json.load(f)

    coverage_data = {}
    for package_name, package_info in data.items():
        pyright_coverage = package_info.get('pyright_stats', {}).get('coverage', None)
        param_coverage = package_info.get('CoverageData', {}).get('parameter_coverage_with_stubs', None)
        return_coverage = package_info.get('CoverageData', {}).get('return_type_coverage_with_stubs', None)

        if pyright_coverage is not None and param_coverage is not None and return_coverage is not None:
            coverage_data[package_name] = {
                'pyright_coverage': pyright_coverage,
                'param_coverage_with_stubs': param_coverage,
                'return_coverage_with_stubs': return_coverage
            }

    return coverage_data


def merge_data(lsp_data: Dict[str, float], coverage_data: Dict[str, Dict[str, float]]) -> Tuple[List[str], Dict[str, List[float]]]:
    """
    Merge LSP and coverage data for packages that exist in both datasets.

    Returns:
        (package_names, {metric_name: values})
    """
    common_packages = set(lsp_data.keys()) & set(coverage_data.keys())

    package_names = sorted(list(common_packages))

    merged = {
        'lsp_success': [],
        'pyright_coverage': [],
        'param_coverage': [],
        'return_coverage': []
    }

    for package in package_names:
        merged['lsp_success'].append(lsp_data[package])
        merged['pyright_coverage'].append(coverage_data[package]['pyright_coverage'])
        merged['param_coverage'].append(coverage_data[package]['param_coverage_with_stubs'])
        merged['return_coverage'].append(coverage_data[package]['return_coverage_with_stubs'])

    return package_names, merged


def plot_correlations(package_names: List[str], data: Dict[str, List[float]]) -> None:
    """
    Create scatter plots showing correlations between type coverage metrics and LSP success.
    """
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle('Correlation between Type Coverage and Go-to-Definition Success Rate',
                 fontsize=14, fontweight='bold')

    lsp_success = data['lsp_success']

    # Plot 1: Pyright Coverage vs LSP Success
    ax1 = axes[0]
    ax1.scatter(data['pyright_coverage'], lsp_success, alpha=0.6, s=100)

    # Add trend line
    z = np.polyfit(data['pyright_coverage'], lsp_success, 1)
    p = np.poly1d(z)
    ax1.plot(data['pyright_coverage'], p(data['pyright_coverage']), "r--", alpha=0.8, linewidth=2)

    # Calculate correlation
    corr, p_value = stats.pearsonr(data['pyright_coverage'], lsp_success)
    ax1.set_xlabel('Pyright Type Coverage (%)', fontsize=11)
    ax1.set_ylabel('Avg LSP Go-to-Definition Success (%)', fontsize=11)
    ax1.set_title(f'Pyright Coverage\nr={corr:.3f}, p={p_value:.4f}', fontsize=12)
    ax1.grid(True, alpha=0.3)

    # Plot 2: Parameter Coverage vs LSP Success
    ax2 = axes[1]
    ax2.scatter(data['param_coverage'], lsp_success, alpha=0.6, s=100, color='green')

    z = np.polyfit(data['param_coverage'], lsp_success, 1)
    p = np.poly1d(z)
    ax2.plot(data['param_coverage'], p(data['param_coverage']), "r--", alpha=0.8, linewidth=2)

    corr, p_value = stats.pearsonr(data['param_coverage'], lsp_success)
    ax2.set_xlabel('Parameter Coverage w/ Typeshed (%)', fontsize=11)
    ax2.set_ylabel('Avg LSP Go-to-Definition Success (%)', fontsize=11)
    ax2.set_title(f'Parameter Coverage\nr={corr:.3f}, p={p_value:.4f}', fontsize=12)
    ax2.grid(True, alpha=0.3)

    # Plot 3: Return Type Coverage vs LSP Success
    ax3 = axes[2]
    ax3.scatter(data['return_coverage'], lsp_success, alpha=0.6, s=100, color='purple')

    z = np.polyfit(data['return_coverage'], lsp_success, 1)
    p = np.poly1d(z)
    ax3.plot(data['return_coverage'], p(data['return_coverage']), "r--", alpha=0.8, linewidth=2)

    corr, p_value = stats.pearsonr(data['return_coverage'], lsp_success)
    ax3.set_xlabel('Return Type Coverage w/ Typeshed (%)', fontsize=11)
    ax3.set_ylabel('Avg LSP Go-to-Definition Success (%)', fontsize=11)
    ax3.set_title(f'Return Type Coverage\nr={corr:.3f}, p={p_value:.4f}', fontsize=12)
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()
    output_file = 'correlation_analysis.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"\nPlot saved to: {output_file}")
    plt.show()


def print_statistics(package_names: List[str], data: Dict[str, List[float]]) -> None:
    """
    Print correlation statistics.
    """
    print("\n" + "="*70)
    print("CORRELATION ANALYSIS RESULTS")
    print("="*70)
    print(f"\nNumber of packages analyzed: {len(package_names)}")
    print(f"Packages: {', '.join(package_names)}")

    print("\n" + "-"*70)
    print("CORRELATION COEFFICIENTS (Pearson's r)")
    print("-"*70)

    lsp_success = data['lsp_success']

    metrics = [
        ('Pyright Coverage', data['pyright_coverage']),
        ('Parameter Coverage (w/ Typeshed)', data['param_coverage']),
        ('Return Type Coverage (w/ Typeshed)', data['return_coverage'])
    ]

    for metric_name, metric_values in metrics:
        corr, p_value = stats.pearsonr(metric_values, lsp_success)
        print(f"\n{metric_name}:")
        print(f"  Correlation coefficient (r): {corr:6.3f}")
        print(f"  P-value:                      {p_value:.4f}")
        print(f"  Interpretation: ", end="")

        if p_value < 0.001:
            sig = "***"
        elif p_value < 0.01:
            sig = "**"
        elif p_value < 0.05:
            sig = "*"
        else:
            sig = "not significant"

        if abs(corr) > 0.7:
            strength = "Strong"
        elif abs(corr) > 0.4:
            strength = "Moderate"
        elif abs(corr) > 0.2:
            strength = "Weak"
        else:
            strength = "Very weak"

        direction = "positive" if corr > 0 else "negative"
        print(f"{strength} {direction} correlation {sig}")

    print("\n" + "-"*70)
    print("SUMMARY STATISTICS")
    print("-"*70)

    all_metrics = {
        'LSP Go-to-Def Success': lsp_success,
        'Pyright Coverage': data['pyright_coverage'],
        'Param Coverage': data['param_coverage'],
        'Return Coverage': data['return_coverage']
    }

    for name, values in all_metrics.items():
        print(f"\n{name}:")
        print(f"  Mean:   {np.mean(values):6.2f}%")
        print(f"  Median: {np.median(values):6.2f}%")
        print(f"  Std:    {np.std(values):6.2f}%")
        print(f"  Range:  [{np.min(values):6.2f}%, {np.max(values):6.2f}%]")

    print("\n" + "="*70)


def main() -> None:
    """
    Main analysis function.
    """
    # Configuration
    BENCHMARK_DIR = "lsp/benchmark/results"
    COVERAGE_FILE = "prioritized/historical_data/json/package_report-2026-01-05.json"

    print("Loading LSP benchmark data...")
    lsp_data = load_lsp_benchmarks(BENCHMARK_DIR)
    print(f"  Loaded data for {len(lsp_data)} packages")

    print("\nLoading type coverage data...")
    coverage_data = load_type_coverage(COVERAGE_FILE)
    print(f"  Loaded data for {len(coverage_data)} packages")

    print("\nMerging datasets...")
    package_names, merged_data = merge_data(lsp_data, coverage_data)
    print(f"  Found {len(package_names)} packages in common")

    if len(package_names) < 3:
        print("\nError: Need at least 3 common packages for correlation analysis")
        return

    print("\nCalculating correlations and generating plots...")
    print_statistics(package_names, merged_data)
    plot_correlations(package_names, merged_data)


if __name__ == "__main__":
    main()
