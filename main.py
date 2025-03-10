import argparse
import concurrent.futures
import json
import os
import shutil
import sys
import tempfile
from typing import Any, Optional

from analyzer.coverage_calculator import calculate_overall_coverage
from analyzer.package_analyzer import extract_files, find_stub_package
from analyzer.report_generator import (
    archive_old_reports,
    generate_report,
    generate_report_html,
    update_main_html_with_links,
)
from analyzer.typeshed_checker import (
    check_typeshed,
    find_stub_files,
    merge_files_with_stubs,
)
from analyzer.historical_view_generator import generate_historical_graphs
from coverage_sources.get_pyright_stats import main as get_pyright_stats
from coverage_sources.typeshed_coverage import download_typeshed_csv

JSON_REPORT_FILE = "package_report.json"
HTML_REPORT_FILE = "index.html"
TOP_PYPI_PACKAGES = "top-pypi-packages-30-days.min.json"
STUB_PACKAGES = "stub_packages.json"

HISTORICAL_DATA_DIR = "historical_data"



def load_and_sort_top_packages(json_file: str) -> list[dict[str, Any]]:
    """Load the JSON file and sort it by download_count."""
    with open(json_file, "r") as f:
        data = json.load(f)

    sorted_rows = sorted(data["rows"], key=lambda x: x["download_count"], reverse=True)
    return sorted_rows


def separate_test_files(files: list[str]) -> list[str]:
    """Separate files into test files and non-test files."""
    non_test_files: list[str] = []
    for file in files:
        parts = [x.replace("_", "") for x in file.split("/")]
        if "test" in parts or "tests" in parts:
            continue
        non_test_files.append(file)
    return non_test_files


def analyze_package(
    package_name: str,
    rank: Optional[int] = None,
    download_count: Optional[int] = None,
    typeshed_data: Optional[dict[str, Any]] = None,
    has_stub_package: bool = False,
    parallel: bool = False,
) -> dict[str, Any]:
    """Analyze a single package and generate a report."""
    package_report: dict[str, Any] = {
        "DownloadCount": download_count,
        "DownloadRanking": rank,
        "CoverageData": {},
    }

    # Create a temporary directory
    temp_dir = tempfile.mkdtemp()
    stub_package_dir = tempfile.mkdtemp() if has_stub_package else None

    try:
        print(f"Analyzing package: {package_name} rank {rank}")

        # Download and extract package files
        files, has_py_typed_file = extract_files(package_name, temp_dir)

        # Separate test and non-test files
        non_test_files = separate_test_files(files)

        stub_has_py_typed_file = False
        if stub_package_dir:
            stub_package_files, stub_has_py_typed_file = extract_files(
                package_name + "-stubs", stub_package_dir
            )
            files = merge_files_with_stubs(files, stub_package_files)
            non_test_files = merge_files_with_stubs(non_test_files, stub_package_files)

        package_report["HasPyTypedFile"] = has_py_typed_file or stub_has_py_typed_file

        non_test_coverage = calculate_overall_coverage(non_test_files)
        parameter_coverage = non_test_coverage["parameter_coverage"]
        return_type_coverage = non_test_coverage["return_type_coverage"]
        skipped_files_non_tests = non_test_coverage["skipped_files"]

        package_report["CoverageData"]["parameter_coverage"] = parameter_coverage
        package_report["CoverageData"]["return_type_coverage"] = return_type_coverage
        package_report["SurfaceArea"] = non_test_coverage["surface_area"]

        total_test_coverage = calculate_overall_coverage(files)
        skipped_tests = total_test_coverage["skipped_files"]

        package_report["CoverageData"]["param_coverage_with_tests"] = (
            total_test_coverage["parameter_coverage"]
        )
        package_report["CoverageData"]["return_coverage_with_tests"] = (
            total_test_coverage["return_type_coverage"]
        )

        # Merge non-test files with typeshed stubs
        typeshed_exists = check_typeshed(package_name)
        package_report["HasTypeShed"] = typeshed_exists
        package_report["HasStubsPackage"] = has_stub_package
        package_report["non_typeshed_stubs"] = "N/A"
        if typeshed_exists:
            if not parallel:
                print(f"Typeshed exists for {package_name}. Including it in analysis.")
            stub_files = find_stub_files(package_name)
            merged_files = merge_files_with_stubs(non_test_files, stub_files)

            # Calculate coverage with stubs
            total_test_coverage_stubs = calculate_overall_coverage(merged_files)
            parameter_coverage_with_stubs = total_test_coverage_stubs[
                "parameter_coverage"
            ]
            return_type_coverage_with_stubs = total_test_coverage_stubs[
                "return_type_coverage"
            ]
            skipped_files_with_stubs = total_test_coverage["skipped_files"]
        else:
            # Check for PyPI stub package if no Typeshed stubs exist
            stub_package_url = find_stub_package(package_name)
            if stub_package_url:
                print(f"Found non-typeshed stub package: {stub_package_url}")
                package_report["non_typeshed_stubs"] = stub_package_url

                # Download and merge PyPI stub files
                stub_temp_dir = tempfile.mkdtemp()
                try:
                    stub_files, _ = extract_files(
                        f"{package_name}-stubs", stub_temp_dir
                    )
                    merged_files = merge_files_with_stubs(non_test_files, stub_files)

                    # Calculate coverage with stubs
                    total_test_coverage_stubs = calculate_overall_coverage(merged_files)
                    parameter_coverage_with_stubs = total_test_coverage_stubs[
                        "parameter_coverage"
                    ]
                    return_type_coverage_with_stubs = total_test_coverage_stubs[
                        "return_type_coverage"
                    ]
                    skipped_files_with_stubs = total_test_coverage["skipped_files"]
                finally:
                    print("temp file removed", stub_temp_dir)
                    shutil.rmtree(stub_temp_dir)
            else:
                print(f"No stubs found for {package_name} in Typeshed or PyPI.")

                parameter_coverage_with_stubs = parameter_coverage
                return_type_coverage_with_stubs = return_type_coverage
                skipped_files_with_stubs = skipped_files_non_tests

        # Add typeshed data if available
        if typeshed_data and package_name in typeshed_data:
            package_report["TypeshedData"] = typeshed_data[package_name]
        else:
            package_report["TypeshedData"] = {}

        package_report["CoverageData"][
            "parameter_coverage_with_stubs"
        ] = parameter_coverage_with_stubs
        package_report["CoverageData"][
            "return_type_coverage_with_stubs"
        ] = return_type_coverage_with_stubs

        skipped_files_total = max(skipped_files_with_stubs, skipped_tests)
        package_report["CoverageData"]["skipped_files"] = skipped_files_total

        # Write CLI
        if not parallel:
            generate_report(package_report, package_name)
    finally:
        # Clean up the temporary directory
        shutil.rmtree(temp_dir)
        if stub_package_dir:
            shutil.rmtree(stub_package_dir)

    return package_report


