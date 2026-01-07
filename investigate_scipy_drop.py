#!/usr/bin/env python3
"""
Investigate what changed with scipy between 2025-12-29 and 2025-12-31.
"""

import json


def compare_scipy_configs() -> None:
    """
    Compare scipy benchmark configuration between day 6 and day 7.
    """
    day6_file = "lsp/benchmark/results/benchmark_2025-12-29.json"
    day7_file = "lsp/benchmark/results/benchmark_2025-12-31.json"

    print("="*100)
    print("COMPARING SCIPY CONFIGURATION BETWEEN 2025-12-29 (Day 6) and 2025-12-31 (Day 7)")
    print("="*100)

    for label, filepath in [("Day 6 (2025-12-29)", day6_file), ("Day 7 (2025-12-31)", day7_file)]:
        print(f"\n{label}:")
        print("-"*100)

        with open(filepath, 'r') as f:
            data = json.load(f)

        # Print top-level metadata
        print(f"Timestamp: {data.get('timestamp')}")
        print(f"Type checkers: {data.get('type_checkers')}")
        print(f"Type checker versions: {data.get('type_checker_versions')}")
        print(f"Package count: {data.get('package_count')}")
        print(f"Runs per package: {data.get('runs_per_package')}")

        # Find scipy
        for package_result in data.get('results', []):
            if package_result['package_name'] == 'scipy':
                print(f"\nScipy details:")
                print(f"  Package name: {package_result.get('package_name')}")
                print(f"  GitHub URL: {package_result.get('github_url')}")
                print(f"  Ranking: {package_result.get('ranking')}")
                print(f"  Error: {package_result.get('error')}")

                # Show sample results from each LSP
                metrics = package_result.get('metrics', {})
                print(f"\n  Success rates:")
                for lsp_name in sorted(metrics.keys()):
                    lsp_data = metrics[lsp_name]
                    print(f"    {lsp_name}: {lsp_data.get('valid_pct')}% "
                          f"({lsp_data.get('valid_count')}/{lsp_data.get('runs')} valid)")

                break

    print("\n" + "="*100)
    print("HYPOTHESIS: Check if scipy package was updated or test methodology changed")
    print("="*100)
    print("\nPossible causes:")
    print("1. scipy package version changed (e.g., new release with different structure)")
    print("2. Test file selection changed (different files being randomly sampled)")
    print("3. Symbol selection methodology changed")
    print("4. LSP server versions updated")
    print("5. Something in scipy's codebase structure changed that affects go-to-definition")
    print("\nRecommendation: Check git history and scipy package version between these dates.")


def main() -> None:
    compare_scipy_configs()


if __name__ == "__main__":
    main()
