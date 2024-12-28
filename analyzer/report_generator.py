from typing import Dict, Union
import os
import datetime

HTML_REPORT_FILE = "index.html"
JSON_REPORT_FILE = "package_report.json"
HISTORICAL_DATA_DIR = "historical_data"
HISTORICAL_HTML_DIR = os.path.join(HISTORICAL_DATA_DIR, "html")
HISTORICAL_JSON_DIR = os.path.join(HISTORICAL_DATA_DIR, "json")

def archive_old_reports() -> None:
    """Move the old reports to the historical_data directory with a timestamp."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d")
    os.makedirs(HISTORICAL_HTML_DIR, exist_ok=True)
    os.makedirs(HISTORICAL_JSON_DIR, exist_ok=True)

    # Archive old HTML report
    if os.path.exists(HTML_REPORT_FILE):
        new_html_name = os.path.join(HISTORICAL_HTML_DIR, f"index-{timestamp}.html")
        os.rename(HTML_REPORT_FILE, new_html_name)
        print(f"Archived {HTML_REPORT_FILE} to {new_html_name}")

    # Archive old JSON report
    if os.path.exists(JSON_REPORT_FILE):
        new_json_name = os.path.join(HISTORICAL_JSON_DIR, f"package_report-{timestamp}.json")
        os.rename(JSON_REPORT_FILE, new_json_name)
        print(f"Archived {JSON_REPORT_FILE} to {new_json_name}")

def update_main_html_with_links() -> None:
    """Update the main HTML file with a link to view historical data."""
    if not os.path.exists(HISTORICAL_HTML_DIR):
        return

    historical_links = []
    for file_name in sorted(os.listdir(HISTORICAL_HTML_DIR)):
        if file_name.endswith(".html"):
            link = f"<li><a href='{os.path.join(HISTORICAL_HTML_DIR, file_name)}'>{file_name}</a></li>"
            historical_links.append(link)

    # Add the links to the main HTML
    historical_section = f"""
    <h2>Historical Data</h2>
    <ul>
        {''.join(historical_links)}
    </ul>
    """
    with open(HTML_REPORT_FILE, "r") as file:
        html_content = file.read()

    updated_html_content = html_content.replace(
        "</body>", historical_section + "\n</body>"
    )
    with open(HTML_REPORT_FILE, "w") as file:
        file.write(updated_html_content)
    print("Updated main HTML with historical data links.")

def generate_report(package_data: Dict[str, Dict[str, float]], package_name: str) -> None:
    """Generates a report of the coverage data."""
    coverage_data = package_data["CoverageData"]
    typeshed_data = package_data.get("TypeshedData", {})
    
    # Print package coverage
    print(f"Coverage Report for {package_name}:")
    print(f"Has typeshed stubs: {package_data['HasTypeShed']}")
    print(f"Parameter Type Coverage: {coverage_data['parameter_coverage']:.2f}%")
    print(f"Return Type Coverage: {coverage_data['return_type_coverage']:.2f}%")
    print(f"Parameter Type Coverage With Stubs: {coverage_data['parameter_coverage_with_stubs']:.2f}%")
    print(f"Return Type Coverage With Stubs: {coverage_data['return_type_coverage_with_stubs']:.2f}%")
    print(f"Parameter Type Coverage With Tests: {coverage_data['param_coverage_with_tests']:.2f}%")
    print(f"Return Type Coverage With Tests: {coverage_data['return_coverage_with_tests']:.2f}%")
    
    # Print Typeshed data if available
    if typeshed_data:
        print("\nTypeshed Coverage Stats:")
        print(f"Completeness Level: {typeshed_data.get('completeness_level', 'N/A')}")
        print(f"Annotated Parameters: {typeshed_data.get('annotated_parameters', 'N/A')}")
        print(f"Unannotated Parameters: {typeshed_data.get('unannotated_parameters', 'N/A')}")
        print(f"Parameter Coverage: {typeshed_data.get('% param')}")
        print(f"Annotated Returns: {typeshed_data.get('annotated_returns', 'N/A')}")
        print(f"Unannotated Returns: {typeshed_data.get('unannotated_returns', 'N/A')}")
        print(f"Return Coverage: {typeshed_data.get('% return')}")
        print(f"Stubtest Strictness: {typeshed_data.get('stubtest_strictness', 'N/A')}")
        print(f"Stubtest Platforms: {typeshed_data.get('stubtest_platforms', 'N/A')}")
    print("-" * 40)


def get_color(percentage: float) -> str:
    """Calculate a subtle but noticeable color gradient from light red (0%) to light green (100%)."""
    if percentage < 50:
        # Transition from light red to light yellow for 0% to 50%
        red = 255
        green = int(255 * (percentage / 50))
    else:
        # Transition from light yellow to light green for 50% to 100%
        red = int(255 * ((100 - percentage) / 50))
        green = 255
    
    blue = 200  # A small amount of blue for a softer, more pleasant color
    return f"rgb({red},{green},{blue})"

def create_percentage_row(percentage: Union[str, float]) -> str:
    if type(percentage) == str:
        return f"<td class=\"coverage-cell\">{percentage}</td>"

    percentage_color = get_color(float(percentage))
    return f"<td class=\"coverage-cell\" style=\"background-color: {percentage_color};\">{percentage:.2f}%</td>"

def generate_report_html(package_report: Dict[str, Dict[str, Dict[str, float]]]) -> None:
    """Generates an HTML report of the package coverage data."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Package Type Coverage Report</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 40px;
                background-color: #f4f4f4;
            }
            h1 {
                text-align: center;
                color: #333;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
                font-size: 18px;
                text-align: left;
            }
            table th, table td {
                padding: 12px;
                border: 1px solid #ddd;
            }
            table th {
                background-color: #f2f2f2;
                color: #333;
            }
            table tr:nth-child(even) {
                background-color: #f9f9f9;
            }
            table tr:hover {
                background-color: #f1f1f1;
            }
            .coverage-cell {
                text-align: right;
                padding-right: 10px;
                color: #333;  /* Darker text color for better readability */
            }
            .skipped-cell {
                text-align: center;
                color: #d9534f; /* Red color for skipped text */
            }
            .github-link {
                text-align: center;
                margin-top: 20px;
                font-size: 16px;
            }
            .github-link a {
                color: #0066cc;
                text-decoration: none;
            }
            .github-link a:hover {
                text-decoration: underline;
            }
        </style>
    </head>
    <body>
        <h1>Package Type Coverage Report</h1>
        <p class="github-link">See code and methodology here: 
            <a href="https://github.com/lolpack/type_coverage_py" target="_blank">
                https://github.com/lolpack/type_coverage_py
            </a>
        </p>
        <table>
            <tr>
                <th>Ranking</th>
                <th>Package Name</th>
                <th>Download Count</th>
                <th>Has Typeshed</th>
                <th>Parameter Type Coverage</th>
                <th>Return Type Coverage</th>
                <th>Parameter Coverage with Typeshed</th>
                <th>Return Type Coverage with Typeshed</th>
                <th>Parameter Coverage with Test</th>
                <th>Return Type Coverage with Test</th>
                <th>Typeshed Parameter Type Coverage</th>
                <th>Typeshed Return Type Coverage</th>
                <th>Skipped Files</th>
                <th>Typeshed Completeness Level</th>
                <th>Typeshed Stubtest Strictness</th>
            </tr>
    """

    for package_name, details in package_report.items():
        coverage_data = details['CoverageData']
        typeshed_data = details.get('TypeshedData', {})
        parameter_coverage = round(coverage_data['parameter_coverage'], 2)
        return_coverage = round(coverage_data['return_type_coverage'], 2)

        parameter_coverage_with_stubs = round(coverage_data.get('parameter_coverage_with_stubs', 0), 2)
        return_coverage_with_stubs = round(coverage_data.get('return_type_coverage_with_stubs', 0), 2)
        param_coverage_with_tests = round(coverage_data.get('param_coverage_with_tests', 0), 2)
        return_coverage_with_tests = round(coverage_data.get('return_coverage_with_tests', 0), 2)    

        skipped_files = f"{coverage_data['skipped_files']}"
        
        completeness_level = typeshed_data.get('completeness_level', 'N/A')
        stubtest_strictness = typeshed_data.get('stubtest_strictness', 'N/A')
        typshed_return_percent = typeshed_data.get('% param', 'N/A')
        typshed_param_percent = typeshed_data.get('% return', 'N/A')

        html_content += f"""
            <tr>
                <td>{details['DownloadRanking']}</td>
                <td>{package_name}</td>
                <td>{details['DownloadCount']}</td>
                <td>{'Yes' if details['HasTypeShed'] else 'No'}</td>
                {create_percentage_row(parameter_coverage)}
                {create_percentage_row(return_coverage)}
                {create_percentage_row(parameter_coverage_with_stubs)}
                {create_percentage_row(return_coverage_with_stubs)}
                {create_percentage_row(param_coverage_with_tests)}
                {create_percentage_row(return_coverage_with_tests)}
                {create_percentage_row(typshed_param_percent)}
                {create_percentage_row(typshed_return_percent)}
                <td class="skipped-cell">{skipped_files}</td>
                <td>{completeness_level}</td>
                <td>{stubtest_strictness}</td>
            </tr>
        """

    html_content += """
        </table>
    </body>
    </html>
    """

    # Output the HTML to a file
    with open(HTML_REPORT_FILE, "w") as file:
        file.write(html_content)

    print(f"HTML report generated: {HTML_REPORT_FILE}")

