import pytest
from analyzer.coverage_calculator import (
    calculate_parameter_coverage,
    calculate_return_type_coverage,
    calculate_overall_coverage,
)


def test_calculate_parameter_coverage():
    # Test with a basic example
    # Example file with annotated parameters
    files = ["tests/test_files/annotated_function.py"]
    total_params, annotated_params, skipped_files = calculate_parameter_coverage(
        files)
    assert total_params == 2
    assert annotated_params == 2
    assert skipped_files == 0

    # Test with a file that has no annotations
    files = ["tests/test_files/non_annotated_function.py"]
    total_params, annotated_params, skipped_files = calculate_parameter_coverage(
        files)
    assert total_params == 2
    assert annotated_params == 0
    assert skipped_files == 0


def test_calculate_return_type_coverage():
    # Test with a basic example
    # Example file with return type annotations
    files = ["tests/test_files/annotated_function.py"]
    total_returns, annotated_returns, skipped_files = calculate_return_type_coverage(
        files)
    assert total_returns == 1
    assert annotated_returns == 1
    assert skipped_files == 0

    # Test with a file that has no annotations
    files = ["tests/test_files/non_annotated_function.py"]
    total_returns, annotated_returns, skipped_files = calculate_return_type_coverage(
        files)
    assert total_returns == 1
    assert annotated_returns == 0
    assert skipped_files == 0


def test_calculate_overall_coverage():
    # Test with a mix of files
    files = ["tests/test_files/annotated_function.py",
             "tests/test_files/non_annotated_function.py"]
    coverage_data = calculate_overall_coverage(files)
    # Assuming 1 file with 100% and 1 with 0%
    assert coverage_data["parameter_coverage"] == 50.0
    assert coverage_data["return_type_coverage"] == 50.0
    assert coverage_data["skipped_files"] == 0


def test_calculate_overall_coverage_with_stubs():
    # Test with both .py and .pyi files to verify stub coverage
    files = ["tests/test_files/embedded_pyi.py",
             "tests/test_files/embedded_pyi.pyi"]
    coverage_data = calculate_overall_coverage(files)

    # .pyi provides full annotations
    assert coverage_data["parameter_coverage"] == 100.0
    assert coverage_data["return_type_coverage"] == 100.0
    assert coverage_data["skipped_files"] == 0


def test_fully_annotated_with_stubs():
    files = ["tests/test_files/fully_annotated.py"]
    coverage_data = calculate_overall_coverage(files)

    assert coverage_data["parameter_coverage"] == 100.0
    assert coverage_data["return_type_coverage"] == 100.0
    assert coverage_data["skipped_files"] == 0


def test_partially_annotated_with_stubs():
    files = ["tests/test_files/partially_annotated.py"]
    coverage_data = calculate_overall_coverage(files)

    assert coverage_data["parameter_coverage"] == pytest.approx(  # type: ignore[reportUnknownMemberType]
        33.33, rel=1e-2)
    assert coverage_data["return_type_coverage"] == pytest.approx(  # type: ignore[reportUnknownMemberType]
        66.67, rel=1e-2)
    assert coverage_data["skipped_files"] == 0


def test_complex_types_with_stubs():
    files = ["tests/test_files/complex_types.py"]
    coverage_data = calculate_overall_coverage(files)

    assert coverage_data["parameter_coverage"] == 100.0
    assert coverage_data["return_type_coverage"] == 100.0
    assert coverage_data["skipped_files"] == 0


def test_class_methods_with_stubs():
    files = ["tests/test_files/class_methods.py"]
    coverage_data = calculate_overall_coverage(files)

    assert coverage_data["parameter_coverage"] == 100.0
    assert coverage_data["return_type_coverage"] == 100.0
    assert coverage_data["skipped_files"] == 0


def test_skip_init_method_in_class():
    # A file containing a class with an __init__ method
    files = ["tests/test_files/class_with_init.py"]

    # Parameter coverage should ignore the __init__ method
    param_total, params_annotated, skipped_files = calculate_parameter_coverage(
        files)
    assert params_annotated == 2  # Methods other than __init__ fully annotated
    assert param_total == 2
    assert skipped_files == 0

    # Return type coverage should also ignore the __init__ method
    return_total, return_annotated, _ = calculate_return_type_coverage(files)
    assert return_total == 1  # Other methods are considered
    assert return_annotated == 1
    assert skipped_files == 0
