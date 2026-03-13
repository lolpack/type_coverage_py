"""Tests for the LSP benchmark daily runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# Import the module under test
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from lsp.benchmark.daily_runner import (
    TYPE_CHECKER_COMMANDS,
    PackageResult,
    compute_aggregate_stats,
    fetch_github_package,
    find_type_checker_command,
    load_packages_from_install_envs,
    parse_args,
    _parse_benchmark_results,
    _save_results,
)


class TestLoadPackagesFromInstallEnvs:
    """Tests for load_packages_from_install_envs function."""

    def _write_install_envs(self, tmp_path: Path, packages: list[dict[str, Any]]) -> Path:
        """Write a test install_envs.json and return path to its parent dir."""
        envs_dir = tmp_path / "typecheck_benchmark"
        envs_dir.mkdir()
        envs_file = envs_dir / "install_envs.json"
        envs_file.write_text(json.dumps({"packages": packages}))
        return tmp_path

    def test_loads_all_packages(self, tmp_path: Path) -> None:
        """Test loading all packages from install_envs.json."""
        root = self._write_install_envs(tmp_path, [
            {"github_url": "https://github.com/psf/requests", "name": "requests"},
            {"github_url": "https://github.com/pallets/flask", "name": "flask"},
        ])

        with patch("lsp.benchmark.daily_runner.ROOT_DIR", root):
            result = load_packages_from_install_envs()

        assert len(result) == 2
        assert result[0]["name"] == "requests"
        assert result[1]["name"] == "flask"

    def test_filter_by_package_names(self, tmp_path: Path) -> None:
        """Test filtering by specific package names."""
        root = self._write_install_envs(tmp_path, [
            {"github_url": "https://github.com/psf/requests", "name": "requests"},
            {"github_url": "https://github.com/pallets/flask", "name": "flask"},
            {"github_url": "https://github.com/django/django", "name": "django"},
        ])

        with patch("lsp.benchmark.daily_runner.ROOT_DIR", root):
            result = load_packages_from_install_envs(package_names=["flask", "django"])

        assert len(result) == 2
        names = [p["name"] for p in result]
        assert "flask" in names
        assert "django" in names

    def test_limit(self, tmp_path: Path) -> None:
        """Test limiting number of packages."""
        root = self._write_install_envs(tmp_path, [
            {"github_url": "https://github.com/psf/requests", "name": "requests"},
            {"github_url": "https://github.com/pallets/flask", "name": "flask"},
            {"github_url": "https://github.com/django/django", "name": "django"},
        ])

        with patch("lsp.benchmark.daily_runner.ROOT_DIR", root):
            result = load_packages_from_install_envs(limit=2)

        assert len(result) == 2

    def test_derives_name_from_url(self, tmp_path: Path) -> None:
        """Test that name is derived from github_url when not specified."""
        root = self._write_install_envs(tmp_path, [
            {"github_url": "https://github.com/psf/requests"},
        ])

        with patch("lsp.benchmark.daily_runner.ROOT_DIR", root):
            result = load_packages_from_install_envs()

        assert result[0]["name"] == "requests"

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """Test that missing install_envs.json returns empty list."""
        with patch("lsp.benchmark.daily_runner.ROOT_DIR", tmp_path):
            result = load_packages_from_install_envs()

        assert result == []

    def test_warns_on_unknown_package_name(self, tmp_path: Path, capsys: Any) -> None:
        """Test warning when a requested package is not in install_envs.json."""
        root = self._write_install_envs(tmp_path, [
            {"github_url": "https://github.com/psf/requests", "name": "requests"},
        ])

        with patch("lsp.benchmark.daily_runner.ROOT_DIR", root):
            result = load_packages_from_install_envs(package_names=["requests", "nonexistent"])

        assert len(result) == 1
        captured = capsys.readouterr()
        assert "nonexistent" in captured.out

    def test_github_urls_are_valid(self, tmp_path: Path) -> None:
        """Test that all packages have valid GitHub URLs."""
        root = self._write_install_envs(tmp_path, [
            {"github_url": "https://github.com/psf/requests", "name": "requests"},
        ])

        with patch("lsp.benchmark.daily_runner.ROOT_DIR", root):
            result = load_packages_from_install_envs()

        for pkg in result:
            url = pkg["github_url"]
            assert url is not None
            assert url.startswith("https://github.com/")


class TestInstallEnvsIsSharedSource:
    """Tests that LSP benchmark uses the same install_envs.json as typecheck benchmark."""

    def test_install_envs_exists(self) -> None:
        """Test that the shared install_envs.json exists."""
        root = Path(__file__).parent.parent
        install_envs = root / "typecheck_benchmark" / "install_envs.json"
        assert install_envs.exists(), "install_envs.json must exist as shared package source"

    def test_install_envs_has_packages(self) -> None:
        """Test that install_envs.json has packages with github_urls."""
        root = Path(__file__).parent.parent
        install_envs = root / "typecheck_benchmark" / "install_envs.json"
        with open(install_envs) as f:
            data = json.load(f)
        packages = data.get("packages", [])
        assert len(packages) > 0
        for pkg in packages:
            assert "github_url" in pkg


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
        assert stats["pyright"]["ok_rate"] == 100.0
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
        assert stats["pyright"]["ok_rate"] == 0.0
        assert stats["pyright"]["success_rate"] == 0.0

    def test_compute_stats_with_timeouts(self) -> None:
        """Test ok_rate calculation when some requests timeout."""
        results: list[PackageResult] = [
            {
                "package_name": "pkg1",
                "github_url": "https://github.com/test/pkg1",
                "ranking": 1,
                "error": None,
                "metrics": {
                    "pyright": {
                        "ok": True,
                        "runs": 10,
                        "ok_count": 8,  # 2 timeouts
                        "found_count": 7,
                        "valid_count": 7,
                        "latency_ms": {"mean": 100.0},
                    }
                },
            },
        ]

        stats = compute_aggregate_stats(results, ["pyright"])

        assert stats["pyright"]["total_runs"] == 10
        assert stats["pyright"]["total_ok"] == 8
        assert stats["pyright"]["ok_rate"] == 80.0  # 8/10 * 100
        assert stats["pyright"]["success_rate"] == 70.0  # 7/10 * 100

    def test_compute_stats_ok_rate_vs_success_rate(self) -> None:
        """Test that ok_rate and success_rate are calculated independently."""
        results: list[PackageResult] = [
            {
                "package_name": "pkg1",
                "github_url": "https://github.com/test/pkg1",
                "ranking": 1,
                "error": None,
                "metrics": {
                    "pyright": {
                        "ok": True,
                        "runs": 100,
                        "ok_count": 95,  # 95% completed without timeout
                        "found_count": 90,
                        "valid_count": 85,  # 85% returned valid definitions
                        "latency_ms": {"mean": 100.0},
                    }
                },
            },
        ]

        stats = compute_aggregate_stats(results, ["pyright"])

        assert stats["pyright"]["ok_rate"] == 95.0  # Reliability
        assert stats["pyright"]["success_rate"] == 85.0  # Accuracy
        # ok_rate should be >= success_rate since ok includes non-valid results
        assert stats["pyright"]["ok_rate"] >= stats["pyright"]["success_rate"]

    def test_compute_stats_multiple_checkers_different_ok_rates(self) -> None:
        """Test ok_rate calculation for multiple type checkers."""
        results: list[PackageResult] = [
            {
                "package_name": "pkg1",
                "github_url": "https://github.com/test/pkg1",
                "ranking": 1,
                "error": None,
                "metrics": {
                    "pyright": {
                        "ok": True,
                        "runs": 10,
                        "ok_count": 10,
                        "valid_count": 8,
                        "latency_ms": {"mean": 100.0},
                    },
                    "pyrefly": {
                        "ok": True,
                        "runs": 10,
                        "ok_count": 9,  # 1 timeout
                        "valid_count": 7,
                        "latency_ms": {"mean": 80.0},
                    },
                },
            },
        ]

        stats = compute_aggregate_stats(results, ["pyright", "pyrefly"])

        assert stats["pyright"]["ok_rate"] == 100.0
        assert stats["pyright"]["success_rate"] == 80.0
        assert stats["pyrefly"]["ok_rate"] == 90.0
        assert stats["pyrefly"]["success_rate"] == 70.0


class TestParseArgs:
    """Tests for parse_args function."""

    def test_default_arguments(self) -> None:
        """Test parsing with default arguments."""
        args = parse_args([])

        assert args.packages is None  # None means all packages
        assert args.runs == 100
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

    def test_install_deps_flag(self) -> None:
        """Test parsing --install-deps flag."""
        args = parse_args(["--install-deps"])
        assert args.install_deps is True

    def test_install_deps_default_false(self) -> None:
        """Test that --install-deps defaults to False."""
        args = parse_args([])
        assert args.install_deps is False


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


class TestParseArgsOsName:
    """Tests for parse_args --os-name argument."""

    def test_default_os_name_is_none(self) -> None:
        """Test that os_name defaults to None."""
        args = parse_args([])
        assert args.os_name is None

    def test_os_name_ubuntu(self) -> None:
        """Test parsing --os-name ubuntu."""
        args = parse_args(["--os-name", "ubuntu"])
        assert args.os_name == "ubuntu"

    def test_os_name_macos(self) -> None:
        """Test parsing --os-name macos."""
        args = parse_args(["--os-name", "macos"])
        assert args.os_name == "macos"

    def test_os_name_windows(self) -> None:
        """Test parsing --os-name windows."""
        args = parse_args(["--os-name", "windows"])
        assert args.os_name == "windows"


class TestSaveResultsOsName:
    """Tests for _save_results with os_name parameter."""

    def _make_sample_data(self) -> tuple[list[PackageResult], dict, list[str], dict[str, str]]:
        """Create sample data for testing _save_results."""
        results: list[PackageResult] = [
            {
                "package_name": "requests",
                "github_url": "https://github.com/psf/requests",
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
        ]
        aggregate: dict[str, Any] = {
            "pyright": {
                "packages_tested": 1,
                "total_runs": 5,
                "total_ok": 5,
                "total_found": 4,
                "total_valid": 4,
                "avg_latency_ms": 100.0,
                "min_latency_ms": 100.0,
                "max_latency_ms": 100.0,
                "success_rate": 80.0,
            }
        }
        type_checkers = ["pyright"]
        versions = {"pyright": "1.1.400"}
        return results, aggregate, type_checkers, versions

    def test_save_with_os_name_creates_os_specific_files(self, tmp_path: Path) -> None:
        """Test that os_name creates OS-specific filenames."""
        results, aggregate, checkers, versions = self._make_sample_data()

        output_file = _save_results(
            results, aggregate, checkers, versions,
            package_count=1, runs_per_package=5,
            output_dir=tmp_path, os_name="macos",
        )

        assert "_macos.json" in output_file.name
        assert (tmp_path / f"latest-macos.json").exists()

        # Verify the output contains the os field
        with open(output_file) as f:
            data = json.load(f)
        assert data["os"] == "macos"

    def test_save_without_os_name_creates_standard_files(self, tmp_path: Path) -> None:
        """Test that no os_name creates standard filenames (backwards compat)."""
        results, aggregate, checkers, versions = self._make_sample_data()

        output_file = _save_results(
            results, aggregate, checkers, versions,
            package_count=1, runs_per_package=5,
            output_dir=tmp_path,
        )

        assert "_ubuntu" not in output_file.name
        assert "_macos" not in output_file.name
        assert "_windows" not in output_file.name
        assert (tmp_path / "latest.json").exists()

        # Verify the output does NOT contain the os field
        with open(output_file) as f:
            data = json.load(f)
        assert "os" not in data

    def test_save_latest_file_matches_dated_file(self, tmp_path: Path) -> None:
        """Test that latest-{os}.json matches the dated file content."""
        results, aggregate, checkers, versions = self._make_sample_data()

        output_file = _save_results(
            results, aggregate, checkers, versions,
            package_count=1, runs_per_package=5,
            output_dir=tmp_path, os_name="ubuntu",
        )

        with open(output_file) as f:
            dated_data = json.load(f)
        with open(tmp_path / "latest-ubuntu.json") as f:
            latest_data = json.load(f)

        assert dated_data == latest_data
