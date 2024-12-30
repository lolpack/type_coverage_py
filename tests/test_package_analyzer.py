from io import BytesIO
import tarfile
import tempfile
import os
from typing import Any
import pytest
from unittest.mock import Mock, patch
from analyzer.package_analyzer import download_package, extract_files, find_stub_package

def test_download_package(monkeypatch: pytest.MonkeyPatch) -> None:
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

    def mock_get(*args: Any, **kwargs: Any) -> Any:
        class MockResponse:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict[str, Any]:
                return {
                    "urls": [{"packagetype": "sdist", "url": "https://example.com/fake_package.tar.gz"}]
                }

            @property
            def content(self) -> bytes:
                # Return a valid tar.gz file content
                return create_mock_tar_gz()

        return MockResponse()

    monkeypatch.setattr("requests.get", mock_get)

    # Test the download and extraction
    with tempfile.TemporaryDirectory() as temp_dir:
        result_dir = download_package("fake_package", temp_dir)
        assert os.path.exists(result_dir)

def test_extract_files(monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_download_package(package_name: str, temp_dir: str) -> str:
        os.makedirs(f"{temp_dir}/fake_package_dir", exist_ok=True)
        with open(f"{temp_dir}/fake_package_dir/test.py", "w") as f:
            f.write("# Example Python file")
        return f"{temp_dir}/fake_package_dir"

    monkeypatch.setattr("analyzer.package_analyzer.download_package", mock_download_package)

    # Test extracting files
    with tempfile.TemporaryDirectory() as temp_dir:
        files = extract_files("fake_package", temp_dir)
        assert len(files) > 0  # Expect at least one file to be extracted

def test_find_stub_package_success() -> None:
    # Mock a successful response for an existing stub package
    with patch("requests.get") as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        package_name = "example_package"
        stub_url = find_stub_package(package_name)
        expected_url = f"https://pypi.org/project/{package_name}-stubs/"

        assert stub_url == expected_url
        mock_get.assert_called_once_with(f"https://pypi.org/pypi/{package_name}-stubs/json")

def test_find_stub_package_not_found() -> None:
    # Mock a 404 response for a non-existing stub package
    with patch("requests.get") as mock_get:
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        package_name = "nonexistent_package"
        stub_url = find_stub_package(package_name)

        assert stub_url is None
        mock_get.assert_called_once_with(f"https://pypi.org/pypi/{package_name}-stubs/json")