def get_packages_with_stubs() -> set[str]:
    with open(STUB_PACKAGES, "r") as f:
        data = json.load(f)
    return set(data)


def analyze_package_concurrently(
    package_data: dict[str, Any],
    rank: int,
    typeshed_data: dict[str, dict[str, Any]],
    packages_with_stubs: set[str],
) -> tuple[str, dict[str, Any]] | None:
    package_name = package_data["project"]
    download_count = package_data["download_count"]

    if package_name:  # Ensure package_name is not None
        return package_name, analyze_package(
            package_name,
            rank=rank,
            download_count=download_count,
            typeshed_data=typeshed_data,
            has_stub_package=package_name in packages_with_stubs,
            parallel=True,
        )
    return None


def parallel_analyze_packages(
    top_packages: list[dict[str, Any]],
    typeshed_data: dict[str, dict[str, Any]],
    packages_with_stubs: set[str],
) -> dict[str, Any]:
    package_report: dict[str, Any] = {}
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(
                analyze_package_concurrently,
                package_data,
                rank,
                typeshed_data,
                packages_with_stubs,
            ): package_data
            for rank, package_data in enumerate(top_packages, start=1)
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                package_name, analysis_result = result
                package_report[package_name] = analysis_result
    sorted_pairs = sorted(
        [pair for pair in package_report.items()], key=lambda x: x[1]["DownloadRanking"]
    )
    package_report = {k: v for k, v in sorted_pairs}
    return package_report


