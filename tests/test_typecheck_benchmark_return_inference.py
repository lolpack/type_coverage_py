"""Tests for timing checkers with and without return type inference.

Checkers whose return type inference is configurable also run with the
opposite of their default setting. Those runs land in ``alternate_metrics``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from typecheck_benchmark.daily_runner import (
    DEFAULT_TYPE_CHECKERS,
    INFERS_RETURN_TYPES_BY_DEFAULT,
    RETURN_TYPE_INFERENCE_CONFIGURABLE,
    _benchmark_local_dir,
    _run_local_benchmark,
    _write_dummy_pyrefly_config,
    _write_dummy_ty_config,
    _write_dummy_zuban_config,
    parse_args,
    run_checker,
)

FAKE_RUN: dict[str, object] = {
    "stdout": "", "stderr": "", "returncode": 0, "timed_out": False,
    "execution_time_s": 1.0, "peak_memory_mb": 50.0, "oom_killed": False,
}


class TestTables:
    def test_every_default_checker_has_a_default(self) -> None:
        assert set(INFERS_RETURN_TYPES_BY_DEFAULT) == set(DEFAULT_TYPE_CHECKERS)

    def test_configurable_checkers(self) -> None:
        assert RETURN_TYPE_INFERENCE_CONFIGURABLE == {"pyrefly", "ty", "zuban"}


class TestConfigs:
    def test_default_configs_leave_inference_unset(self, tmp_path: Path) -> None:
        assert "infer-return-types" not in _write_dummy_pyrefly_config(tmp_path, ["src"]).read_text()
        assert "return-type-inference" not in _write_dummy_ty_config(tmp_path, ["src"]).read_text()
        assert "untyped_function_return_mode" not in _write_dummy_zuban_config(tmp_path, ["src"]).read_text()

    @pytest.mark.parametrize(("infer", "mode"), [(True, "checked"), (False, "never")])
    def test_pyrefly(self, tmp_path: Path, infer: bool, mode: str) -> None:
        content = _write_dummy_pyrefly_config(tmp_path, ["src"], infer).read_text()
        assert content == f'project_includes = ["src"]\ninfer-return-types = "{mode}"\n'

    @pytest.mark.parametrize(("infer", "mode"), [(True, "always"), (False, "never")])
    def test_ty(self, tmp_path: Path, infer: bool, mode: str) -> None:
        content = _write_dummy_ty_config(tmp_path, ["src"], infer).read_text()
        assert content == f'[src]\ninclude = ["src"]\n[analysis]\nreturn-type-inference = "{mode}"\n'

    @pytest.mark.parametrize(("infer", "mode"), [(True, "inferred"), (False, "any")])
    def test_zuban(self, tmp_path: Path, infer: bool, mode: str) -> None:
        content = _write_dummy_zuban_config(tmp_path, ["src"], infer).read_text()
        assert content.endswith(f"check_untyped_defs = True\nuntyped_function_return_mode = {mode}\n")

    @pytest.mark.parametrize("checker", ["pyright", "mypy"])
    def test_unconfigurable_checker_rejects_setting(self, tmp_path: Path, checker: str) -> None:
        with patch("typecheck_benchmark.daily_runner.run_process_with_timeout") as mock:
            with pytest.raises(AssertionError):
                run_checker(checker, tmp_path, None, timeout=60, infer_return_types=False)
        mock.assert_not_called()


@patch("typecheck_benchmark.daily_runner.is_type_checker_available", return_value=True)
@patch("typecheck_benchmark.daily_runner.run_process_with_timeout", return_value=FAKE_RUN)
class TestBenchmarkLocalDir:
    def test_alternate_runs_only_configurable_checkers(
        self, mock_run: object, mock_avail: object, tmp_path: Path,
    ) -> None:
        result = _benchmark_local_dir(tmp_path, DEFAULT_TYPE_CHECKERS, timeout=60)
        assert set(result["metrics"]) == set(DEFAULT_TYPE_CHECKERS)
        assert set(result["alternate_metrics"]) == {"pyrefly", "ty", "zuban"}
        assert all(m["ok"] for m in result["alternate_metrics"].values())

    def test_alternate_run_flips_the_default(
        self, mock_run: object, mock_avail: object, tmp_path: Path,
    ) -> None:
        configs: list[str] = []

        def record(cmd: list[str], **kwargs: object) -> dict[str, object]:
            configs.append((tmp_path / "ty.benchmark.toml").read_text())
            return FAKE_RUN

        mock_run.side_effect = record  # type: ignore[attr-defined]
        _benchmark_local_dir(tmp_path, ["ty"], timeout=60)
        # A warmup and a measured run of the default configuration, then of the alternate.
        alternate = '[analysis]\nreturn-type-inference = "always"\n'
        assert configs == ["", "", alternate, alternate]

    def test_no_alternate_inference(
        self, mock_run: object, mock_avail: object, tmp_path: Path,
    ) -> None:
        result = _benchmark_local_dir(
            tmp_path, DEFAULT_TYPE_CHECKERS, timeout=60, alternate_inference=False,
        )
        assert result["alternate_metrics"] == {}

    def test_output_records_defaults_and_alternate_aggregate(
        self, mock_run: object, mock_avail: object, tmp_path: Path,
    ) -> None:
        local_dir = tmp_path / "project"
        local_dir.mkdir()
        (tmp_path / "out").mkdir()
        with patch("typecheck_benchmark.daily_runner.get_type_checker_versions", return_value={}):
            path = _run_local_benchmark(
                local_dir, ["pyright", "pyrefly", "ty"], timeout=60,
                output_dir=tmp_path / "out", os_name=None, runs=1,
            )
        data = json.loads(path.read_text())
        assert data["return_type_inference_default"] == {"pyright": True, "pyrefly": True, "ty": False}
        assert set(data["alternate_aggregate"]) == {"pyrefly", "ty"}
        assert data["alternate_aggregate"]["ty"]["packages_tested"] == 1


class TestCli:
    def test_alternate_inference_on_by_default(self) -> None:
        assert parse_args([]).alternate_inference is True

    def test_no_alternate_inference_flag(self) -> None:
        assert parse_args(["--no-alternate-inference"]).alternate_inference is False
