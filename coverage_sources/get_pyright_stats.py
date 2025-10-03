import json
import shutil
from pathlib import Path
import os
import subprocess
from typing import Any, Dict, Union
from fnmatch import fnmatch

EXCLUDE_LIKE: Dict[str, list[str]] = {
    'numpy': ['*.tests.*'],
    'pandas': [
        # pandas distributes (untyped) tests with the package
        '*.tests.*',
        # pandas.core is technically private, and anything considered public
        # is re-exported in other places. For example, `DataFrameGroupBy` is
        # re-exported in `pandas.api.typing`. The re-exports are available
        # under `'alternateNames'`, which we consider when excluding symbols.
        'pandas.core.*',
        # Not considered public
        'pandas.compat.*'
    ],
}


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
            activate_cmd = f". {venv_name}/bin/activate && python3.12 -m pip install {package}"
        else:
            activate_cmd = f"{venv_name}\\Scripts\\activate && python -m pip install {package}"
        subprocess.run(activate_cmd, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error installing package: {e}")

def activate_and_uninstall_package(venv_name: str, package: str) -> None:
    try:
        if os.name == "posix":
            activate_cmd = f". {venv_name}/bin/activate && python3.12 -m pip uninstall {package} -y"
        else:
            activate_cmd = f"{venv_name}\\Scripts\\activate && python -m pip uninstall {package} -y"
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
    # NOTE: we use `--ignoreexternal` to ignore partially unknown symbols imported from
    # other libraries (e.g. if pandas annotates a variable using an incomplete NumPy Dtype, then
    # we don't want that to count against pandas' completeness metric).
    # https://github.com/microsoft/pyright/discussions/9911
    if os.name == "posix":
        run_pyright_cmd = f". {venv_name}/bin/activate && pyright --ignoreexternal --verifytypes {package} --outputjson > {output_file}"
    else:
        run_pyright_cmd = f"{venv_name}\\Scripts\\activate && pyright --ignoreexternal --verifytypes {package} --outputjson > {output_file}"

    try:
        subprocess.run(run_pyright_cmd, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running pyright: {e}")
        print(f"Command: {run_pyright_cmd}")
        print(f"Return code: {e.returncode}")
        print(f"Output: {e.output}")


def parse_output_json(output_file: str, exclude_like: list[str] | None = None) -> Dict[str, Union[int, float]]:
    try:
        with open(output_file, "r") as f:
            output_data = json.load(f)
            pyright_data: Dict[str, Union[int, float]] = {}

            symbol_count = output_data["typeCompleteness"]["exportedSymbolCounts"]
            if exclude_like is None:
                coverage: float = output_data["typeCompleteness"]["completenessScore"] * 100.0
            else:
                matched_symbols = [
                    x for x in output_data["typeCompleteness"]["symbols"]
                    if x['isExported']
                    # Keep symbols where there's any name which doesn't match any excluded patterns.
                    and any(
                        all(not fnmatch(name, pattern) for pattern in exclude_like)
                        for name in [x['name'], *x.get('alternateNames', [])]
                    )
                ]
                coverage = (
                    sum(x["isTypeKnown"] for x in matched_symbols) / len(matched_symbols) * 100
                )
            
            pyright_data = symbol_count
            pyright_data["coverage"] = coverage
            
            return pyright_data

    except FileNotFoundError:
        print(f"Error: File '{output_file}' not found.")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return {}

def inline_pandas_stubs(venv_name: str) -> None:
    # pandas publishes a separate stubs package called `pandas-stubs`.
    # To get PyRight to accurately report on pandas' coverage using
    # the stubs, we need to inline the stub files manually and make
    # sure `pandas-stubs` is uninstalled.
    activate_and_install_package(venv_name, 'pandas-stubs')
    if os.name == "posix":
        cmd = f". {venv_name}/bin/activate && python3.12 -c 'import pandas; print(pandas.__file__)'"
    else:
        cmd = f"{venv_name}\\Scripts\\activate && python3.12 -c 'import pandas; print(pandas.__file__)'"
    pandas_file = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True).stdout
    pandas_dir = Path(pandas_file).parent
    pandas_stubs_dir = pandas_dir.parent / 'pandas-stubs'
    for item in pandas_stubs_dir.iterdir():
        s = pandas_stubs_dir / item.name
        d = pandas_dir / item.name
        if s.is_dir():
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)
    activate_and_uninstall_package(venv_name, 'pandas-stubs')


def main(packages: list[dict[str, Any]]) -> Dict[str, Any]:
    output_dir = ".pyright_output"
    create_output_directory(output_dir)

    stats: Dict[str, Any] = {}

    for package_data in packages:
        package = package_data["package_name"]
        has_py_typed = package_data["has_py_typed"]

        venv_name = f".pyright_env_{package}"
        create_virtual_environment(venv_name)
        activate_and_install_package(venv_name, package)
        if package == 'pandas':
            inline_pandas_stubs(venv_name)

        # Pyright requires a py.typed file to be present to calculate type coverage
        if not has_py_typed:
            print(f"Package {package} does not have a py.typed file. Creating one. {venv_name}/lib/python3.12/site-packages/{package}/py.typed")
            py_typed_path = f"{venv_name}/lib/python3.12/site-packages/{package}/py.typed"
            create_py_typed_file(py_typed_path)

        output_file = f"{output_dir}/{package}_output.json"
        run_pyright(venv_name, package, output_file)
        pyright_data = parse_output_json(output_file, EXCLUDE_LIKE.get(package, None))

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
