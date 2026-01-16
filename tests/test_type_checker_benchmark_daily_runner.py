"""Tests for the type checker benchmark daily runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from type_checker_benchmark.daily_runner import (
    DEFAULT_TYPE_CHECKERS,
    AggregateStats,
    ErrorMetrics,
    PackageResult,
    compute_aggregate_stats,
    compute_percentile,
    fetch_github_package,
    get_fallback_packages,
    get_type_checker_versions,
    is_type_checker_available,
    load_benchmark_packages,
    load_prioritized_packages,
    parse_args,
    run_process_with_timeout,
)


class TestLoadBenchmarkPackages:
    """Tests for load_benchmark_packages function."""

    def test_load_from_file(self, tmp_path: Path) -> None:
        """Test loading packages from a JSON file."""
        packages_file = tmp_path / "benchmark_packages.json"
        packages_file.write_text(
            json.dumps(
                {
                    "packages": [
                        {
                            "name": "requests",
                            "github_url": "https://github.com/psf/requests",
                            "has_py_typed": True,
                            "type_checkers": {
                                "pyright": {"detected": True},
                                "mypy": {"detected": False},
                            },
                        },
                        {
                            "name": "flask",
                            "github_url": "https://github.com/pallets/flask",
                            "has_py_typed": False,
                            "type_checkers": {},
                        },
                    ]
                }
            )
        )

        result = load_benchmark_packages(packages_file=packages_file)

        assert len(result) == 2
        assert result[0]["name"] == "requests"
        assert result[0]["github_url"] == "https://github.com/psf/requests"
        assert result[0]["has_py_typed"] is True
        assert result[0]["configured_checkers"]["pyright"] is True
        assert result[0]["configured_checkers"]["mypy"] is False
        assert result[1]["name"] == "flask"

    def test_load_with_limit(self, tmp_path: Path) -> None:
        """Test loading packages with a limit."""
        packages_file = tmp_path / "benchmark_packages.json"
        packages_file.write_text(
            json.dumps(
                {
                    "packages": [
                        {"name": "requests", "github_url": "https://github.com/psf/requests"},
                        {"name": "flask", "github_url": "https://github.com/pallets/flask"},
                        {"name": "django", "github_url": "https://github.com/django/django"},
                    ]
                }
            )
        )

        result = load_benchmark_packages(limit=2, packages_file=packages_file)

        assert len(result) == 2
        assert result[0]["name"] == "requests"
        assert result[1]["name"] == "flask"

    def test_fallback_when_file_not_found(self, tmp_path: Path) -> None:
        """Test fallback to default packages when file not found."""
        non_existent = tmp_path / "does_not_exist.json"

        result = load_benchmark_packages(packages_file=non_existent)

        # Should return fallback packages
        assert len(result) > 0
        assert all("name" in pkg for pkg in result)
        assert all("github_url" in pkg for pkg in result)

    def test_skip_packages_without_github_url(self, tmp_path: Path) -> None:
        """Test that packages without GitHub URLs are skipped."""
        packages_file = tmp_path / "benchmark_packages.json"
        packages_file.write_text(
            json.dumps(
                {
                    "packages": [
                        {"name": "requests", "github_url": "https://github.com/psf/requests"},
                        {"name": "no_url_package"},  # Missing github_url
                    ]
                }
            )
        )

        result = load_benchmark_packages(packages_file=packages_file)

        assert len(result) == 1
        assert result[0]["name"] == "requests"


class TestLoadPrioritizedPackages:
    """Tests for load_prioritized_packages function."""

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

        with patch("type_checker_benchmark.daily_runner._fetch_github_url_from_pypi") as mock:
            mock.return_value = "https://github.com/test/repo"
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

    def test_well_known_packages_included(self) -> None:
        """Test that common packages are in the fallback list."""
        result = get_fallback_packages()
        names = [pkg["name"] for pkg in result]

        common_packages = ["requests", "flask", "django", "numpy", "pandas"]
        for pkg in common_packages:
            assert pkg in names, f"Expected {pkg} in fallback packages"


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


class TestRunProcessWithTimeout:
    """Tests for run_process_with_timeout function."""

    def test_successful_command(self, tmp_path: Path) -> None:
        """Test running a successful command."""
        result = run_process_with_timeout(
            ["echo", "hello"],
            cwd=tmp_path,
            timeout=10,
        )

        assert result["timed_out"] is False
        assert result["returncode"] == 0
        assert "hello" in result["stdout"]
        assert result["execution_time_s"] >= 0

    def test_failed_command(self, tmp_path: Path) -> None:
        """Test running a command that fails."""
        result = run_process_with_timeout(
            ["false"],  # Returns non-zero exit code
            cwd=tmp_path,
            timeout=10,
        )

        assert result["timed_out"] is False
        assert result["returncode"] != 0


class TestIsTypeCheckerAvailable:
    """Tests for is_type_checker_available function."""

    def test_known_checker_available(self) -> None:
        """Test checking for an available type checker."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = is_type_checker_available("pyright")

            assert result is True

    def test_known_checker_not_available(self) -> None:
        """Test when type checker is not installed."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)

            result = is_type_checker_available("pyright")

            assert result is False

    def test_unknown_checker(self) -> None:
        """Test with unknown type checker name."""
        result = is_type_checker_available("unknown_checker")

        assert result is False


class TestGetTypeCheckerVersions:
    """Tests for get_type_checker_versions function."""

    def test_returns_dict_with_all_checkers(self) -> None:
        """Test that versions dict includes all expected checkers."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="pyright 1.2.3",
                stderr="",
            )

            result = get_type_checker_versions()

            assert isinstance(result, dict)
            # Should have entries for known type checkers
            for checker in ["pyright", "pyrefly", "ty", "mypy", "zuban"]:
                assert checker in result

    def test_parses_version_number(self) -> None:
        """Test that version numbers are parsed correctly."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="pyright 1.2.345",
                stderr="",
            )

            result = get_type_checker_versions()

            # Should find semver pattern
            assert result["pyright"] == "1.2.345"

    def test_handles_not_installed(self) -> None:
        """Test handling of unavailable type checkers."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("command not found")

            result = get_type_checker_versions()

            for version in result.values():
                assert version == "not installed"


