"""Tests for timing precision in the typecheck benchmark.

Timings must come from the process exit, not from a polling interval.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from typecheck_benchmark.daily_runner import run_process_with_timeout


class TestProcessTiming:
    @pytest.mark.parametrize("elapsed_s", [0.025, 0.11])
    def test_process_duration_preserves_millisecond_precision(
        self, tmp_path: Path, elapsed_s: float,
    ) -> None:
        # Process startup and scheduling can exceed 100ms on a busy runner.
        # Control the clock to test precision independently of machine speed;
        # test_waits_without_timeout checks that waiting does not poll.
        with patch(
            "typecheck_benchmark.daily_runner.time.perf_counter",
            side_effect=[10.0, 10.0 + elapsed_s],
        ):
            result = run_process_with_timeout(
                [sys.executable, "-S", "-c", "pass"], cwd=tmp_path, timeout=30, capture_output=False,
            )
        assert result["returncode"] == 0
        assert result["execution_time_s"] == elapsed_s

    def test_timeout_still_enforced(self, tmp_path: Path) -> None:
        result = run_process_with_timeout(
            [sys.executable, "-S", "-c", "import time; time.sleep(30)"],
            cwd=tmp_path, timeout=1, capture_output=False,
        )
        assert result["timed_out"] is True
        assert 1 <= result["execution_time_s"] < 5

    def test_waits_without_timeout(self, tmp_path: Path) -> None:
        import subprocess

        real_popen = subprocess.Popen
        wait_calls: list[object] = []

        class RecordingPopen(real_popen):  # type: ignore[misc, valid-type]
            def wait(self, timeout: float | None = None) -> int:
                wait_calls.append(timeout)
                return super().wait(timeout)

        with patch("typecheck_benchmark.daily_runner.subprocess.Popen", RecordingPopen):
            run_process_with_timeout(
                [sys.executable, "-S", "-c", "pass"], cwd=tmp_path, timeout=30, capture_output=False,
            )
        # Popen.wait(timeout=...) polls with up to 50ms sleeps, which would
        # quantize timings. The measured wait must block with no timeout;
        # later cleanup waits don't matter.
        assert wait_calls and wait_calls[0] is None
