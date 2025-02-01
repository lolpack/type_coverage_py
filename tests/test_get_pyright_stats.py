import os
import json
from pathlib import Path
from unittest.mock import patch, mock_open

from coverage_sources.get_pyright_stats import (
    create_output_directory,
    create_virtual_environment,
    activate_and_install_package,
    create_py_typed_file,
    run_pyright,
    parse_output_json,
    main,
)

def test_create_output_directory(tmp_path: Path) -> None:
    output_dir: Path = tmp_path / ".pyright_output"
    create_output_directory(str(output_dir))
    assert os.path.exists(output_dir)


def test_create_virtual_environment() -> None:
    venv_name: str = ".test_env"
    with patch("subprocess.run") as mock_run:
        create_virtual_environment(venv_name)
        mock_run.assert_called_with(
            f"python3.12 -m venv {venv_name}", shell=True, check=True
        )


def test_activate_and_install_package() -> None:
    venv_name: str = ".test_env"
    package: str = "test_package"
    if os.name == "posix":
        activate_cmd: str = f"source {venv_name}/bin/activate && python3.12 -m pip install {package}"
    else:
        activate_cmd = f"{venv_name}\\Scripts\\activate && python3.12 -m pip install {package}"
    with patch("subprocess.run") as mock_run:
        activate_and_install_package(venv_name, package)
        mock_run.assert_called_with(activate_cmd, shell=True, check=True)


def test_create_py_typed_file(tmp_path: Path) -> None:
    py_typed_path: Path = tmp_path / "lib/python3.12/site-packages/test_package/py.typed"
    create_py_typed_file(str(py_typed_path))
    assert os.path.exists(py_typed_path)


def test_run_pyright() -> None:
    venv_name: str = ".test_env"
    package: str = "test_package"
    output_file: str = ".pyright_output/test_package_output.json"
    run_pyright_cmd: str = (
        f"source {venv_name}/bin/activate && pyright --verifytypes {package} --outputjson > {output_file}"
    )
    with patch("subprocess.run") as mock_run:
        run_pyright(venv_name, package, output_file)
        mock_run.assert_called_with(run_pyright_cmd, shell=True, check=True)


def test_parse_output_json() -> None:
    output_file: str = "test_output.json"
    mock_data = {
        "typeCompleteness": {
            "exportedSymbolCounts": {"total": 10, "withAnnotations": 5},
            "completenessScore": 0.5,
        }
    }
    with patch("builtins.open", mock_open(read_data=json.dumps(mock_data))):
        result = parse_output_json(output_file)
        assert result["total"] == 10
        assert result["withAnnotations"] == 5
        assert result["coverage"] == 50.0


def test_main(tmp_path: Path) -> None:
    packages: list[str] = ["test_package"]
    output_dir: Path = tmp_path / ".pyright_output"
    venv_name: Path = tmp_path / ".pyright_env_test_package"
    py_typed_path: Path = venv_name / "lib/python3.12/site-packages/test_package/py.typed"
    output_file: Path = output_dir / "test_package_output.json"

    # Compute the relative paths from tmp_path.
    expected_venv: str = os.path.normpath(os.path.relpath(str(venv_name), start=str(tmp_path)))
    expected_output_file: str = os.path.normpath(os.path.relpath(str(output_file), start=str(tmp_path)))
    # Convert to forward slashes to match what is produced in the code under test.
    expected_output_file = expected_output_file.replace(os.sep, "/")

    expected_py_typed: str = os.path.normpath(os.path.relpath(str(py_typed_path), start=str(tmp_path)))
    expected_py_typed = expected_py_typed.replace(os.sep, "/")

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
