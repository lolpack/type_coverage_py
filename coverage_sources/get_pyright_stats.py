import json
import os
import subprocess
from typing import Any, Dict, Union


def create_output_directory(output_dir: str) -> None:
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)


def create_virtual_environment(venv_name: str) -> None:
    try:
        subprocess.run(f"python3.12 -m venv {venv_name}", shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error creating virtual environment: {e}")


def activate_and_install_package(venv_name: str, package: str) -> None:
    try:
        if os.name == "posix":
            activate_cmd = f"source {venv_name}/bin/activate && python3.12 -m pip install {package}"
        else:
            activate_cmd = f"{venv_name}\\Scripts\\activate && python -m pip install {package}"
        subprocess.run(activate_cmd, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error installing package: {e}")


def create_py_typed_file(py_typed_path: str) -> None:
    if not os.path.exists(os.path.dirname(py_typed_path)):
        os.makedirs(os.path.dirname(py_typed_path))
    if not os.path.exists(py_typed_path):
        with open(py_typed_path, "w"):
            pass


def run_pyright(venv_name: str, package: str, output_file: str) -> None:
    if os.name == "posix":
        run_pyright_cmd = f"source {venv_name}/bin/activate && pyright --verifytypes {package} --outputjson > {output_file}"
    else:
        run_pyright_cmd = f"{venv_name}\\Scripts\\activate && pyright --verifytypes {package} --outputjson > {output_file}"

    try:
        subprocess.run(run_pyright_cmd, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running pyright: {e}")
        print(f"Command: {run_pyright_cmd}")
        print(f"Return code: {e.returncode}")
        print(f"Output: {e.output}")


def parse_output_json(output_file: str) -> Dict[str, Union[int, float]]:
    try:
        with open(output_file, "r") as f:
            output_data = json.load(f)
            pyright_data: Dict[str, Union[int, float]] = {}
            symbol_count = output_data["typeCompleteness"]["exportedSymbolCounts"]
            coverage: float = output_data["typeCompleteness"]["completenessScore"] * 100.0
            
            pyright_data = symbol_count
            pyright_data["coverage"] = coverage
            
            return pyright_data

    except FileNotFoundError:
        print(f"Error: File '{output_file}' not found.")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return {}


def main(packages: list[str]) -> Dict[str, Any]:
    output_dir = ".pyright_output"
    create_output_directory(output_dir)

    stats: Dict[str, Any] = {}

    for package in packages:
        venv_name = f".pyright_env_{package}"
        create_virtual_environment(venv_name)
        activate_and_install_package(venv_name, package)
        
        # Pyright requires a py.typed file to be present to calculate type coverage
        py_typed_path = f"{venv_name}/lib/python3.12/site-packages/{package}/py.typed"
        create_py_typed_file(py_typed_path)
        
        output_file = f"{output_dir}/{package}_output.json"
        run_pyright(venv_name, package, output_file)
        pyright_data = parse_output_json(output_file)

        stats[package] = pyright_data

        print(f"Package: {package}")
        print(f"Exported Pyright Symbol Counts: {stats[package]}")
        print()

        cleanup_cmd = (
            f"rm -rf {venv_name}"
            if os.name == "posix"
            else f"deactivate && rmdir /s /q {venv_name}"
        )
        subprocess.run(cleanup_cmd, shell=True, check=True)

    return stats


if __name__ == "__main__":
    stats = main([])
    print("Package stats:", stats)
    print()
