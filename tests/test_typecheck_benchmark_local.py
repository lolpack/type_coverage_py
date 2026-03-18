"""Tests for --local flag in typecheck benchmark.

Verifies that the local directory benchmarking mode works correctly:
skips cloning/deps, runs checkers on the specified directory, and
produces valid output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from typecheck_benchmark.daily_runner import (
    _benchmark_local_dir,
    _run_local_benchmark,
    main,
    parse_args,
    run_benchmark,
)


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


class TestParseArgsLocal:
    def test_local_flag_default_none(self) -> None:
        args = parse_args([])
        assert args.local is None

    def test_local_flag_accepts_path(self) -> None:
        args = parse_args(["--local", "/some/dir"])
        assert args.local == Path("/some/dir")

    def test_local_flag_with_other_flags(self) -> None:
        args = parse_args(["--local", "/dir", "--checkers", "pyright", "--runs", "3"])
        assert args.local == Path("/dir")
        assert args.checkers == ["pyright"]
        assert args.runs == 3


# ---------------------------------------------------------------------------
# _benchmark_local_dir
# ---------------------------------------------------------------------------


class TestBenchmarkLocalDir:
    def _make_fake_run(self) -> object:
        def fake_run(cmd: list[str], **kwargs: object) -> dict[str, object]:
            return {
                "stdout": "",
                "stderr": "",
                "returncode": 0,
                "timed_out": False,
                "execution_time_s": 1.23,
                "peak_memory_mb": 100.0,
                "oom_killed": False,
            }
        return fake_run

    @patch("typecheck_benchmark.daily_runner.is_type_checker_available", return_value=True)
    @patch("typecheck_benchmark.daily_runner.run_process_with_timeout")
    def test_returns_package_result(self, mock_run: object, mock_avail: object, tmp_path: Path) -> None:
        mock_run.side_effect = self._make_fake_run()  # type: ignore[union-attr]
        result = _benchmark_local_dir(tmp_path, ["pyright"], timeout=60)
        assert result["package_name"] == tmp_path.name
        assert result["github_url"] is None
        assert result["error"] is None
        assert "pyright" in result["metrics"]
        assert result["metrics"]["pyright"]["ok"] is True

    @patch("typecheck_benchmark.daily_runner.is_type_checker_available", return_value=True)
    @patch("typecheck_benchmark.daily_runner.run_process_with_timeout")
    def test_uses_local_dir_as_cwd(self, mock_run: object, mock_avail: object, tmp_path: Path) -> None:
        mock_run.side_effect = self._make_fake_run()  # type: ignore[union-attr]
        _benchmark_local_dir(tmp_path, ["pyright"], timeout=60)
        call_kwargs = mock_run.call_args  # type: ignore[union-attr]
        assert call_kwargs[1]["cwd"] == tmp_path

    @patch("typecheck_benchmark.daily_runner.is_type_checker_available", return_value=True)
    @patch("typecheck_benchmark.daily_runner.run_process_with_timeout")
    def test_no_check_paths_passed(self, mock_run: object, mock_avail: object, tmp_path: Path) -> None:
        """Local mode passes None for check_paths, so checker uses full dir."""
        mock_run.side_effect = self._make_fake_run()  # type: ignore[union-attr]
        _benchmark_local_dir(tmp_path, ["pyright"], timeout=60)
        # pyright with no check_paths => pyrightconfig.json includes ["."]
        config = json.loads((tmp_path / "pyrightconfig.json").read_text())
        assert config["include"] == ["."]

    @patch("typecheck_benchmark.daily_runner.is_type_checker_available", return_value=False)
    def test_skips_unavailable_checker(self, mock_avail: object, tmp_path: Path) -> None:
        result = _benchmark_local_dir(tmp_path, ["pyright"], timeout=60)
        assert result["metrics"]["pyright"]["ok"] is False
        assert result["metrics"]["pyright"]["error_message"] == "Not installed"

    @patch("typecheck_benchmark.daily_runner.is_type_checker_available", return_value=True)
    @patch("typecheck_benchmark.daily_runner.run_process_with_timeout")
    def test_does_not_delete_local_dir(self, mock_run: object, mock_avail: object, tmp_path: Path) -> None:
        """Local mode must NOT delete the user's directory."""
        mock_run.side_effect = self._make_fake_run()  # type: ignore[union-attr]
        _benchmark_local_dir(tmp_path, ["pyright"], timeout=60)
        assert tmp_path.exists()

    @patch("typecheck_benchmark.daily_runner.is_type_checker_available", return_value=True)
    @patch("typecheck_benchmark.daily_runner.run_process_with_timeout")
    def test_multiple_runs(self, mock_run: object, mock_avail: object, tmp_path: Path) -> None:
        mock_run.side_effect = self._make_fake_run()  # type: ignore[union-attr]
        result = _benchmark_local_dir(tmp_path, ["pyright"], timeout=60, runs=3)
        assert result["metrics"]["pyright"]["runs"] == 3
        assert "execution_time_stats" in result["metrics"]["pyright"]


