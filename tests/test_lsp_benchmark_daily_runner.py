"""Tests for the LSP benchmark daily runner."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Import the module under test
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from lsp.benchmark.daily_runner import (
    KNOWN_GITHUB_URLS,
    TYPE_CHECKER_COMMANDS,
    AggregateStats,
    CheckerMetrics,
    PackageInfo,
    PackageResult,
    compute_aggregate_stats,
    fetch_github_package,
    find_type_checker_command,
    get_fallback_packages,
    load_prioritized_packages,
    parse_args,
    resolve_github_url,
    _parse_benchmark_results,
)


class TestLoadPrioritizedPackages:
    """Tests for load_prioritized_packages function."""

    def test_load_from_file(self, tmp_path: Path) -> None:
        """Test loading packages from a JSON file."""
        packages_file = tmp_path / "packages.json"
        packages_file.write_text(
            json.dumps(
                {
                    "requests": {
                        "DownloadCount": 1000000,
                        "DownloadRanking": 1,
                    },
                    "flask": {
                        "DownloadCount": 500000,
                        "DownloadRanking": 2,
                    },
                }
            )
        )

        result = load_prioritized_packages(packages_file=packages_file)

        assert len(result) == 2
        assert result[0]["name"] == "requests"
        assert result[0]["ranking"] == 1
        assert result[1]["name"] == "flask"
        assert result[1]["ranking"] == 2

    def test_load_with_limit(self, tmp_path: Path) -> None:
        """Test loading packages with a limit."""
        packages_file = tmp_path / "packages.json"
        packages_file.write_text(
            json.dumps(
                {
                    "requests": {"DownloadRanking": 1},
                    "flask": {"DownloadRanking": 2},
                    "django": {"DownloadRanking": 3},
                }
            )
        )

        result = load_prioritized_packages(limit=2, packages_file=packages_file)

        assert len(result) == 2
        assert result[0]["name"] == "requests"
        assert result[1]["name"] == "flask"

    def test_fallback_when_file_not_found(self, tmp_path: Path) -> None:
        """Test fallback to default packages when file not found."""
        non_existent = tmp_path / "does_not_exist.json"

        result = load_prioritized_packages(packages_file=non_existent)

        # Should return fallback packages
        assert len(result) > 0
        assert all("name" in pkg for pkg in result)
        assert all("github_url" in pkg for pkg in result)

    def test_packages_sorted_by_ranking(self, tmp_path: Path) -> None:
        """Test that packages are sorted by ranking."""
        packages_file = tmp_path / "packages.json"
        packages_file.write_text(
            json.dumps(
                {
                    "django": {"DownloadRanking": 3},
                    "requests": {"DownloadRanking": 1},
                    "flask": {"DownloadRanking": 2},
                }
            )
        )

        result = load_prioritized_packages(packages_file=packages_file)

        rankings = [pkg.get("ranking", 999) for pkg in result]
        assert rankings == sorted(rankings)


class TestGetFallbackPackages:
    """Tests for get_fallback_packages function."""

    def test_returns_list_of_packages(self) -> None:
        """Test that fallback returns a non-empty list."""
        result = get_fallback_packages()

        assert isinstance(result, list)
        assert len(result) > 0

    def test_packages_have_required_fields(self) -> None:
        """Test that each package has required fields."""
        result = get_fallback_packages()

        for pkg in result:
            assert "name" in pkg
            assert "github_url" in pkg
            assert "ranking" in pkg

    def test_github_urls_are_valid(self) -> None:
        """Test that GitHub URLs are properly formatted."""
        result = get_fallback_packages()

        for pkg in result:
            url = pkg.get("github_url")
            assert url is not None
            assert url.startswith("https://github.com/")


class TestResolveGithubUrl:
    """Tests for resolve_github_url function."""

    def test_known_package(self) -> None:
        """Test resolving URL for a known package."""
        result = resolve_github_url("requests", {})

        assert result == "https://github.com/psf/requests"

    def test_known_package_case_insensitive(self) -> None:
        """Test that package name lookup is case-insensitive."""
        result = resolve_github_url("REQUESTS", {})

        assert result == "https://github.com/psf/requests"

    def test_unknown_package_returns_none_without_network(self) -> None:
        """Test that unknown packages return None when PyPI fails."""
        with patch("lsp.benchmark.daily_runner._fetch_github_url_from_pypi") as mock:
            mock.return_value = None
            result = resolve_github_url("unknown_package_xyz", {})

        assert result is None


class TestFetchGithubPackage:
    """Tests for fetch_github_package function."""

    def test_successful_clone(self, tmp_path: Path) -> None:
        """Test successful git clone."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            result = fetch_github_package(
                "https://github.com/test/repo",
                "test_repo",
                tmp_path,
            )

            assert result == tmp_path / "test_repo"
            mock_run.assert_called_once()

    def test_clone_failure(self, tmp_path: Path) -> None:
        """Test handling of git clone failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="Clone failed")

            result = fetch_github_package(
                "https://github.com/test/repo",
                "test_repo",
                tmp_path,
            )

            assert result is None

    def test_clone_timeout(self, tmp_path: Path) -> None:
        """Test handling of git clone timeout."""
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=180)

            result = fetch_github_package(
                "https://github.com/test/repo",
                "test_repo",
                tmp_path,
            )

            assert result is None


class TestFindTypeCheckerCommand:
    """Tests for find_type_checker_command function."""

    def test_known_checker_available(self) -> None:
        """Test finding an available type checker."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = find_type_checker_command("pyright")

            assert result == TYPE_CHECKER_COMMANDS["pyright"]

    def test_known_checker_not_available(self) -> None:
        """Test when type checker is not installed."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)

            result = find_type_checker_command("pyright")

            assert result is None

    def test_unknown_checker(self) -> None:
        """Test with unknown type checker name."""
        result = find_type_checker_command("unknown_checker")

        assert result is None


class TestParseBenchmarkResults:
    """Tests for _parse_benchmark_results function."""

    def test_parse_valid_results(self) -> None:
        """Test parsing valid benchmark results."""
        benchmark_data: dict[str, Any] = {
            "summary": {
                "pyright": {
                    "ok": 5,
                    "ok_pct": 100.0,
                    "found": 4,
                    "found_pct": 80.0,
                    "valid": 4,
                    "valid_pct": 80.0,
                    "errors": 0,
                    "latency_ms": {
                        "p50": 100.0,
                        "p95": 150.0,
                        "min": 50.0,
                        "max": 200.0,
                        "mean": 110.0,
                    },
                }
            }
        }

        result = _parse_benchmark_results(benchmark_data, "pyright", 5)

        assert result["ok"] is True
        assert result["runs"] == 5
        assert result["ok_count"] == 5
        assert result["valid_pct"] == 80.0
        latency = result.get("latency_ms")
        assert latency is not None
        assert latency["mean"] == 110.0

    def test_parse_missing_checker(self) -> None:
        """Test parsing when checker not in results."""
        benchmark_data: dict[str, Any] = {"summary": {}}

        result = _parse_benchmark_results(benchmark_data, "pyright", 5)

        assert result["ok"] is True
        assert result["ok_count"] == 0
        latency = result.get("latency_ms")
        assert latency is not None
        assert latency["mean"] is None


class TestComputeAggregateStats:
    """Tests for compute_aggregate_stats function."""

    def test_compute_stats_with_valid_results(self) -> None:
        """Test computing aggregate statistics."""
        results: list[PackageResult] = [
            {
                "package_name": "pkg1",
                "github_url": "https://github.com/test/pkg1",
                "ranking": 1,
                "error": None,
                "metrics": {
                    "pyright": {
                        "ok": True,
                        "runs": 5,
                        "ok_count": 5,
                        "found_count": 4,
                        "valid_count": 4,
                        "latency_ms": {"mean": 100.0},
                    }
                },
            },
            {
                "package_name": "pkg2",
                "github_url": "https://github.com/test/pkg2",
                "ranking": 2,
                "error": None,
                "metrics": {
                    "pyright": {
                        "ok": True,
                        "runs": 5,
                        "ok_count": 5,
                        "found_count": 5,
                        "valid_count": 5,
                        "latency_ms": {"mean": 200.0},
                    }
                },
            },
        ]

        stats = compute_aggregate_stats(results, ["pyright"])

        assert stats["pyright"]["packages_tested"] == 2
        assert stats["pyright"]["total_runs"] == 10
        assert stats["pyright"]["total_valid"] == 9
        assert stats["pyright"]["avg_latency_ms"] == 150.0
        assert stats["pyright"]["success_rate"] == 90.0

    def test_compute_stats_with_errors(self) -> None:
        """Test computing stats when some packages have errors."""
        results: list[PackageResult] = [
            {
                "package_name": "pkg1",
                "github_url": None,
                "ranking": 1,
                "error": "No GitHub URL",
                "metrics": {},
            },
            {
                "package_name": "pkg2",
                "github_url": "https://github.com/test/pkg2",
                "ranking": 2,
                "error": None,
                "metrics": {
                    "pyright": {
                        "ok": True,
                        "runs": 5,
                        "ok_count": 5,
                        "valid_count": 5,
                        "latency_ms": {"mean": 100.0},
                    }
                },
            },
        ]

        stats = compute_aggregate_stats(results, ["pyright"])

        assert stats["pyright"]["packages_tested"] == 1
        assert stats["pyright"]["total_runs"] == 5

    def test_compute_stats_empty_results(self) -> None:
        """Test computing stats with no results."""
        stats = compute_aggregate_stats([], ["pyright"])

        assert stats["pyright"]["packages_tested"] == 0
        assert stats["pyright"]["total_runs"] == 0
        assert stats["pyright"]["avg_latency_ms"] is None
        assert stats["pyright"]["success_rate"] == 0.0


class TestParseArgs:
    """Tests for parse_args function."""

    def test_default_arguments(self) -> None:
        """Test parsing with default arguments."""
        args = parse_args([])

        assert args.packages == 10
        assert args.runs == 5
        assert args.output is None
        assert args.seed is None

    def test_custom_packages(self) -> None:
        """Test parsing custom package count."""
        args = parse_args(["--packages", "20"])

        assert args.packages == 20

    def test_custom_checkers(self) -> None:
        """Test parsing custom type checkers."""
        args = parse_args(["--checkers", "pyright", "mypy"])

        assert args.checkers == ["pyright", "mypy"]

    def test_output_path(self) -> None:
        """Test parsing output path."""
        args = parse_args(["--output", "/tmp/results"])

        assert args.output == Path("/tmp/results")

    def test_seed(self) -> None:
        """Test parsing random seed."""
        args = parse_args(["--seed", "42"])

        assert args.seed == 42

    def test_short_flags(self) -> None:
        """Test parsing with short flags."""
        args = parse_args(["-p", "5", "-r", "3", "-s", "123"])

        assert args.packages == 5
        assert args.runs == 3
        assert args.seed == 123


class TestKnownGithubUrls:
    """Tests for KNOWN_GITHUB_URLS constant."""

    def test_common_packages_included(self) -> None:
        """Test that common packages are in the known URLs."""
        common_packages = ["requests", "flask", "django", "numpy", "pandas"]

        for pkg in common_packages:
            assert pkg in KNOWN_GITHUB_URLS
            assert KNOWN_GITHUB_URLS[pkg].startswith("https://github.com/")

    def test_urls_are_valid_format(self) -> None:
        """Test that all URLs are properly formatted."""
        for name, url in KNOWN_GITHUB_URLS.items():
            assert url.startswith("https://github.com/"), f"Invalid URL for {name}"
            # URL should have owner/repo format
            parts = url.replace("https://github.com/", "").split("/")
            assert len(parts) >= 2, f"Missing owner/repo in URL for {name}"


class TestTypeCheckerCommands:
    """Tests for TYPE_CHECKER_COMMANDS constant."""

    def test_supported_checkers(self) -> None:
        """Test that expected type checkers are supported."""
        expected = ["pyright", "pyrefly", "ty"]

        for checker in expected:
            assert checker in TYPE_CHECKER_COMMANDS

    def test_commands_are_strings(self) -> None:
        """Test that all commands are non-empty strings."""
        for name, cmd in TYPE_CHECKER_COMMANDS.items():
            assert isinstance(cmd, str), f"Command for {name} is not a string"
            assert len(cmd) > 0, f"Command for {name} is empty"
