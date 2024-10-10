import tempfile
import shutil
import json
import sys
import argparse
from typing import Optional, Any, Dict, List
from analyzer.package_analyzer import extract_files
from analyzer.typeshed_checker import check_typeshed, find_stub_files, merge_files_with_stubs
from analyzer.coverage_calculator import calculate_overall_coverage
from analyzer.report_generator import generate_report, generate_report_html
from coverage_sources.typeshed_coverage import download_typeshed_csv

JSON_REPORT_FILE = 'package_report.json'
TOP_PYPI_PACKAGES = 'top-pypi-packages-30-days.min.json'

def load_and_sort_top_packages(json_file: str) -> List[Dict[str, Any]]:
    """Load the JSON file and sort it by download_count."""
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    sorted_rows = sorted(data['rows'], key=lambda x: x['download_count'], reverse=True)
    return sorted_rows

def separate_test_files(files: List[str]) -> List[str]:
    """Separate files into test files and non-test files."""
    non_test_files: List[str] = []
    
    for file in files:
        if "test" not in file or "tests" not in file:
            non_test_files.append(file)
    
    return non_test_files

def analyze_package(package_name: str, rank: Optional[int] = None, download_count: Optional[int] = None, typeshed_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Analyze a single package and generate a report."""
    package_report: Dict[str, Any] = {
        "DownloadCount": download_count,
        "DownloadRanking": rank,
        "CoverageData": {}
    }

    # Create a temporary directory
    temp_dir = tempfile.mkdtemp()

    try:
        print(f"Temporary directory created: {temp_dir} for {package_name}")
        print(f"Analyzing package: {package_name} rank {rank}")

        # Download and extract package files
        files = extract_files(package_name, temp_dir)        

        # Separate test and non-test files
        non_test_files = separate_test_files(files)

        non_test_coverage = calculate_overall_coverage(non_test_files)
        parameter_coverage = non_test_coverage["parameter_coverage"]
        return_type_coverage = non_test_coverage["return_type_coverage"]
        skipped_files_non_tests = non_test_coverage["skipped_files"]
        
        package_report["CoverageData"]["parameter_coverage"] = parameter_coverage
        package_report["CoverageData"]["return_type_coverage"] = return_type_coverage

        total_test_coverage = calculate_overall_coverage(files)
        skipped_tests = total_test_coverage["skipped_files"]

        package_report["CoverageData"]["param_coverage_with_tests"] = total_test_coverage["parameter_coverage"]
        package_report["CoverageData"]["return_coverage_with_tests"] = total_test_coverage["return_type_coverage"]

        # Merge non-test files with typeshed stubs
        typeshed_exists = check_typeshed(package_name)
        package_report["HasTypeShed"] = typeshed_exists
        if typeshed_exists:
            print(f"Typeshed exists for {package_name}. Including it in analysis.")
            stub_files = find_stub_files(package_name)
            merged_files = merge_files_with_stubs(non_test_files, stub_files)

            # Calculate coverage with stubs
            total_test_coverage_stubs = calculate_overall_coverage(merged_files)
            parameter_coverage_with_stubs = total_test_coverage_stubs["parameter_coverage"]
            return_type_coverage_with_stubs = total_test_coverage_stubs["return_type_coverage"]
            skipped_files_with_stubs = total_test_coverage["skipped_files"]
        else:
            parameter_coverage_with_stubs = parameter_coverage
            return_type_coverage_with_stubs = return_type_coverage
            skipped_files_with_stubs = skipped_files_non_tests

        # Add typeshed data if available
        if typeshed_data and package_name in typeshed_data:
            package_report["TypeshedData"] = typeshed_data[package_name]
        else:
            package_report["TypeshedData"] = {}

        package_report["CoverageData"]["parameter_coverage_with_stubs"] = parameter_coverage_with_stubs
        package_report["CoverageData"]["return_type_coverage_with_stubs"] = return_type_coverage_with_stubs

        skipped_files_total = max(skipped_files_with_stubs, skipped_tests)
        package_report["CoverageData"]["skipped_files"] = skipped_files_total

        # Write CLI
        generate_report(package_report, package_name)

    finally:
        # Clean up the temporary directory
        shutil.rmtree(temp_dir)
        print(f"Temporary directory {temp_dir} has been deleted.")

    return package_report

def main(top_n: Optional[int] = None, package_name: Optional[str] = None, write_json: bool = False, write_html: bool = False) -> None:
    package_report: Dict[str, Any] = {}

    # Download the CSV file with typeshed stats
    typeshed_data = download_typeshed_csv()

    if package_name:
        # Analyze a specific package
        print(f"Analyzing specific package: {package_name}")
        package_report[package_name] = analyze_package(package_name, typeshed_data=typeshed_data)
    else:
        # Analyze top N packages
        sorted_packages = load_and_sort_top_packages(TOP_PYPI_PACKAGES)
        top_packages = sorted_packages[:top_n]

        for rank, package_data in enumerate(top_packages, start=1):
            package_name = package_data['project']
            download_count = package_data['download_count']

            if package_name:  # Ensure package_name is not None
                package_report[package_name] = analyze_package(package_name, rank=rank, download_count=download_count, typeshed_data=typeshed_data)

    # Conditionally write the JSON report
    if write_json:
        with open(JSON_REPORT_FILE, "w") as json_file:
            json.dump(package_report, json_file, indent=4)
        print("package_report.json file generated.")

    # Conditionally generate the HTML report
    if write_html:
        generate_report_html(package_report)
        print("HTML report generated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze Python package type coverage.")
    parser.add_argument('top_n', type=int, nargs='?', help="Analyze the top N PyPI packages.")
    parser.add_argument('--package-name', type=str, help="Analyze a specific package by name.")
    parser.add_argument('--write-json', action='store_true', help="Write the output to a JSON report.")
    parser.add_argument('--write-html', action='store_true', help="Generate an HTML report.")

    args = parser.parse_args()

    if args.package_name:
        main(package_name=args.package_name, write_json=args.write_json, write_html=args.write_html)
    elif args.top_n:
        if not (1 <= args.top_n <= 8000):
            print("Error: <top_n> must be an integer between 1 and 8000.")
            sys.exit(1)
        main(top_n=args.top_n, write_json=args.write_json, write_html=args.write_html)
    else:
        print("Error: Either provide a top N number or a package name.")
        sys.exit(1)