# ---------------------------------------------------------------------------
# _run_local_benchmark (end-to-end with mocks)
# ---------------------------------------------------------------------------


class TestRunLocalBenchmark:
    @patch("typecheck_benchmark.daily_runner.is_type_checker_available", return_value=True)
    @patch("typecheck_benchmark.daily_runner.run_process_with_timeout")
    @patch("typecheck_benchmark.daily_runner.get_type_checker_versions", return_value={"pyright": "1.0.0"})
    def test_produces_json_output(self, mock_ver: object, mock_run: object, mock_avail: object, tmp_path: Path) -> None:
        mock_run.return_value = {  # type: ignore[union-attr]
            "stdout": "", "stderr": "", "returncode": 0,
            "timed_out": False, "execution_time_s": 1.0,
            "peak_memory_mb": 50.0, "oom_killed": False,
        }
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        local_dir = tmp_path / "myproject"
        local_dir.mkdir()

        result_path = _run_local_benchmark(
            local_dir, ["pyright"], timeout=60,
            output_dir=output_dir, os_name=None, runs=1,
        )
        assert result_path.exists()
        data = json.loads(result_path.read_text())
        assert len(data["results"]) == 1
        assert data["results"][0]["package_name"] == "myproject"
        assert data["results"][0]["github_url"] is None

    @patch("typecheck_benchmark.daily_runner.is_type_checker_available", return_value=True)
    @patch("typecheck_benchmark.daily_runner.run_process_with_timeout")
    @patch("typecheck_benchmark.daily_runner.get_type_checker_versions", return_value={"pyright": "1.0.0"})
    def test_nonexistent_dir_returns_empty(self, mock_ver: object, mock_run: object, mock_avail: object, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        result_path = _run_local_benchmark(
            tmp_path / "nonexistent", ["pyright"], timeout=60,
            output_dir=output_dir, os_name=None, runs=1,
        )
        assert result_path == output_dir / "empty.json"


# ---------------------------------------------------------------------------
# run_benchmark with local_dir
# ---------------------------------------------------------------------------


class TestRunBenchmarkLocal:
    @patch("typecheck_benchmark.daily_runner.is_type_checker_available", return_value=True)
    @patch("typecheck_benchmark.daily_runner.run_process_with_timeout")
    @patch("typecheck_benchmark.daily_runner.get_type_checker_versions", return_value={"pyright": "1.0.0"})
    def test_local_dir_skips_install_envs(self, mock_ver: object, mock_run: object, mock_avail: object, tmp_path: Path) -> None:
        """When --local is used, install_envs.json should not be loaded."""
        mock_run.return_value = {  # type: ignore[union-attr]
            "stdout": "", "stderr": "", "returncode": 0,
            "timed_out": False, "execution_time_s": 1.0,
            "peak_memory_mb": 50.0, "oom_killed": False,
        }
        local_dir = tmp_path / "myproject"
        local_dir.mkdir()
        output_dir = tmp_path / "output"

        with patch("typecheck_benchmark.daily_runner.load_install_envs") as mock_load:
            run_benchmark(
                type_checkers=["pyright"],
                timeout=60,
                output_dir=output_dir,
                local_dir=local_dir,
            )
            mock_load.assert_not_called()


# ---------------------------------------------------------------------------
# main() with --local
# ---------------------------------------------------------------------------


class TestMainLocal:
    @patch("typecheck_benchmark.daily_runner.run_benchmark")
    def test_passes_local_dir(self, mock_rb: object) -> None:
        mock_rb.return_value = Path("/fake/output.json")  # type: ignore[union-attr]
        main(["--local", "/some/dir", "--checkers", "pyright"])
        mock_rb.assert_called_once()  # type: ignore[union-attr]
        call_kwargs = mock_rb.call_args[1]  # type: ignore[union-attr]
        assert call_kwargs["local_dir"] == Path("/some/dir")
