# # Regenerates the HTML report from the JSON report file, useful when making HTML only styling changes
# import json

# from analyzer.report_generator import generate_report_html

# report = None


# def generate_report(html_report_file: str) -> None:
#     """Generates a report of the coverage data."""
#     # Load the JSON report file
#     with open("package_report.json", "r") as f:
#         report = json.load(f)
#         # Generate the HTML report
#         generate_report_html(report, html_report_file)
#     print(f"Generated HTML report: {html_report_file}")
