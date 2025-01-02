# Regenerates the HTML report from the JSON report file, useful when making HTML only styling changes
import json
from analyzer.report_generator import generate_report_html
report = None
with open("package_report.json", "r") as f:
    report = json.load(f)
    generate_report_html(report)
