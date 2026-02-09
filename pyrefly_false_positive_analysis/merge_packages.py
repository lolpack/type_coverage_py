#!/usr/bin/env python3
"""Merge and deduplicate package lists, preserving all metadata."""

import json
from pathlib import Path

# Non-Python projects and curated lists to exclude
EXCLUDE_NAMES = {
    "free-programming-books",
    "public-apis",
    "awesome-python",
    "HelloGitHub",
    "awesome-llm-apps",
    "system-design-primer",  # Documentation/learning resource
}

def main():
    # Load benchmark_packages.json
    benchmark_file = Path(__file__).parent.parent / "type_checker_benchmark" / "benchmark_packages.json"
    top25_file = Path(__file__).parent.parent / "type_checker_benchmark" / "top25_missing_packages.json"

    packages = {}

    # Load benchmark packages (preserve all data)
    if benchmark_file.exists():
        with open(benchmark_file) as f:
            data = json.load(f)
            for pkg in data.get("packages", []):
                name = pkg["name"]
                if name not in EXCLUDE_NAMES:
                    packages[name] = pkg  # Keep all fields

    # Load top25 packages (preserve all data)
    if top25_file.exists():
        with open(top25_file) as f:
            data = json.load(f)
            for pkg in data.get("packages", []):
                name = pkg["name"]
                if name not in EXCLUDE_NAMES and name not in packages:
                    packages[name] = pkg  # Keep all fields

    # Sort by name
    sorted_packages = sorted(packages.values(), key=lambda x: x["name"].lower())

    output = {
        "packages": sorted_packages,
        "description": "Python packages for type checker analysis",
        "count": len(sorted_packages),
        "type_checkers": ["pyright", "pyrefly", "mypy", "ty", "zuban"],
    }

    output_file = Path(__file__).parent / "packages.json"
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Wrote {len(sorted_packages)} packages to {output_file}")


if __name__ == "__main__":
    main()
