"""Tests for the backfill_ok_rate script."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Import the module under test
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from lsp.benchmark.backfill_ok_rate import (
    backfill_file,
    calculate_ok_rate_from_results,
)


class TestCalculateOkRateFromResults:
    """Tests for calculate_ok_rate_from_results function."""

    def test_calculate_with_all_successful(self) -> None:
        """Test calculating ok_rate when all requests succeed."""
        results: list[dict[str, Any]] = [
            {
                "package_name": "pkg1",
                "error": None,
                "metrics": {
                    "pyright": {
                        "ok": True,
                        "runs": 10,
                        "ok_count": 10,
                    }
                },
            },
        ]

        ok_rates = calculate_ok_rate_from_results(results, ["pyright"])

        assert ok_rates["pyright"] == 100.0

    def test_calculate_with_some_timeouts(self) -> None:
        """Test calculating ok_rate when some requests timeout."""
        results: list[dict[str, Any]] = [
            {
                "package_name": "pkg1",
                "error": None,
                "metrics": {
                    "pyright": {
                        "ok": True,
                        "runs": 10,
                        "ok_count": 8,  # 2 timeouts
                    }
                },
            },
        ]

        ok_rates = calculate_ok_rate_from_results(results, ["pyright"])

        assert ok_rates["pyright"] == 80.0

    def test_calculate_with_multiple_packages(self) -> None:
        """Test calculating ok_rate across multiple packages."""
        results: list[dict[str, Any]] = [
            {
                "package_name": "pkg1",
                "error": None,
                "metrics": {
                    "pyright": {
                        "ok": True,
                        "runs": 10,
                        "ok_count": 10,
                    }
                },
            },
            {
                "package_name": "pkg2",
                "error": None,
                "metrics": {
                    "pyright": {
                        "ok": True,
                        "runs": 10,
                        "ok_count": 6,  # 4 timeouts
                    }
                },
            },
        ]

        ok_rates = calculate_ok_rate_from_results(results, ["pyright"])

        # Total: 16 ok out of 20 runs = 80%
        assert ok_rates["pyright"] == 80.0

    def test_calculate_with_multiple_checkers(self) -> None:
        """Test calculating ok_rate for multiple type checkers."""
        results: list[dict[str, Any]] = [
            {
                "package_name": "pkg1",
                "error": None,
                "metrics": {
                    "pyright": {
                        "ok": True,
                        "runs": 10,
                        "ok_count": 10,
                    },
                    "pyrefly": {
                        "ok": True,
                        "runs": 10,
                        "ok_count": 9,
                    },
                },
            },
        ]

        ok_rates = calculate_ok_rate_from_results(
            results, ["pyright", "pyrefly"]
        )

        assert ok_rates["pyright"] == 100.0
        assert ok_rates["pyrefly"] == 90.0

    def test_calculate_with_package_errors(self) -> None:
        """Test that packages with errors are excluded."""
        results: list[dict[str, Any]] = [
            {
                "package_name": "pkg1",
                "error": "Failed to clone",
                "metrics": {},
            },
            {
                "package_name": "pkg2",
                "error": None,
                "metrics": {
                    "pyright": {
                        "ok": True,
                        "runs": 10,
                        "ok_count": 10,
                    }
                },
            },
        ]

        ok_rates = calculate_ok_rate_from_results(results, ["pyright"])

        # Only pkg2 should be counted
        assert ok_rates["pyright"] == 100.0

    def test_calculate_with_checker_not_ok(self) -> None:
        """Test that metrics with ok=False are excluded."""
        results: list[dict[str, Any]] = [
            {
                "package_name": "pkg1",
                "error": None,
                "metrics": {
                    "pyright": {
                        "ok": False,
                        "runs": 10,
                        "ok_count": 0,
                    }
                },
            },
            {
                "package_name": "pkg2",
                "error": None,
                "metrics": {
                    "pyright": {
                        "ok": True,
                        "runs": 10,
                        "ok_count": 10,
                    }
                },
            },
        ]

        ok_rates = calculate_ok_rate_from_results(results, ["pyright"])

        # Only pkg2 should be counted
        assert ok_rates["pyright"] == 100.0

    def test_calculate_with_no_results(self) -> None:
        """Test calculating ok_rate with no results."""
        ok_rates = calculate_ok_rate_from_results([], ["pyright"])

        assert ok_rates["pyright"] == 0.0


class TestBackfillFile:
    """Tests for backfill_file function."""

    def test_backfill_adds_ok_rate(self, tmp_path: Path) -> None:
        """Test that backfill adds ok_rate to aggregate stats."""
        test_file = tmp_path / "benchmark.json"
        data = {
            "type_checkers": ["pyright"],
            "aggregate": {
                "pyright": {
                    "packages_tested": 1,
                    "total_runs": 10,
                    "success_rate": 90.0,
                }
            },
            "results": [
                {
                    "package_name": "pkg1",
                    "error": None,
                    "metrics": {
                        "pyright": {
                            "ok": True,
                            "runs": 10,
                            "ok_count": 10,
                        }
                    },
                }
            ],
        }

        test_file.write_text(json.dumps(data))

        result = backfill_file(test_file)

        assert result is True

        # Verify file was updated
        updated_data = json.loads(test_file.read_text())
        assert "ok_rate" in updated_data["aggregate"]["pyright"]
        assert updated_data["aggregate"]["pyright"]["ok_rate"] == 100.0

    def test_backfill_skips_if_already_has_ok_rate(
        self, tmp_path: Path
    ) -> None:
        """Test that backfill skips files that already have ok_rate."""
        test_file = tmp_path / "benchmark.json"
        data = {
            "type_checkers": ["pyright"],
            "aggregate": {
                "pyright": {
                    "packages_tested": 1,
                    "total_runs": 10,
                    "ok_rate": 95.0,  # Already has ok_rate
                    "success_rate": 90.0,
                }
            },
            "results": [],
        }

        test_file.write_text(json.dumps(data))

        result = backfill_file(test_file)

        assert result is False  # Should return False (not updated)

        # Verify file wasn't modified
        updated_data = json.loads(test_file.read_text())
        assert updated_data["aggregate"]["pyright"]["ok_rate"] == 95.0

    def test_backfill_multiple_checkers(self, tmp_path: Path) -> None:
        """Test backfilling ok_rate for multiple type checkers."""
        test_file = tmp_path / "benchmark.json"
        data = {
            "type_checkers": ["pyright", "pyrefly"],
            "aggregate": {
                "pyright": {"packages_tested": 1},
                "pyrefly": {"packages_tested": 1},
            },
            "results": [
                {
                    "package_name": "pkg1",
                    "error": None,
                    "metrics": {
                        "pyright": {
                            "ok": True,
                            "runs": 10,
                            "ok_count": 10,
                        },
                        "pyrefly": {
                            "ok": True,
                            "runs": 10,
                            "ok_count": 9,
                        },
                    },
                }
            ],
        }

        test_file.write_text(json.dumps(data))

        result = backfill_file(test_file)

        assert result is True

        updated_data = json.loads(test_file.read_text())
        assert updated_data["aggregate"]["pyright"]["ok_rate"] == 100.0
        assert updated_data["aggregate"]["pyrefly"]["ok_rate"] == 90.0

    def test_backfill_preserves_existing_fields(self, tmp_path: Path) -> None:
        """Test that backfill preserves all existing fields."""
        test_file = tmp_path / "benchmark.json"
        data = {
            "timestamp": "2025-01-01T00:00:00Z",
            "type_checkers": ["pyright"],
            "aggregate": {
                "pyright": {
                    "packages_tested": 1,
                    "total_runs": 10,
                    "total_valid": 9,
                    "avg_latency_ms": 123.4,
                    "success_rate": 90.0,
                }
            },
            "results": [
                {
                    "package_name": "pkg1",
                    "error": None,
                    "metrics": {
                        "pyright": {
                            "ok": True,
                            "runs": 10,
                            "ok_count": 10,
                        }
                    },
                }
            ],
        }

        original_json = json.dumps(data)
        test_file.write_text(original_json)

        backfill_file(test_file)

        updated_data = json.loads(test_file.read_text())

        # Verify all original fields are preserved
        assert updated_data["timestamp"] == "2025-01-01T00:00:00Z"
        assert updated_data["aggregate"]["pyright"]["packages_tested"] == 1
        assert updated_data["aggregate"]["pyright"]["total_runs"] == 10
        assert updated_data["aggregate"]["pyright"]["total_valid"] == 9
        assert updated_data["aggregate"]["pyright"]["avg_latency_ms"] == 123.4
        assert updated_data["aggregate"]["pyright"]["success_rate"] == 90.0
        # And ok_rate was added
        assert "ok_rate" in updated_data["aggregate"]["pyright"]

    def test_backfill_handles_invalid_json(self, tmp_path: Path) -> None:
        """Test that backfill handles invalid JSON gracefully."""
        test_file = tmp_path / "invalid.json"
        test_file.write_text("not valid json {")

        result = backfill_file(test_file)

        assert result is False  # Should return False on error
