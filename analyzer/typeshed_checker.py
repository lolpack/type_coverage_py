import os
from typing import List

# Get the absolute path to the project root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))

# Construct the path to the typeshed directory
TYPESHED_DIR = os.path.join(PROJECT_ROOT, "typeshed")

def check_typeshed(package_name: str) -> bool:
    """Checks if the package has stubs available in the typeshed repository."""
    
    # Check in the third-party stubs directory
    stubs_path = os.path.join(TYPESHED_DIR, 'stubs', package_name)
    
    return os.path.exists(stubs_path)

def find_stub_files(package_name: str) -> List[str]:
    """Finds the .pyi stub files for the given package in the typeshed directory."""
    typeshed_path = os.path.join(TYPESHED_DIR, 'stubs', package_name)
    stub_files: List[str] = []  # Explicitly type the list as List[str]
    for root, _, files in os.walk(typeshed_path):
        for file in files:
            if file.endswith('.pyi'):
                stub_files.append(os.path.join(root, file))
    return stub_files

def merge_files_with_stubs(package_files: List[str], typeshed_stubs: List[str]) -> List[str]:
    """Merge package files with typeshed stubs, preferring .pyi files from the package itself."""
    merged_files: List[str] = []  # Explicitly type the list as List[str]
    typeshed_stub_dict = {os.path.basename(stub): stub for stub in typeshed_stubs}

    for file in package_files:
        base_name = os.path.basename(file)
        if base_name.endswith('.pyi'):
            # If a .pyi file from the package exists, prefer it over typeshed
            if base_name in typeshed_stub_dict:
                typeshed_stub_dict.pop(base_name)
            merged_files.append(file)
        elif base_name.endswith('.py'):
            # Include all .py files from the package
            merged_files.append(file)

    # Add remaining typeshed stubs (those that were not overridden by package stubs)
    merged_files.extend(typeshed_stub_dict.values())
    
    return merged_files