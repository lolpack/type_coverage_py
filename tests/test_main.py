from main import main, analyze_package
import pytest
from unittest.mock import Mock
from io import BytesIO
import tarfile
import tempfile
import os
import sys
import requests
from typing import Any, Optional

# Add the directory containing main.py to sys.path
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))


def mock_download_typeshed_csv() -> dict[str, Any]:
    # Return a mock dictionary that would simulate the CSV data
    return {
        "package_a": {"typeshed_coverage": 85.0},
        "package_b": {"typeshed_coverage": 90.0}
    }


def create_mock_tar_gz() -> bytes:
    # Create a mock tar.gz file in memory
    tar_bytes = BytesIO()
    with tarfile.open(fileobj=tar_bytes, mode='w:gz') as tar:
        # Add a dummy file to the tar.gz
        info = tarfile.TarInfo(name="test.py")
        info.size = len(b"print('Hello, world!')")
        tar.addfile(info, BytesIO(b"print('Hello, world!')"))
    tar_bytes.seek(0)
    return tar_bytes.read()


def mock_get(url: str, *args: Any, **kwargs: Any) -> Any:
    class MockResponse:
        def __init__(self, url: str):
            self.url = url
            if "fake_package.tar.gz" in url or "package_" in url:
                self.status_code = 200
            else:
                self.status_code = 404

        def raise_for_status(self) -> None:
            if self.status_code != 200:
                raise requests.exceptions.HTTPError(
                    f"HTTP {self.status_code} Error: {self.url}")

        def json(self) -> dict[str, Any]:
            if "package_a-stubs" in self.url:
                return {
                    "info": {"name": "package_a-stubs"},
                    "urls": [{"packagetype": "sdist", "url": "https://example.com/fake_package.tar.gz"}],
                }
            return {}

        @property
        def content(self) -> bytes:
            if self.status_code == 200:
                return create_mock_tar_gz()
            return b""

    return MockResponse(url)


