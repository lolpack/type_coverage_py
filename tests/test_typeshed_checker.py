import os
import pytest
from analyzer.typeshed_checker import (
    check_typeshed,
    find_stub_files,
    merge_files_with_stubs
)
from pathlib import Path


@pytest.fixture
def mock_typeshed(tmp_path: Path) -> str:
    """Fixture to set up a mock typeshed directory."""
    stubs_dir = tmp_path / "typeshed" / "stubs"
    package_dir = stubs_dir / "mock_package"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "__init__.pyi").write_text("# mock init file")
    (package_dir / "module.pyi").write_text("# mock module file")
    return str(tmp_path)


def test_check_typeshed(mock_typeshed: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test check_typeshed function."""
    # Ensure the mock_typeshed includes the 'typeshed' directory
    corrected_typeshed_dir = os.path.join(mock_typeshed, 'typeshed')

    monkeypatch.setattr(
        "analyzer.typeshed_checker.TYPESHED_DIR", corrected_typeshed_dir)

    stubs_path = os.path.join(corrected_typeshed_dir, 'stubs', 'mock_package')
    print(f"Checking for stubs at: {stubs_path}")
    print(f"Directory exists: {os.path.exists(stubs_path)}")

    # Debug inside check_typeshed
    result = check_typeshed("mock_package")
    print(f"check_typeshed result for 'mock_package': {result}")

    assert result is True


def test_find_stub_files(mock_typeshed: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test find_stub_files function."""
    # Ensure the mock_typeshed includes the 'typeshed' directory
    corrected_typeshed_dir = os.path.join(mock_typeshed, 'typeshed')

    monkeypatch.setattr(
        "analyzer.typeshed_checker.TYPESHED_DIR", corrected_typeshed_dir)

    stubs = find_stub_files("mock_package")
    print(f"Found stubs: {stubs}")

    # Ensure that we are looking in the correct directory
    print(f"Typeshed path: {os.path.join(
        corrected_typeshed_dir, 'stubs/mock_package')}")

    assert len(stubs) == 2
    assert os.path.join(corrected_typeshed_dir,
                        "stubs/mock_package/__init__.pyi") in stubs
    assert os.path.join(corrected_typeshed_dir,
                        "stubs/mock_package/module.pyi") in stubs


def test_merge_files_with_stubs() -> None:
    """Test merge_files_with_stubs function."""
    package_files = [
        "/path/to/package/__init__.py",
        "/path/to/package/module.py",
        "/path/to/package/module.pyi"
    ]
    typeshed_stubs = [
        "/mocked/path/to/typeshed/stubs/mock_package/module.pyi",
        "/mocked/path/to/typeshed/stubs/mock_package/another_module.pyi"
    ]
    merged_files = merge_files_with_stubs(package_files, typeshed_stubs)
    print(f"Merged files: {merged_files}")

    # Ensure the .pyi from the package overrides the typeshed
    assert "/path/to/package/module.pyi" in merged_files
    assert "/mocked/path/to/typeshed/stubs/mock_package/another_module.pyi" in merged_files

    # The .py file should be included if there's no corresponding .pyi in the package itself
    assert "/path/to/package/module.py" in merged_files


def test_integration_with_coverage_calculation(monkeypatch: pytest.MonkeyPatch, mock_typeshed: str, tmp_path: Path) -> None:
    """Test full integration with coverage calculation."""
    from analyzer.coverage_calculator import calculate_overall_coverage

    # Create mock package files
    package_dir = tmp_path / "package"
    package_dir.mkdir()

    init_file = package_dir / "__init__.py"
    init_file.write_text("def function(): pass")

    module_file = package_dir / "module.py"
    module_file.write_text("def function(): pass")

    module_pyi = package_dir / "module.pyi"
    module_pyi.write_text("def function() -> int: ...")

    package_files = [str(init_file), str(module_file), str(module_pyi)]

    monkeypatch.setattr(
        "analyzer.typeshed_checker.TYPESHED_DIR", mock_typeshed)
    typestub_files = find_stub_files("mock_package")

    # Merge files with type stubs
    merged_files = merge_files_with_stubs(package_files, typestub_files)

    # Perform coverage calculation
    coverage_data_with_stubs = calculate_overall_coverage(merged_files)

    # Check that the coverage data is calculated as expected
    assert "parameter_coverage" in coverage_data_with_stubs
    assert "return_type_coverage" in coverage_data_with_stubs
    print(f"Coverage data: {coverage_data_with_stubs}")
