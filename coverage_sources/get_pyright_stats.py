import json
import os
import subprocess
from typing import Any, Dict


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
        activate_cmd = (
            f"source {venv_name}/bin/activate && python3.12 -m pip install {package}"
            if os.name == "posix"
            else f"{venv_name}\\Scripts\\activate && python3.12 -m pip install {package}"
        )
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
    run_pyright_cmd = f"source {venv_name}/bin/activate && pyright --verifytypes {package} --outputjson > {output_file}"

    try:
        subprocess.run(run_pyright_cmd, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running pyright: {e}")
        print(f"Command: {run_pyright_cmd}")
        print(f"Return code: {e.returncode}")
        print(f"Output: {e.output}")


def parse_output_json(output_file: str) -> Dict[str, int]:
    try:
        with open(output_file, "r") as f:
            output_data = json.load(f)
            return output_data["typeCompleteness"]["exportedSymbolCounts"]
    except FileNotFoundError:
        print(f"Error: File '{output_file}' not found.")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return {}


def calculate_pyright_coverage(exported_symbol_counts: Dict[str, int]) -> float:
    total_symbols = sum(exported_symbol_counts.values())
    if total_symbols == 0:
        return 0.0
    covered_symbols = (
        exported_symbol_counts["withKnownType"]
        + exported_symbol_counts["withAmbiguousType"]
    )
    return covered_symbols / total_symbols * 100.0


def main(packages: list[str]) -> Dict[str, Any]:
    output_dir = ".pyright_output"
    create_output_directory(output_dir)

    stats: Dict[str, Any] = {}

    for package in packages:
        venv_name = f".pyright_env_{package}"
        create_virtual_environment(venv_name)
        activate_and_install_package(venv_name, package)
        py_typed_path = f"{venv_name}/lib/python3.12/site-packages/{package}/py.typed"
        create_py_typed_file(py_typed_path)
        output_file = f"{output_dir}/{package}_output.json"
        run_pyright(venv_name, package, output_file)
        exported_symbol_counts = parse_output_json(output_file)

        stats[package] = exported_symbol_counts
        stats[package]["coverage"] = calculate_pyright_coverage(exported_symbol_counts)

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