class TestComputePercentile:
    """Tests for compute_percentile function."""

    def test_empty_list(self) -> None:
        """Test percentile of empty list."""
        result = compute_percentile([], 95)
        assert result == 0.0

    def test_single_value(self) -> None:
        """Test percentile of single value."""
        result = compute_percentile([100], 95)
        assert result == 100.0

    def test_p50(self) -> None:
        """Test 50th percentile (median)."""
        result = compute_percentile([1, 2, 3, 4, 5], 50)
        assert result == 3.0

    def test_p95(self) -> None:
        """Test 95th percentile."""
        values = list(range(1, 101))  # 1 to 100
        result = compute_percentile(values, 95)
        # p95 of [1..100] should be close to 95
        assert 94 <= result <= 96

    def test_p100(self) -> None:
        """Test 100th percentile (max)."""
        result = compute_percentile([1, 2, 3, 4, 100], 100)
        assert result == 100.0


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
                        "error_count": 100,
                        "warning_count": 10,
                        "info_count": 5,
                        "files_checked": 20,
                        "execution_time_s": 5.0,
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
                        "error_count": 200,
                        "warning_count": 20,
                        "info_count": 10,
                        "files_checked": 40,
                        "execution_time_s": 10.0,
                    }
                },
            },
        ]

        stats = compute_aggregate_stats(results, ["pyright"])

        assert stats["pyright"]["packages_tested"] == 2
        assert stats["pyright"]["total_errors"] == 300
        assert stats["pyright"]["total_warnings"] == 30
        assert stats["pyright"]["avg_errors_per_package"] == 150.0
        assert stats["pyright"]["min_errors"] == 100
        assert stats["pyright"]["max_errors"] == 200
        assert stats["pyright"]["avg_execution_time_s"] == 7.5

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
                        "error_count": 100,
                        "warning_count": 10,
                        "execution_time_s": 5.0,
                    }
                },
            },
        ]

        stats = compute_aggregate_stats(results, ["pyright"])

        # Only pkg2 should be counted
        assert stats["pyright"]["packages_tested"] == 1
        assert stats["pyright"]["total_errors"] == 100

    def test_compute_stats_with_failed_checker(self) -> None:
        """Test computing stats when checker failed for a package."""
        results: list[PackageResult] = [
            {
                "package_name": "pkg1",
                "github_url": "https://github.com/test/pkg1",
                "ranking": 1,
                "error": None,
                "metrics": {
                    "pyright": {
                        "ok": False,
                        "error_count": 0,
                        "warning_count": 0,
                        "error_message": "Timeout",
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
                        "error_count": 100,
                        "warning_count": 10,
                        "execution_time_s": 5.0,
                    }
                },
            },
        ]

        stats = compute_aggregate_stats(results, ["pyright"])

        # Only pkg2 should be counted (pkg1 checker failed)
        assert stats["pyright"]["packages_tested"] == 1
        assert stats["pyright"]["total_errors"] == 100

    def test_compute_stats_empty_results(self) -> None:
        """Test computing stats with no results."""
        stats = compute_aggregate_stats([], ["pyright"])

        assert stats["pyright"]["packages_tested"] == 0
        assert stats["pyright"]["total_errors"] == 0
        assert stats["pyright"]["total_warnings"] == 0
        assert stats["pyright"]["avg_errors_per_package"] == 0.0

    def test_compute_stats_multiple_checkers(self) -> None:
        """Test computing stats for multiple type checkers."""
        results: list[PackageResult] = [
            {
                "package_name": "pkg1",
                "github_url": "https://github.com/test/pkg1",
                "ranking": 1,
                "error": None,
                "metrics": {
                    "pyright": {
                        "ok": True,
                        "error_count": 100,
                        "warning_count": 10,
                        "execution_time_s": 5.0,
                    },
                    "mypy": {
                        "ok": True,
                        "error_count": 50,
                        "warning_count": 5,
                        "execution_time_s": 8.0,
                    },
                },
            },
        ]

        stats = compute_aggregate_stats(results, ["pyright", "mypy"])

        assert stats["pyright"]["total_errors"] == 100
        assert stats["mypy"]["total_errors"] == 50


