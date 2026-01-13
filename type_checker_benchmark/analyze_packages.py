#!/usr/bin/env python3
"""Analyze packages to detect which type checkers they use.

This script:
1. Clones each package from the benchmark list
2. Searches for type checker configuration in various files
3. Outputs a JSON file with detection results
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add parent directory to path
import sys
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from type_checker_benchmark.daily_runner import resolve_github_url

# Type checkers to detect
TYPE_CHECKERS = ["pyright", "pyrefly", "mypy", "ty", "zuban"]


def load_existing_urls() -> dict[str, str]:
    """Load existing package URLs from benchmark_packages.json.

    Returns:
        Dictionary mapping package names to GitHub URLs.
    """
    json_file = ROOT_DIR / "type_checker_benchmark" / "benchmark_packages.json"
    if not json_file.exists():
        return {}

    try:
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
        return {
            pkg["name"]: pkg["github_url"]
            for pkg in data.get("packages", [])
            if pkg.get("github_url")
        }
    except (json.JSONDecodeError, KeyError):
        return {}


@dataclass
class TypeCheckerDetection:
    """Detection result for a single type checker."""
    detected: bool = False
    locations: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


@dataclass
class PackageAnalysis:
    """Analysis result for a package."""
    name: str
    github_url: str
    type_checkers: dict[str, TypeCheckerDetection] = field(default_factory=dict)
    has_py_typed: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "github_url": self.github_url,
            "has_py_typed": self.has_py_typed,
            "error": self.error,
            "type_checkers": {
                name: {
                    "detected": tc.detected,
                    "locations": tc.locations,
                    "evidence": tc.evidence[:3],  # Limit evidence to 3 items
                }
                for name, tc in self.type_checkers.items()
            },
        }


def clone_repo(github_url: str, target_dir: Path, timeout: int = 120) -> bool:
    """Clone a repository.

    Args:
        github_url: GitHub URL to clone.
        target_dir: Directory to clone into.
        timeout: Timeout in seconds.

    Returns:
        True if successful, False otherwise.
    """
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", github_url, str(target_dir)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def search_file_for_checker(
    file_path: Path,
    checker: str,
) -> tuple[bool, list[str]]:
    """Search a file for type checker references.

    Args:
        file_path: Path to the file to search.
        checker: Type checker name to search for.

    Returns:
        Tuple of (found, evidence_lines).
    """
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False, []

    evidence = []
    found = False

    # Patterns to search for each checker
    patterns = {
        "pyright": [
            r"\bpyright\b",
            r"pyrightconfig\.json",
            r"\[tool\.pyright\]",
            r"typeCheckingMode",
        ],
        "pyrefly": [
            r"\bpyrefly\b",
            r"\.pyrefly",
            r"\[tool\.pyrefly\]",
        ],
        "mypy": [
            r"\bmypy\b",
            r"mypy\.ini",
            r"\[mypy\]",
            r"\[tool\.mypy\]",
            r"# type: ignore",
            r"# mypy:",
        ],
        "ty": [
            r"\bty\s+check\b",
            r"\[tool\.ty\]",
            # Be careful not to match random "ty" occurrences
        ],
        "zuban": [
            r"\bzuban\b",
            r"\[tool\.zuban\]",
        ],
    }

    for pattern in patterns.get(checker, []):
        matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            # Get the line containing the match
            start = content.rfind("\n", 0, match.start()) + 1
            end = content.find("\n", match.end())
            if end == -1:
                end = len(content)
            line = content[start:end].strip()

            # Filter out false positives
            if checker == "ty" and not re.search(r"\bty\s+(check|version)", line, re.IGNORECASE):
                continue

            if line and line not in evidence:
                evidence.append(line[:200])  # Limit line length
                found = True

    return found, evidence


def analyze_github_workflows(repo_path: Path, checker: str) -> tuple[bool, list[str]]:
    """Analyze GitHub workflow files for type checker usage.

    Args:
        repo_path: Path to the repository.
        checker: Type checker name to search for.

    Returns:
        Tuple of (found, evidence_lines).
    """
    workflows_dir = repo_path / ".github" / "workflows"
    if not workflows_dir.exists():
        return False, []

    found = False
    evidence = []

    for yml_file in workflows_dir.glob("*.yml"):
        file_found, file_evidence = search_file_for_checker(yml_file, checker)
        if file_found:
            found = True
            evidence.extend([f"{yml_file.name}: {e}" for e in file_evidence])

    for yaml_file in workflows_dir.glob("*.yaml"):
        file_found, file_evidence = search_file_for_checker(yaml_file, checker)
        if file_found:
            found = True
            evidence.extend([f"{yaml_file.name}: {e}" for e in file_evidence])

    return found, evidence


def analyze_pyproject_toml(repo_path: Path, checker: str) -> tuple[bool, list[str]]:
    """Analyze pyproject.toml for type checker configuration.

    Args:
        repo_path: Path to the repository.
        checker: Type checker name to search for.

    Returns:
        Tuple of (found, evidence_lines).
    """
    pyproject = repo_path / "pyproject.toml"
    if not pyproject.exists():
        return False, []

    return search_file_for_checker(pyproject, checker)


def analyze_requirements(repo_path: Path, checker: str) -> tuple[bool, list[str]]:
    """Analyze requirements files for type checker dependencies.

    Args:
        repo_path: Path to the repository.
        checker: Type checker name to search for.

    Returns:
        Tuple of (found, evidence_lines).
    """
    found = False
    evidence = []

    # Check various requirements files
    req_patterns = [
        "requirements*.txt",
        "dev-requirements*.txt",
        "test-requirements*.txt",
        "requirements/*.txt",
    ]

    for pattern in req_patterns:
        for req_file in repo_path.glob(pattern):
            file_found, file_evidence = search_file_for_checker(req_file, checker)
            if file_found:
                found = True
                evidence.extend([f"{req_file.name}: {e}" for e in file_evidence])

    return found, evidence


def analyze_setup_files(repo_path: Path, checker: str) -> tuple[bool, list[str]]:
    """Analyze setup.py and setup.cfg for type checker configuration.

    Args:
        repo_path: Path to the repository.
        checker: Type checker name to search for.

    Returns:
        Tuple of (found, evidence_lines).
    """
    found = False
    evidence = []

    for setup_file in ["setup.py", "setup.cfg"]:
        file_path = repo_path / setup_file
        if file_path.exists():
            file_found, file_evidence = search_file_for_checker(file_path, checker)
            if file_found:
                found = True
                evidence.extend([f"{setup_file}: {e}" for e in file_evidence])

    return found, evidence


def analyze_config_files(repo_path: Path, checker: str) -> tuple[bool, list[str]]:
    """Analyze type checker config files.

    Args:
        repo_path: Path to the repository.
        checker: Type checker name to search for.

    Returns:
        Tuple of (found, evidence_lines).
    """
    config_files = {
        "pyright": ["pyrightconfig.json"],
        "mypy": ["mypy.ini", ".mypy.ini"],
        "pyrefly": [".pyrefly", "pyrefly.toml"],
        "ty": [],
        "zuban": [],
    }

    found = False
    evidence = []

    for config_file in config_files.get(checker, []):
        file_path = repo_path / config_file
        if file_path.exists():
            found = True
            evidence.append(f"Config file exists: {config_file}")

    return found, evidence


def check_py_typed(repo_path: Path) -> bool:
    """Check if the package has a py.typed marker.

    Args:
        repo_path: Path to the repository.

    Returns:
        True if py.typed exists, False otherwise.
    """
    # Search for py.typed in common locations
    for py_typed in repo_path.rglob("py.typed"):
        return True
    return False


def analyze_package(name: str, github_url: str, temp_dir: Path) -> PackageAnalysis:
    """Analyze a single package for type checker usage.

    Args:
        name: Package name.
        github_url: GitHub URL.
        temp_dir: Temporary directory for cloning.

    Returns:
        PackageAnalysis result.
    """
    analysis = PackageAnalysis(
        name=name,
        github_url=github_url,
        type_checkers={tc: TypeCheckerDetection() for tc in TYPE_CHECKERS},
    )

    repo_path = temp_dir / name
    print(f"  Cloning {github_url}...")

    if not clone_repo(github_url, repo_path):
        analysis.error = "Failed to clone repository"
        return analysis

    print(f"  Analyzing...")

    # Check for py.typed
    analysis.has_py_typed = check_py_typed(repo_path)

    # Analyze each type checker
    for checker in TYPE_CHECKERS:
        detection = analysis.type_checkers[checker]

        # Check GitHub workflows
        found, evidence = analyze_github_workflows(repo_path, checker)
        if found:
            detection.detected = True
            detection.locations.append("github_workflows")
            detection.evidence.extend(evidence)

        # Check pyproject.toml
        found, evidence = analyze_pyproject_toml(repo_path, checker)
        if found:
            detection.detected = True
            detection.locations.append("pyproject.toml")
            detection.evidence.extend(evidence)

        # Check requirements files
        found, evidence = analyze_requirements(repo_path, checker)
        if found:
            detection.detected = True
            detection.locations.append("requirements")
            detection.evidence.extend(evidence)

        # Check setup files
        found, evidence = analyze_setup_files(repo_path, checker)
        if found:
            detection.detected = True
            detection.locations.append("setup")
            detection.evidence.extend(evidence)

        # Check config files
        found, evidence = analyze_config_files(repo_path, checker)
        if found:
            detection.detected = True
            detection.locations.append("config_file")
            detection.evidence.extend(evidence)

    # Cleanup
    shutil.rmtree(repo_path, ignore_errors=True)

    return analysis


def load_packages_from_json(json_path: Path) -> list[tuple[str, str]]:
    """Load packages from the benchmark JSON file.

    Args:
        json_path: Path to benchmark_packages.json.

    Returns:
        List of (name, github_url) tuples.
    """
    packages = []

    # Load existing URLs from JSON
    existing_urls = load_existing_urls()

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    for pkg in data.get("packages", []):
        name = pkg["name"]
        github_url = pkg.get("github_url")

        # If no URL in JSON, try to fetch from PyPI
        if not github_url:
            github_url = resolve_github_url(name, {})

        if github_url:
            packages.append((name, github_url))
        else:
            print(f"Warning: No GitHub URL found for {name}")

    return packages


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Analyze packages for type checker usage")
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=ROOT_DIR / "type_checker_benchmark" / "benchmark_packages.json",
        help="Input package JSON file",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=ROOT_DIR / "type_checker_benchmark" / "benchmark_packages.json",
        help="Output JSON file",
    )
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=None,
        help="Limit number of packages to analyze",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Package Type Checker Analysis")
    print("=" * 70)

    # Load packages
    packages = load_packages_from_json(args.input)
    if args.limit:
        packages = packages[: args.limit]

    print(f"Analyzing {len(packages)} packages...")
    print()

    results = []

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        for i, (name, github_url) in enumerate(packages, 1):
            print(f"[{i}/{len(packages)}] {name}")
            analysis = analyze_package(name, github_url, temp_path)
            results.append(analysis.to_dict())

            # Print summary
            detected = [tc for tc, det in analysis.type_checkers.items() if det.detected]
            if detected:
                print(f"    Type checkers: {', '.join(detected)}")
            else:
                print(f"    No type checkers detected")
            if analysis.has_py_typed:
                print(f"    Has py.typed marker")
            print()

    # Save results
    output_data = {
        "packages": results,
        "type_checkers": TYPE_CHECKERS,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print("=" * 70)
    print(f"Results saved to: {args.output}")
    print("=" * 70)

    # Print summary
    total_by_checker = {tc: 0 for tc in TYPE_CHECKERS}
    for pkg in results:
        for tc in TYPE_CHECKERS:
            if pkg["type_checkers"].get(tc, {}).get("detected"):
                total_by_checker[tc] += 1

    print("\nSummary:")
    for tc, count in total_by_checker.items():
        print(f"  {tc}: {count} packages")


if __name__ == "__main__":
    main()
