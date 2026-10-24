"""Tests for timing precision in the typecheck benchmark.

Timings must come from the process exit, not from a polling interval.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from typecheck_benchmark.daily_runner import run_process_with_timeout


class TestProcessTiming:
    def test_fast_process_not_rounded_up_to_poll_interval(self, tmp_path: Path) -> None:
        # The old 100ms polling loop could never report less than 0.1s.
        result = run_process_with_timeout(
            [sys.executable, "-S", "-c", "pass"], cwd=tmp_path, timeout=30, capture_output=False,
        )
        assert result["returncode"] == 0
        assert 0 < result["execution_time_s"] < 0.1

    def test_timeout_still_enforced(self, tmp_path: Path) -> None:
        result = run_process_with_timeout(
            [sys.executable, "-S", "-c", "import time; time.sleep(30)"],
            cwd=tmp_path, timeout=1, capture_output=False,
        )
        assert result["timed_out"] is True
        assert 1 <= result["execution_time_s"] < 5
