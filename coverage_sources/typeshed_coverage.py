import csv
from typing import Any

import requests

CSV_URL = "https://alexwaygood.github.io/typeshed-stats/stats_as_csv.csv"


def generate_coverage_percent(annotated: str, unannotated: str) -> float | str:
    if float(unannotated) <= 0:
        return "N/A"
    return (float(annotated) / (float(unannotated) + float(annotated))) * 100


def download_typeshed_csv() -> dict[str, dict[str, Any]]:
    """Download and parse the typeshed CSV file into a dictionary."""
    response = requests.get(CSV_URL)
    response.raise_for_status()  # Ensure the download was successful

    typeshed_data: dict[str, dict[str, Any]] = {}
    decoded_content = response.content.decode("utf-8").splitlines()
    csv_reader = csv.DictReader(decoded_content)

    for row in csv_reader:
        package_name = row["package_name"].strip().lower()
        annotated_parameters = row["annotated_parameters"]
        unannotated_parameters = row["unannotated_parameters"]
        annotated_returns = row["annotated_returns"]
        unannotated_returns = row["unannotated_returns"]

        param_percent: float | str = generate_coverage_percent(
            annotated_parameters, unannotated_parameters
        )
        return_percent: float | str = generate_coverage_percent(
            annotated_returns, unannotated_returns
        )
        typeshed_data[package_name] = {
            "completeness_level": row["completeness_level"],
            "annotated_parameters": annotated_returns,
            "unannotated_parameters": unannotated_returns,
            "% param": param_percent,
            "annotated_returns": annotated_returns,
            "unannotated_returns": unannotated_returns,
            "% return": return_percent,
            "stubtest_strictness": row["stubtest_strictness"],
            "stubtest_platforms": row["stubtest_platforms"],
        }

    return typeshed_data
