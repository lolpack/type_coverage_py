"""Tests for typecheck benchmark dummy config generation.

Verifies that each _write_dummy_*_config function produces valid config files
with check_paths correctly embedded in each checker's native format.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from typecheck_benchmark.daily_runner import (
    _write_dummy_mypy_config,
    _write_dummy_pyrefly_config,
    _write_dummy_pyright_config,
    _write_dummy_ty_config,
    _write_dummy_zuban_config,
    run_checker,
)


# ---------------------------------------------------------------------------
# _write_dummy_pyright_config
# ---------------------------------------------------------------------------


class TestWriteDummyPyrightConfig:
    def test_default_includes_dot(self, tmp_path: Path) -> None:
        _write_dummy_pyright_config(tmp_path)
        config = json.loads((tmp_path / "pyrightconfig.json").read_text())
        assert config["include"] == ["."]

    def test_check_paths_embedded(self, tmp_path: Path) -> None:
        _write_dummy_pyright_config(tmp_path, ["src", "lib"])
        config = json.loads((tmp_path / "pyrightconfig.json").read_text())
        assert config["include"] == ["src", "lib"]

    def test_always_has_basic_mode(self, tmp_path: Path) -> None:
        _write_dummy_pyright_config(tmp_path, ["src"])
        config = json.loads((tmp_path / "pyrightconfig.json").read_text())
        assert config["typeCheckingMode"] == "basic"


# ---------------------------------------------------------------------------
# _write_dummy_mypy_config
# ---------------------------------------------------------------------------


class TestWriteDummyMypyConfig:
    def test_default_no_files_line(self, tmp_path: Path) -> None:
        path = _write_dummy_mypy_config(tmp_path)
        content = path.read_text()
        assert "[mypy]\n" in content
        assert "files" not in content
        assert "exclude" in content

    def test_check_paths_in_files(self, tmp_path: Path) -> None:
        path = _write_dummy_mypy_config(tmp_path, ["src", "lib"])
        content = path.read_text()
        assert "files = src, lib\n" in content

    def test_single_check_path(self, tmp_path: Path) -> None:
        path = _write_dummy_mypy_config(tmp_path, ["src"])
        content = path.read_text()
        assert "files = src\n" in content

    def test_returns_benchmark_ini_path(self, tmp_path: Path) -> None:
        path = _write_dummy_mypy_config(tmp_path)
        assert path.name == "mypy.benchmark.ini"

    def test_exclude_tests_dirs(self, tmp_path: Path) -> None:
        path = _write_dummy_mypy_config(tmp_path)
        content = path.read_text()
        assert "/tests/" in content
        assert "/test_" in content
        assert "/testing/" in content


# ---------------------------------------------------------------------------
# _write_dummy_ty_config
# ---------------------------------------------------------------------------


class TestWriteDummyTyConfig:
    def test_default_empty(self, tmp_path: Path) -> None:
        path = _write_dummy_ty_config(tmp_path)
        content = path.read_text()
        assert content == ""

    def test_check_paths_in_src_include(self, tmp_path: Path) -> None:
        path = _write_dummy_ty_config(tmp_path, ["src", "lib"])
        content = path.read_text()
        assert "[src]\n" in content
        assert 'include = ["src", "lib"]' in content

    def test_single_path(self, tmp_path: Path) -> None:
        path = _write_dummy_ty_config(tmp_path, ["src"])
        content = path.read_text()
        assert 'include = ["src"]' in content

    def test_returns_benchmark_toml_path(self, tmp_path: Path) -> None:
        path = _write_dummy_ty_config(tmp_path)
        assert path.name == "ty.benchmark.toml"


# ---------------------------------------------------------------------------
# _write_dummy_pyrefly_config
# ---------------------------------------------------------------------------


class TestWriteDummyPyreflyConfig:
    def test_default_empty(self, tmp_path: Path) -> None:
        path = _write_dummy_pyrefly_config(tmp_path)
        content = path.read_text()
        assert content == ""

    def test_check_paths_in_project_includes(self, tmp_path: Path) -> None:
        path = _write_dummy_pyrefly_config(tmp_path, ["src", "lib"])
        content = path.read_text()
        assert 'project_includes = ["src", "lib"]' in content

    def test_single_path(self, tmp_path: Path) -> None:
        path = _write_dummy_pyrefly_config(tmp_path, ["src"])
        content = path.read_text()
        assert 'project_includes = ["src"]' in content

    def test_returns_benchmark_toml_path(self, tmp_path: Path) -> None:
        path = _write_dummy_pyrefly_config(tmp_path)
        assert path.name == "pyrefly.benchmark.toml"


# ---------------------------------------------------------------------------
# _write_dummy_zuban_config
# ---------------------------------------------------------------------------


class TestWriteDummyZubanConfig:
    def test_default_no_files_line(self, tmp_path: Path) -> None:
        path = _write_dummy_zuban_config(tmp_path)
        content = path.read_text()
        assert "[mypy]\n" in content
        assert "files" not in content

    def test_check_paths_in_files(self, tmp_path: Path) -> None:
        path = _write_dummy_zuban_config(tmp_path, ["src", "lib"])
        content = path.read_text()
        assert "files = src, lib\n" in content

    def test_returns_benchmark_ini_path(self, tmp_path: Path) -> None:
        path = _write_dummy_zuban_config(tmp_path)
        assert path.name == "mypy.benchmark.ini"


# ---------------------------------------------------------------------------
# run_checker – command construction (mocked subprocess)
# ---------------------------------------------------------------------------


class TestRunCheckerCommands:
    """Verify run_checker builds the right CLI commands with paths in configs."""

    def _run_and_capture_cmd(
        self, checker: str, tmp_path: Path, check_paths: list[Path] | None = None,
    ) -> list[str]:
        """Run run_checker with mocked subprocess; return the command used."""
        captured: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> dict[str, object]:
            captured.append(cmd)
            return {
                "stdout": "",
                "stderr": "",
                "returncode": 0,
                "timed_out": False,
                "execution_time_s": 0.1,
                "peak_memory_mb": 10.0,
                "oom_killed": False,
            }

        with patch("typecheck_benchmark.daily_runner.run_process_with_timeout", side_effect=fake_run):
            run_checker(checker, tmp_path, check_paths, timeout=60)

        assert len(captured) == 1, f"Expected 1 subprocess call, got {len(captured)}"
        return captured[0]

    def test_pyright_no_path_args(self, tmp_path: Path) -> None:
        cmd = self._run_and_capture_cmd("pyright", tmp_path)
        assert cmd == ["pyright", "--outputjson"]

    def test_pyright_with_check_paths_no_path_args(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        cmd = self._run_and_capture_cmd("pyright", tmp_path, [src])
        # Paths should be in config, not in CLI args
        assert cmd == ["pyright", "--outputjson"]
        # Verify the config got the paths
        config = json.loads((tmp_path / "pyrightconfig.json").read_text())
        assert config["include"] == ["src"]

    def test_pyrefly_no_path_args(self, tmp_path: Path) -> None:
        cmd = self._run_and_capture_cmd("pyrefly", tmp_path)
        config_path = str(tmp_path / "pyrefly.benchmark.toml")
        assert cmd == ["pyrefly", "check", "--config", config_path]

    def test_pyrefly_with_check_paths_no_path_args(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        cmd = self._run_and_capture_cmd("pyrefly", tmp_path, [src])
        config_path = str(tmp_path / "pyrefly.benchmark.toml")
        assert cmd == ["pyrefly", "check", "--config", config_path]
        content = (tmp_path / "pyrefly.benchmark.toml").read_text()
        assert 'project_includes = ["src"]' in content

    def test_ty_no_path_args(self, tmp_path: Path) -> None:
        cmd = self._run_and_capture_cmd("ty", tmp_path)
        config_path = str(tmp_path / "ty.benchmark.toml")
        assert cmd == ["ty", "check", "--config-file", config_path]

    def test_ty_with_check_paths_no_path_args(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        cmd = self._run_and_capture_cmd("ty", tmp_path, [src])
        config_path = str(tmp_path / "ty.benchmark.toml")
        assert cmd == ["ty", "check", "--config-file", config_path]
        content = (tmp_path / "ty.benchmark.toml").read_text()
        assert 'include = ["src"]' in content

    def test_mypy_no_check_paths_passes_package_path(self, tmp_path: Path) -> None:
        cmd = self._run_and_capture_cmd("mypy", tmp_path)
        config_path = str(tmp_path / "mypy.benchmark.ini")
        assert cmd == [sys.executable, "-m", "mypy", "--no-incremental", "--config-file", config_path, str(tmp_path)]

    def test_mypy_with_check_paths_no_extra_args(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        cmd = self._run_and_capture_cmd("mypy", tmp_path, [src])
        config_path = str(tmp_path / "mypy.benchmark.ini")
        # Should NOT append path args — files= is in the config
        assert cmd == [sys.executable, "-m", "mypy", "--no-incremental", "--config-file", config_path]
        content = (tmp_path / "mypy.benchmark.ini").read_text()
        assert "files = src\n" in content

    def test_zuban_no_check_paths_passes_dot(self, tmp_path: Path) -> None:
        cmd = self._run_and_capture_cmd("zuban", tmp_path)
        # zuban ignores --config-file, so paths are always positional
        assert cmd == ["zuban", "check", "."]

    def test_zuban_with_check_paths_passes_positional(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        cmd = self._run_and_capture_cmd("zuban", tmp_path, [src])
        # zuban ignores --config-file, so check paths are positional args
        assert cmd == ["zuban", "check", "src"]

    def test_unknown_checker_returns_error(self, tmp_path: Path) -> None:
        with patch("typecheck_benchmark.daily_runner.run_process_with_timeout") as mock:
            result = run_checker("nonexistent", tmp_path, None, timeout=60)
        assert result["ok"] is False
        assert "Unknown checker" in (result.get("error_message") or "")
        mock.assert_not_called()
