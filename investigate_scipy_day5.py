#!/usr/bin/env python3
"""
Investigate scipy anomaly on day 5.
"""

import json
import glob


def investigate_scipy_day5() -> None:
    """
    Look at what happened with scipy on day 5.
    """
    benchmark_files = sorted(glob.glob("lsp/benchmark/results/*.json"))

    # Filter out latest.json
    benchmark_files = [f for f in benchmark_files if 'latest.json' not in f]

    print("="*100)
    print("SCIPY GO-TO-DEFINITION SUCCESS RATES BY DATE")
    print("="*100)
    print(f"\n{'Day':<5} {'Date':<15} {'pyright':>10} {'pyrefly':>10} {'ty':>10} {'zuban':>10}")
    print("-"*100)

    for idx, filepath in enumerate(benchmark_files, 1):
        date = filepath.split('/')[-1].replace('benchmark_', '').replace('.json', '')

        with open(filepath, 'r') as f:
            data = json.load(f)

        # Find scipy in results
        scipy_data = None
        for package_result in data.get('results', []):
            if package_result['package_name'] == 'scipy':
                scipy_data = package_result
                break

        if scipy_data:
            metrics = scipy_data.get('metrics', {})
            pyright_val = metrics.get('pyright', {}).get('valid_pct', 'N/A')
            pyrefly_val = metrics.get('pyrefly', {}).get('valid_pct', 'N/A')
            ty_val = metrics.get('ty', {}).get('valid_pct', 'N/A')
            zuban_val = metrics.get('zuban', {}).get('valid_pct', 'N/A')

            # Highlight day 5
            marker = " <-- Day 5" if idx == 5 else ""

            print(f"{idx:<5} {date:<15} {pyright_val:>9.1f}% {pyrefly_val:>9.1f}% "
                  f"{ty_val:>9.1f}% {zuban_val:>9.1f}%{marker}")

    print("="*100)

    # Now let's look at what actually happened on day 5 in detail
    if len(benchmark_files) >= 5:
        print("\n" + "="*100)
        print("DETAILED ANALYSIS OF DAY 5")
        print("="*100)

        day5_file = benchmark_files[4]  # 0-indexed, so day 5 is index 4
        date = day5_file.split('/')[-1].replace('benchmark_', '').replace('.json', '')
        print(f"\nDate: {date}")
        print(f"File: {day5_file}\n")

        with open(day5_file, 'r') as f:
            data = json.load(f)

        # Find scipy
        for package_result in data.get('results', []):
            if package_result['package_name'] == 'scipy':
                print("Full scipy metrics:")
                print("-"*100)

                metrics = package_result.get('metrics', {})
                for lsp_name in sorted(metrics.keys()):
                    lsp_data = metrics[lsp_name]
                    print(f"\n{lsp_name.upper()}:")
                    print(f"  OK: {lsp_data.get('ok')}")
                    print(f"  Runs: {lsp_data.get('runs')}")
                    print(f"  OK count: {lsp_data.get('ok_count')}")
                    print(f"  Found count: {lsp_data.get('found_count')}")
                    print(f"  Valid count: {lsp_data.get('valid_count')}")
                    print(f"  Valid %: {lsp_data.get('valid_pct')}%")
                    print(f"  Errors: {lsp_data.get('errors')}")

                break

        print("\n" + "="*100)

        # Compare with day 4 and day 6
        print("\nCOMPARISON WITH ADJACENT DAYS")
        print("="*100)

        for day_offset, label in [(-1, "Day 4"), (0, "Day 5"), (1, "Day 6")]:
            day_idx = 4 + day_offset
            if 0 <= day_idx < len(benchmark_files):
                filepath = benchmark_files[day_idx]
                date = filepath.split('/')[-1].replace('benchmark_', '').replace('.json', '')

                with open(filepath, 'r') as f:
                    data = json.load(f)

                for package_result in data.get('results', []):
                    if package_result['package_name'] == 'scipy':
                        metrics = package_result.get('metrics', {})
                        print(f"\n{label} ({date}):")
                        print(f"  {'LSP':<10} {'Valid/Total':>15} {'Valid %':>10}")
                        print(f"  {'-'*10} {'-'*15} {'-'*10}")
                        for lsp_name in sorted(metrics.keys()):
                            lsp_data = metrics[lsp_name]
                            valid = lsp_data.get('valid_count', 0)
                            runs = lsp_data.get('runs', 0)
                            valid_pct = lsp_data.get('valid_pct', 0)
                            print(f"  {lsp_name:<10} {valid:>3}/{runs:<3} ({valid_pct:>6.1f}%) {valid_pct:>10.1f}%")
                        break


def main() -> None:
    investigate_scipy_day5()


if __name__ == "__main__":
    main()
