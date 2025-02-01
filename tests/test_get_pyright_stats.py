import os
import json
from unittest.mock import patch, mock_open
from coverage_sources.get_pyright_stats import (
    create_output_directory,
    create_virtual_environment,
    activate_and_install_package,
    create_py_typed_file,
    run_pyright,
    parse_output_json,
    main
)


def test_create_output_directory(tmp_path):
    output_dir = tmp_path / ".pyright_output"
    create_output_directory(str(output_dir))
    assert os.path.exists(output_dir)


def test_create_virtual_environment():
    venv_name = ".test_env"
    with patch("subprocess.run") as mock_run:
        create_virtual_environment(venv_name)
        mock_run.assert_called_with(f"python3.12 -m venv {venv_name}", shell=True, check=True)


def test_activate_and_install_package():
    venv_name = ".test_env"
    package = "test_package"
    activate_cmd = (
        f"source {venv_name}/bin/activate && python3.12 -m pip install {package}"
        if os.name == "posix"
        else f"{venv_name}\\Scripts\\activate && python3.12 -m pip install {package}"
    )
    with patch("subprocess.run") as mock_run:
        activate_and_install_package(venv_name, package)
        mock_run.assert_called_with(activate_cmd, shell=True, check=True)


def test_create_py_typed_file(tmp_path):
    py_typed_path = tmp_path / "lib/python3.12/site-packages/test_package/py.typed"
    create_py_typed_file(str(py_typed_path))
    assert os.path.exists(py_typed_path)


def test_run_pyright():
    venv_name = ".test_env"
    package = "test_package"
    output_file = ".pyright_output/test_package_output.json"
    run_pyright_cmd = f"source {venv_name}/bin/activate && pyright --verifytypes {package} --outputjson > {output_file}"

    with patch("subprocess.run") as mock_run:
        run_pyright(venv_name, package, output_file)
        mock_run.assert_called_with(run_pyright_cmd, shell=True, check=True)


def test_parse_output_json():
    output_file = "test_output.json"
    mock_data = {
        "typeCompleteness": {
            "exportedSymbolCounts": {"total": 10, "withAnnotations": 5},
            "completenessScore": 0.5
        }
    }
    with patch("builtins.open", mock_open(read_data=json.dumps(mock_data))):
        result = parse_output_json(output_file)
        assert result["total"] == 10
        assert result["withAnnotations"] == 5
        assert result["coverage"] == 50.0


def test_main(tmp_path):
    packages = ["test_package"]
    output_dir = tmp_path / ".pyright_output"
    venv_name = tmp_path / ".pyright_env_test_package"
    py_typed_path = venv_name / "lib/python3.12/site-packages/test_package/py.typed"
    output_file = output_dir / "test_package_output.json"

    # Compute the relative paths from tmp_path.
    expected_venv = os.path.normpath(os.path.relpath(str(venv_name), start=str(tmp_path)))
    expected_output_file = os.path.normpath(os.path.relpath(str(output_file), start=str(tmp_path)))
    expected_output_file = expected_output_file.replace(os.sep, '/')  # Convert to forward slashes

    # For py_typed_path, convert the normalized path to use forward slashes.
    expected_py_typed = os.path.normpath(os.path.relpath(str(py_typed_path), start=str(tmp_path)))
    expected_py_typed = expected_py_typed.replace(os.sep, '/')

    with patch("coverage_sources.get_pyright_stats.create_virtual_environment") as mock_create_venv, \
         patch("coverage_sources.get_pyright_stats.activate_and_install_package") as mock_activate_install, \
         patch("coverage_sources.get_pyright_stats.create_py_typed_file") as mock_create_py_typed, \
         patch("coverage_sources.get_pyright_stats.run_pyright") as mock_run_pyright, \
         patch("coverage_sources.get_pyright_stats.parse_output_json", return_value={"total": 10, "withAnnotations": 5, "coverage": 50.0}) as mock_parse_json, \
         patch("subprocess.run") as mock_subprocess_run:

        stats = main(packages)
        assert stats["test_package"]["total"] == 10
        assert stats["test_package"]["withAnnotations"] == 5
        assert stats["test_package"]["coverage"] == 50.0

        # Expect the relative path as ".pyright_env_test_package" for create_virtual_environment.
        mock_create_venv.assert_called_once_with(".pyright_env_test_package")
        mock_activate_install.assert_called_once_with(expected_venv, "test_package")
        mock_create_py_typed.assert_called_once_with(expected_py_typed)
        mock_run_pyright.assert_called_once_with(expected_venv, "test_package", expected_output_file)
        mock_parse_json.assert_called_once_with(expected_output_file)
        mock_subprocess_run.assert_called()
