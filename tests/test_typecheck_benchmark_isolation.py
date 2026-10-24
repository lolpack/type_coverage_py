"""Tests for per-package environments in the typecheck benchmark.

Each package must be benchmarked in its own virtual environment, with every
checker pointed at it explicitly, so that dependencies installed for one
package can't leak into another.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from typecheck_benchmark.daily_runner import (
    TEST_EXCLUDE_REGEX,
    _benchmark_package,
    create_package_venv,
    install_deps,
    run_checker,
    run_process_with_timeout,
    venv_python,
)


def _ok_result(**_: object) -> dict[str, object]:
    return {
        "stdout": "",
        "stderr": "",
        "returncode": 0,
        "timed_out": False,
        "execution_time_s": 0.1,
        "peak_memory_mb": 10.0,
        "oom_killed": False,
    }


# ---------------------------------------------------------------------------
# venv_python
# ---------------------------------------------------------------------------


class TestVenvPython:
    def test_posix_layout(self, tmp_path: Path) -> None:
        with patch.object(sys, "platform", "linux"):
            assert venv_python(tmp_path) == tmp_path / "bin" / "python"

    def test_windows_layout(self, tmp_path: Path) -> None:
        with patch.object(sys, "platform", "win32"):
            assert venv_python(tmp_path) == tmp_path / "Scripts" / "python.exe"


# ---------------------------------------------------------------------------
# run_checker – environment selection
# ---------------------------------------------------------------------------


class TestRunCheckerVenv:
    """Every checker must be told which environment to resolve imports from."""

    def _run(self, checker: str, tmp_path: Path, venv: Path | None) -> tuple[list[str], dict[str, Any]]:
        captured: list[tuple[list[str], dict[str, Any]]] = []

        def fake_run(cmd: list[str], **kwargs: Any) -> dict[str, object]:
            captured.append((cmd, kwargs))
            return _ok_result()

        with patch("typecheck_benchmark.daily_runner.run_process_with_timeout", side_effect=fake_run):
            run_checker(checker, tmp_path, None, timeout=60, venv=venv)

        assert len(captured) == 1
        return captured[0]

    @pytest.mark.parametrize(
        ("checker", "flag"),
        [
            ("pyright", "--pythonpath"),
            ("pyrefly", "--python-interpreter-path"),
            ("mypy", "--python-executable"),
            ("zuban", "--python-executable"),
        ],
    )
    def test_interpreter_flag(self, checker: str, flag: str, tmp_path: Path) -> None:
        venv = tmp_path / "venv"
        cmd, _ = self._run(checker, tmp_path, venv)
        idx = cmd.index(flag)
        assert cmd[idx + 1] == str(venv_python(venv))

    def test_ty_gets_environment_dir(self, tmp_path: Path) -> None:
        venv = tmp_path / "venv"
        cmd, _ = self._run("ty", tmp_path, venv)
        idx = cmd.index("--python")
        assert cmd[idx + 1] == str(venv)

    def test_zuban_flag_precedes_paths(self, tmp_path: Path) -> None:
        venv = tmp_path / "venv"
        cmd, _ = self._run("zuban", tmp_path, venv)
        assert cmd == [
            "zuban", "check", "--exclude", TEST_EXCLUDE_REGEX,
            "--python-executable", str(venv_python(venv)), ".",
        ]

    @pytest.mark.parametrize("checker", ["pyright", "pyrefly", "ty", "mypy", "zuban"])
    def test_virtual_env_set(self, checker: str, tmp_path: Path) -> None:
        venv = tmp_path / "venv"
        _, kwargs = self._run(checker, tmp_path, venv)
        assert kwargs["env"]["VIRTUAL_ENV"] == str(venv)

    @pytest.mark.parametrize("checker", ["pyright", "pyrefly", "ty", "mypy", "zuban"])
    def test_no_venv_leaves_command_and_env_alone(self, checker: str, tmp_path: Path) -> None:
        cmd, kwargs = self._run(checker, tmp_path, None)
        assert not any(arg in cmd for arg in ("--pythonpath", "--python-interpreter-path", "--python-executable", "--python"))
        assert kwargs["env"] is None


# ---------------------------------------------------------------------------
# _benchmark_package – one environment per package
# ---------------------------------------------------------------------------


class TestBenchmarkPackageVenv:
    def _pkg(self) -> dict[str, Any]:
        return {"name": "demo", "github_url": "https://github.com/x/demo", "install": True}

    def test_installs_and_checks_in_package_venv(self, tmp_path: Path) -> None:
        checkout = tmp_path / "demo"
        checkout.mkdir()
        installs: list[Path | str] = []
        checker_venvs: list[Path | None] = []

        def fake_create(venv_dir: Path) -> Path:
            venv_dir.mkdir()
            return venv_dir

        def fake_install(_package_path: Path, _env_config: dict[str, Any], python: Path | str) -> bool:
            installs.append(python)
            return True

        def fake_run_checker(*args: Any, **kwargs: Any) -> dict[str, object]:
            checker_venvs.append(kwargs.get("venv"))
            return {"ok": True, "execution_time_s": 0.123, "peak_memory_mb": 1.0}

        with (
            patch("typecheck_benchmark.daily_runner.clone_package", return_value=checkout),
            patch("typecheck_benchmark.daily_runner.create_package_venv", side_effect=fake_create),
            patch("typecheck_benchmark.daily_runner.install_deps", side_effect=fake_install),
            patch("typecheck_benchmark.daily_runner.is_type_checker_available", return_value=True),
            patch("typecheck_benchmark.daily_runner.run_checker", side_effect=fake_run_checker),
        ):
            result = _benchmark_package(self._pkg(), tmp_path, ["ty", "mypy"], timeout=60)

        venv = tmp_path / "demo-venv"
        assert installs == [venv_python(venv)]
        assert checker_venvs and all(v == venv for v in checker_venvs)
        assert result["metrics"]["ty"]["execution_time_s"] == 0.123
        # Both the checkout and its environment are discarded afterwards
        assert not venv.exists()
        assert not checkout.exists()

    def test_venv_failure_reports_error(self, tmp_path: Path) -> None:
        checkout = tmp_path / "demo"
        checkout.mkdir()
        with (
            patch("typecheck_benchmark.daily_runner.clone_package", return_value=checkout),
            patch("typecheck_benchmark.daily_runner.create_package_venv", return_value=None),
            patch("typecheck_benchmark.daily_runner.install_deps") as install,
        ):
            result = _benchmark_package(self._pkg(), tmp_path, ["ty"], timeout=60)

        assert result["error"] == "Failed to create virtual environment"
        install.assert_not_called()
        assert not checkout.exists()


# ---------------------------------------------------------------------------
# run_process_with_timeout – child environment
# ---------------------------------------------------------------------------


class TestProcessEnv:
    def test_env_passed_to_child(self, tmp_path: Path) -> None:
        import os

        env = os.environ.copy()
        env["TC_BENCH_MARKER"] = "isolated"
        result = run_process_with_timeout(
            [sys.executable, "-S", "-c", "import os; print(os.environ['TC_BENCH_MARKER'])"],
            cwd=tmp_path, timeout=30, env=env,
        )
        assert result["stdout"].strip() == "isolated"


# ---------------------------------------------------------------------------
# install_deps / create_package_venv – installs target the package venv
# ---------------------------------------------------------------------------


class TestInstallIntoVenv:
    def _capture(self, python: Path | str, tmp_path: Path) -> list[list[str]]:
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **_: Any) -> Any:
            calls.append(cmd)
            return type("R", (), {"returncode": 0, "stderr": ""})()

        with patch("typecheck_benchmark.daily_runner.subprocess.run", side_effect=fake_run):
            assert install_deps(tmp_path, {"install": True, "deps": ["numpy"]}, python)
        return calls

    def test_venv_installs_use_runner_pip_with_python_flag(self, tmp_path: Path) -> None:
        target = tmp_path / "venv" / "bin" / "python"
        calls = self._capture(target, tmp_path)
        prefix = [sys.executable, "-m", "pip", "--python", str(target), "install"]
        assert calls == [prefix + ["-e", "."], prefix + ["numpy"]]

    def test_default_installs_into_runner_env(self, tmp_path: Path) -> None:
        calls = self._capture(sys.executable, tmp_path)
        assert calls == [
            [sys.executable, "-m", "pip", "install", "-e", "."],
            [sys.executable, "-m", "pip", "install", "numpy"],
        ]

    def test_venv_created_without_pip(self, tmp_path: Path) -> None:
        with patch("typecheck_benchmark.daily_runner.subprocess.run") as run:
            run.return_value.returncode = 0
            assert create_package_venv(tmp_path / "v") == tmp_path / "v"
        cmd = run.call_args.args[0]
        assert cmd == [sys.executable, "-m", "venv", "--without-pip", str(tmp_path / "v")]

    def test_real_venv_isolated_from_runner_site_packages(self, tmp_path: Path) -> None:
        import subprocess

        venv = create_package_venv(tmp_path / "v")
        assert venv is not None
        # pytest is installed in the runner's environment but must not be
        # importable from the package venv.
        r = subprocess.run([str(venv_python(venv)), "-c", "import pytest"], capture_output=True)
        assert r.returncode != 0