class TestParseArgs:
    """Tests for parse_args function."""

    def test_default_arguments(self) -> None:
        """Test parsing with default arguments."""
        args = parse_args([])

        assert args.packages is None
        assert args.package_names is None
        assert args.checkers == DEFAULT_TYPE_CHECKERS
        assert args.timeout == 300
        assert args.output is None
        assert args.os_name is None

    def test_custom_packages(self) -> None:
        """Test parsing custom package count."""
        args = parse_args(["--packages", "20"])

        assert args.packages == 20

    def test_package_names(self) -> None:
        """Test parsing specific package names."""
        args = parse_args(["--package-names", "requests", "flask", "django"])

        assert args.package_names == ["requests", "flask", "django"]

    def test_custom_checkers(self) -> None:
        """Test parsing custom type checkers."""
        args = parse_args(["--checkers", "pyright", "mypy"])

        assert args.checkers == ["pyright", "mypy"]

    def test_timeout(self) -> None:
        """Test parsing timeout."""
        args = parse_args(["--timeout", "600"])

        assert args.timeout == 600

    def test_output_path(self) -> None:
        """Test parsing output path."""
        args = parse_args(["--output", "/tmp/results"])

        assert args.output == Path("/tmp/results")

    def test_os_name(self) -> None:
        """Test parsing OS name."""
        args = parse_args(["--os-name", "ubuntu"])

        assert args.os_name == "ubuntu"

    def test_short_flags(self) -> None:
        """Test parsing with short flags."""
        args = parse_args(["-p", "5", "-t", "120"])

        assert args.packages == 5
        assert args.timeout == 120


class TestDefaultTypeCheckers:
    """Tests for DEFAULT_TYPE_CHECKERS constant."""

    def test_expected_checkers_included(self) -> None:
        """Test that expected type checkers are in the default list."""
        expected = ["pyright", "pyrefly", "ty", "mypy", "zuban"]

        for checker in expected:
            assert checker in DEFAULT_TYPE_CHECKERS

    def test_no_duplicates(self) -> None:
        """Test that there are no duplicate checkers."""
        assert len(DEFAULT_TYPE_CHECKERS) == len(set(DEFAULT_TYPE_CHECKERS))
