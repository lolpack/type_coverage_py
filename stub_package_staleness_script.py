# Calculating staleness from stub packages

from typing import Any
import json

import requests

from datetime import datetime
format_str = "%Y-%m-%dT%H:%M:%S"


def get_latest_release_time_for_package(package_name: str) -> tuple[datetime, int]:
    # Fetch the package metadata from PyPI
    pypi_url = f"https://pypi.org/pypi/{package_name}/json"
    response = requests.get(pypi_url)
    response.raise_for_status()

    # The API returns a JSON response, so 'data' is a dictionary
    data: dict[str, Any] = response.json()
    latest_version = data['info']['version']
    n_releases = len(data['releases'])
    release_info = data['releases'][latest_version]
    latest_upload = max(release_info, key=lambda x: datetime.strptime(x['upload_time'], format_str))
    return datetime.strptime(latest_upload['upload_time'], format_str), n_releases


with open("stub_packages.json", "r") as f:
    data = json.load(f)
    for d in data:
        package_release_time, n_package_release = get_latest_release_time_for_package(d)
        stub_release_time, n_stub_releases = get_latest_release_time_for_package(d + "-stubs")
        time_difference = package_release_time - stub_release_time
        print(f"{d}: {time_difference.days} days stale, {n_package_release} releases, {n_stub_releases} stub releases")