def test_main_with_write_json_and_write_html(monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_load_and_sort_top_packages(json_file: str) -> list[dict[str, Any]]:
        return [
            {"download_count": 1000, "project": "package_a"},
            {"download_count": 500, "project": "package_b"},
        ]

    mock_generate_report = Mock()
    mock_generate_report_html = Mock()

    monkeypatch.setattr("main.load_and_sort_top_packages",
                        mock_load_and_sort_top_packages)
    monkeypatch.setattr("main.generate_report", mock_generate_report)
    monkeypatch.setattr("main.generate_report_html", mock_generate_report_html)
    monkeypatch.setattr("main.download_typeshed_csv",
                        mock_download_typeshed_csv)
    monkeypatch.setattr("requests.get", mock_get)

    with tempfile.TemporaryDirectory() as temp_dir:
        json_file = os.path.join(temp_dir, 'package_report.json')
        monkeypatch.setattr("main.JSON_REPORT_FILE", json_file)

        # Test when --write-json and --write-html flags are passed
        main(top_n=2, write_json=True, write_html=True)

        # Check that the JSON file was created
        assert os.path.exists(json_file)

        # Check that the HTML report was generated
        mock_generate_report_html.assert_called_once()


def test_main_without_write_json_and_write_html(monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_load_and_sort_top_packages(json_file: str) -> list[dict[str, Any]]:
        return [
            {"download_count": 1000, "project": "package_a"},
            {"download_count": 500, "project": "package_b"},
        ]

    mock_generate_report = Mock()
    mock_generate_report_html = Mock()

    monkeypatch.setattr("main.load_and_sort_top_packages",
                        mock_load_and_sort_top_packages)
    monkeypatch.setattr("main.generate_report", mock_generate_report)
    monkeypatch.setattr("main.generate_report_html", mock_generate_report_html)
    monkeypatch.setattr("main.download_typeshed_csv",
                        mock_download_typeshed_csv)
    monkeypatch.setattr("requests.get", mock_get)

    with tempfile.TemporaryDirectory() as temp_dir:
        json_file = os.path.join(temp_dir, 'package_report.json')
        monkeypatch.setattr("main.JSON_REPORT_FILE", json_file)

        # Test when --write-json and --write-html flags are not passed
        main(top_n=2, write_json=False, write_html=False)

        # Check that the JSON file was NOT created
        assert not os.path.exists(json_file)

        # Check that the HTML report generation was NOT called
        mock_generate_report_html.assert_not_called()


def test_main_analyze_package(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:  # Create a temp directory here
        def mock_extract_files(package_name: str, temp_dir: str) -> tuple[list[str], bool]:
            return [
                f"{temp_dir}/package_a/module.py",
                f"{temp_dir}/package_a/tests/test_module.py"
            ], True

        def mock_check_typeshed(package_name: str) -> bool:
            return True

        def mock_find_stub_files(package_name: str) -> list[str]:
            return [f"{temp_dir}/package_a/module.pyi"]

        def mock_merge_files_with_stubs(non_test_files: list[str], stub_files: list[str]) -> list[str]:
            return non_test_files + stub_files

        def mock_calculate_overall_coverage(files: list[str]) -> dict[str, float]:
            # Check if the files are test or non-test files based on path
            if any("tests" in file for file in files):
                return {
                    "parameter_coverage": 50.0,  # Test files have lower coverage
                    "return_type_coverage": 50.0,
                    "skipped_files": 1,
                    "surface_area": 100,
                }
            else:
                return {
                    "parameter_coverage": 80.0,  # Non-test files have higher coverage
                    "return_type_coverage": 80.0,
                    "skipped_files": 1,
                    "surface_area": 100,
                }
        mock_generate_report = Mock()

        # Patch the correct module path for calculate_overall_coverage
        monkeypatch.setattr("main.extract_files", mock_extract_files)
        monkeypatch.setattr("main.check_typeshed", mock_check_typeshed)
        monkeypatch.setattr("main.find_stub_files", mock_find_stub_files)
        monkeypatch.setattr("main.merge_files_with_stubs",
                            mock_merge_files_with_stubs)
        monkeypatch.setattr("main.calculate_overall_coverage",
                            mock_calculate_overall_coverage)
        monkeypatch.setattr("main.generate_report", mock_generate_report)
        monkeypatch.setattr("requests.get", mock_get)

        # Test with a single package analysis
        package_report = analyze_package(
            "package_a", rank=1, download_count=1000)

        # Check that the report contains the expected data
        assert package_report["CoverageData"]["parameter_coverage"] == 80.0
        assert package_report["CoverageData"]["return_type_coverage"] == 80.0
        assert package_report["CoverageData"]["param_coverage_with_tests"] == 50.0
        assert package_report["CoverageData"]["return_coverage_with_tests"] == 50.0
        assert package_report["CoverageData"]["skipped_files"] == 1
        mock_generate_report.assert_called_once()


def test_main_analyze_package_with_non_typeshed_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        def mock_extract_files(package_name: str, temp_dir: str) -> tuple[list[str], bool]:
            if package_name == "package_a-stubs":
                return [f"{temp_dir}/package_a/module.pyi"], True
            else:
                return [
                    f"{temp_dir}/package_a/module.py",
                    f"{temp_dir}/package_a/tests/test_module.py"
                ], True

        def mock_check_typeshed(package_name: str) -> bool:
            return False  # Simulate no Typeshed stubs available

        def mock_find_stub_package(package_name: str) -> Optional[str]:
            if package_name == "package_a":
                return "https://pypi.org/project/package_a-stubs/"
            return None

        def mock_find_stub_files(package_name: str) -> list[str]:
            return [f"{temp_dir}/package_a/module.pyi"]

        def mock_merge_files_with_stubs(non_test_files: list[str], stub_files: list[str]) -> list[str]:
            return non_test_files + stub_files

        def mock_calculate_overall_coverage(files: list[str]) -> dict[str, float]:
            if any("tests" in file for file in files):
                # Test files coverage
                return {
                    "parameter_coverage": 50.0,
                    "return_type_coverage": 50.0,
                    "skipped_files": 1,
                    "surface_area": 100,
                }
            elif any("module.pyi" in file for file in files):
                # Stub files coverage
                return {
                    "parameter_coverage": 80.0,
                    "return_type_coverage": 80.0,
                    "skipped_files": 0,
                    "surface_area": 100,
                }
            else:
                # Non-test files without stubs
                return {
                    "parameter_coverage": 70.0,
                    "return_type_coverage": 70.0,
                    "skipped_files": 0,
                    "surface_area": 100,
                }

        mock_generate_report = Mock()

        monkeypatch.setattr("main.extract_files", mock_extract_files)
        monkeypatch.setattr("main.check_typeshed", mock_check_typeshed)
        monkeypatch.setattr("main.find_stub_files", mock_find_stub_files)
        monkeypatch.setattr("main.find_stub_package", mock_find_stub_package)
        monkeypatch.setattr("main.merge_files_with_stubs",
                            mock_merge_files_with_stubs)
        monkeypatch.setattr("main.calculate_overall_coverage",
                            mock_calculate_overall_coverage)
        monkeypatch.setattr("main.generate_report", mock_generate_report)
        monkeypatch.setattr("requests.get", mock_get)

        # Test with a package that has non-typeshed stubs
        package_report = analyze_package(
            "package_a", rank=1, download_count=1000)

        # Check that the non-typeshed stub URL is included in the report
        assert package_report["non_typeshed_stubs"] == "https://pypi.org/project/package_a-stubs/"

        # Check that the report contains the expected data
        assert package_report["CoverageData"]["parameter_coverage"] == 70.0
        assert package_report["CoverageData"]["return_type_coverage"] == 70.0
        assert package_report["CoverageData"]["param_coverage_with_tests"] == 50.0
        assert package_report["CoverageData"]["return_coverage_with_tests"] == 50.0
        assert package_report["CoverageData"]["skipped_files"] == 1
        mock_generate_report.assert_called_once()