def read_packages(file_path: str) -> list[str]:
    try:
        with open(file_path, "r") as f:
            return [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return []


def main(
    top_n: Optional[int] = None,
    package_name: Optional[str] = None,
    write_json: bool = False,
    write_html: bool = False,
    parallel: bool = False,
    create_daily: bool = False,
    package_list: Optional[str] = None,
    pyright_stats: Optional[bool] = False,
    output_list_only: Optional[bool] = False,
) -> None:
    package_report: dict[str, Any] = {}

    # Download the CSV file with typeshed stats
    typeshed_data = download_typeshed_csv()
    packages_with_stubs = get_packages_with_stubs()
    top_packages: list[dict[str, Any]] = []

    if package_name:
        # Analyze a specific package
        print(f"Analyzing specific package: {package_name}")
        package_report[package_name] = analyze_package(
            package_name,
            typeshed_data=typeshed_data,
            has_stub_package=package_name in packages_with_stubs,
        )
        top_packages = [package_report[package_name]]
    else:
        # Analyze top N packages
        sorted_packages = load_and_sort_top_packages(TOP_PYPI_PACKAGES)
        top_packages = sorted_packages[:top_n]

        if package_list:
            included_packages: list[str] = read_packages(package_list)
            top_packages = [
                package
                for package in top_packages
                if package["project"] in included_packages
            ]

        if parallel:
            package_report = parallel_analyze_packages(
                top_packages, typeshed_data, packages_with_stubs
            )
        else:
            for rank, package_data in enumerate(top_packages, start=1):
                name = package_data["project"]
                download_count = package_data["download_count"]
                package_report[name] = analyze_package(
                    name,
                    rank=rank,
                    download_count=download_count,
                    typeshed_data=typeshed_data,
                    has_stub_package=package_name in packages_with_stubs,
                )

    # Call pyright stats and merge data
    if pyright_stats:
        pyright_package_stats: dict[str, Any] = get_pyright_stats([
            {
                "package_name": package_data["project"],
                "has_py_typed": package_report[package_data["project"]]["HasPyTypedFile"]
            } for package_data in top_packages
        ])

        for package, stats in pyright_package_stats.items():
            if package in package_report:
                package_report[package]["pyright_stats"] = stats

    html_report_file = HTML_REPORT_FILE
    json_report_file = JSON_REPORT_FILE
    historical_data_dir = HISTORICAL_DATA_DIR
    historical_html_dir = os.path.join(HISTORICAL_DATA_DIR, "html")
    historical_json_dir = os.path.join(HISTORICAL_DATA_DIR, "json")
    coverag_trends_html = os.path.join(HISTORICAL_DATA_DIR, "coverage-trends.html")

    if output_list_only:
        os.makedirs("prioritized", exist_ok=True)
        html_report_file: str = os.path.join("prioritized", "index.html")
        json_report_file: str = os.path.join("prioritized", "package_report.json")

        historical_data_dir = os.path.join("prioritized", historical_data_dir)
        historical_html_dir: str = os.path.join("prioritized", historical_html_dir)
        historical_json_dir: str = os.path.join("prioritized", historical_json_dir)
        coverag_trends_html: str = os.path.join("prioritized", coverag_trends_html)



    # Archive old report in data section
    if create_daily:
        archive_old_reports(
            html_report_file,
            historical_html_dir,
            historical_json_dir,
            json_report_file
        )

    # Conditionally write the JSON report
    if write_json:
        with open(json_report_file, "w") as json_file:
            json.dump(package_report, json_file, indent=4)
        print(f"{json_report_file} file generated.")

    # Conditionally generate the HTML report
    if write_html:
        generate_report_html(package_report, html_report_file)
        print("HTML report generated.")

    if create_daily:
        update_main_html_with_links(html_report_file, historical_html_dir)
        generate_historical_graphs(historical_json_dir, coverag_trends_html)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze Python package type coverage."
    )
    parser.add_argument(
        "top_n", type=int, nargs="?", help="Analyze the top N PyPI packages."
    )
    parser.add_argument(
        "--package-name", type=str, help="Analyze a specific package by name."
    )
    parser.add_argument(
        "--write-json", action="store_true", help="Write the output to a JSON report."
    )
    parser.add_argument(
        "--write-html", action="store_true", help="Generate an HTML report."
    )
    parser.add_argument(
        "--create-daily",
        action="store_true",
        help="Create a daily report and archive previous data.",
    )
    parser.add_argument(
        "--parallel", action="store_true", help="Analyze packages in parallel."
    )
    parser.add_argument(
        "--pyright-stats", action="store_true", help="Run pyright stats."
    )
    parser.add_argument(
        "--package-list", type=str, help="Path to a file containing a list of packages."
    )

    parser.add_argument(
        "--output-list-only", action="store_true", help="Run pyright stats."
    )

    parser.add_argument(
        "--archive-prioritized", action="store_true", help="Run pyright stats."
    )

    args = parser.parse_args()

    if args.create_daily:
        main(
            top_n=(args.top_n or 8000),
            package_name=args.package_name,
            write_json=True,
            write_html=True,
            create_daily=True,
        )
    elif args.package_name:
        main(
            package_name=args.package_name,
            write_json=args.write_json,
            write_html=args.write_html,
        )
    elif args.top_n:
        if not (1 <= args.top_n <= 8000):
            print("Error: <top_n> must be an integer between 1 and 8000.")
            sys.exit(1)
        main(
            top_n=args.top_n,
            write_json=args.write_json,
            write_html=args.write_html,
            parallel=args.parallel,
            pyright_stats=args.pyright_stats,
        )
    elif args.archive_prioritized:
        if not args.package_list:
            print("Error: Please provide a package list.")
            sys.exit(1)
        main(
            package_list=args.package_list,
            write_json=True,
            write_html=True,
            parallel=args.parallel,
            pyright_stats=True,
            output_list_only=True,
            create_daily=True
        )
    elif args.package_list:
        main(
            package_list=args.package_list,
            write_json=args.write_json,
            write_html=args.write_html,
            parallel=args.parallel,
            pyright_stats=args.pyright_stats,
            output_list_only=args.output_list_only,
        )
    else:
        print("Error: Either provide a top N number or a package name.")
        sys.exit(1)
