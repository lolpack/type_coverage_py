import os
import tarfile
import zipfile
from typing import Any, Optional

import requests


def find_stub_package(package_name: str) -> Optional[str]:
    """Checks if a stub package exists for the given package on PyPI."""
    stub_package_name = f"{package_name}-stubs"
    pypi_url = f"https://pypi.org/pypi/{stub_package_name}/json"
    response = requests.get(pypi_url)

    if response.status_code == 200:
        return f"https://pypi.org/project/{stub_package_name}/"
    return None


def download_package(package_name: str, temp_dir: str) -> str:
    """Downloads the specified package from PyPI and extracts it to a temporary directory."""
    # Fetch the package metadata from PyPI
    pypi_url = f"https://pypi.org/pypi/{package_name}/json"
    response = requests.get(pypi_url)
    response.raise_for_status()

    # The API returns a JSON response, so 'data' is a dictionary
    data: dict[str, Any] = response.json()

    # 'urls' is a list of dictionaries containing information about the available distributions
    urls: list[dict[str, Any]] = data.get("urls", [])

    sdist_url: str | None = None
    for url_info in urls:
        # 'url_info' is a dictionary, and we're accessing the 'packagetype' and 'url' keys
        if url_info.get("packagetype") == "sdist":
            sdist_url = url_info.get("url")
            break

    if not sdist_url:
        raise ValueError(
            f"Source distribution for package '{
                package_name}' not found on PyPI."
        )

    # Download the source distribution
    sdist_response = requests.get(sdist_url)
    sdist_response.raise_for_status()

    # Determine the archive type and extract
    if sdist_url.endswith(".zip"):
        archive_path = os.path.join(temp_dir, f"{package_name}.zip")
        with open(archive_path, "wb") as archive_file:
            archive_file.write(sdist_response.content)
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(temp_dir)
    elif sdist_url.endswith((".tar.gz", ".tgz")):
        archive_path = os.path.join(temp_dir, f"{package_name}.tar.gz")
        with open(archive_path, "wb") as archive_file:
            archive_file.write(sdist_response.content)
        with tarfile.open(archive_path, "r:gz") as tar_ref:
            # type: ignore reportDeprecated python 3.14
            tar_ref.extractall(temp_dir)
    else:
        raise ValueError(f"Unsupported archive format for {sdist_url}.")

    # Return the path to the extracted package
    return temp_dir


def extract_files(package_name: str, temp_dir: str) -> tuple[list[str], bool]:
    """Extracts Python files from the downloaded package directory."""
    try:
        package_dir = download_package(package_name, temp_dir)
    except ValueError as e:
        print(f"Warning: {e}")
        return [], False

    python_files: list[str] = []
    has_py_typed_file = False

    for root, _, files in os.walk(package_dir):
        for file in files:
            if file.endswith(".py") or file.endswith(".pyi"):
                python_files.append(os.path.join(root, file))
            if file.endswith("py.typed"):
                has_py_typed_file = True

    return python_files, has_py_typed_file
