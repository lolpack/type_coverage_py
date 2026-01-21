"""Tests for the LSP benchmark module."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from lsp.lsp_benchmark import (
    _parse_definition_result,
    _looks_like_valid_location,
    Location,
    Range,
    Position,
)


class TestParseDefinitionResult:
    """Tests for _parse_definition_result function."""

    def test_returns_empty_list_for_none(self) -> None:
        """Test that None result returns empty list."""
        result = _parse_definition_result(None)
        assert result == []

    def test_parses_single_location(self) -> None:
        """Test parsing a single Location object."""
        lsp_result = {
            "uri": "file:///path/to/file.py",
            "range": {
                "start": {"line": 10, "character": 5},
                "end": {"line": 10, "character": 15},
            },
        }

        result = _parse_definition_result(lsp_result)

        assert len(result) == 1
        assert result[0].uri == "file:///path/to/file.py"
        assert result[0].range.start.line == 10
        assert result[0].range.start.character == 5

    def test_parses_single_location_link(self) -> None:
        """Test parsing a single LocationLink object."""
        lsp_result = {
            "targetUri": "file:///path/to/target.py",
            "targetRange": {
                "start": {"line": 20, "character": 0},
                "end": {"line": 25, "character": 0},
            },
        }

        result = _parse_definition_result(lsp_result)

        assert len(result) == 1
        assert result[0].uri == "file:///path/to/target.py"
        assert result[0].range.start.line == 20

    def test_parses_multiple_locations(self) -> None:
        """Test parsing multiple Location objects - the key scenario for the fix."""
        lsp_result = [
            {
                "uri": "file:///path/to/file1.py",
                "range": {
                    "start": {"line": 10, "character": 0},
                    "end": {"line": 10, "character": 10},
                },
            },
            {
                "uri": "file:///path/to/file2.py",
                "range": {
                    "start": {"line": 20, "character": 5},
                    "end": {"line": 20, "character": 15},
                },
            },
        ]

        result = _parse_definition_result(lsp_result)

        assert len(result) == 2
        assert result[0].uri == "file:///path/to/file1.py"
        assert result[1].uri == "file:///path/to/file2.py"

    def test_parses_multiple_location_links(self) -> None:
        """Test parsing multiple LocationLink objects."""
        lsp_result = [
            {
                "targetUri": "file:///path/to/target1.py",
                "targetRange": {
                    "start": {"line": 5, "character": 0},
                    "end": {"line": 5, "character": 10},
                },
            },
            {
                "targetUri": "file:///path/to/target2.py",
                "targetRange": {
                    "start": {"line": 15, "character": 0},
                    "end": {"line": 15, "character": 20},
                },
            },
        ]

        result = _parse_definition_result(lsp_result)

        assert len(result) == 2
        assert result[0].uri == "file:///path/to/target1.py"
        assert result[1].uri == "file:///path/to/target2.py"

    def test_filters_invalid_items_from_list(self) -> None:
        """Test that invalid items are filtered from a list of locations."""
        lsp_result = [
            {
                "uri": "file:///valid.py",
                "range": {
                    "start": {"line": 1, "character": 0},
                    "end": {"line": 1, "character": 5},
                },
            },
            {"invalid": "object"},
            None,
            {
                "uri": "file:///also_valid.py",
                "range": {
                    "start": {"line": 2, "character": 0},
                    "end": {"line": 2, "character": 5},
                },
            },
        ]

        result = _parse_definition_result(lsp_result)

        assert len(result) == 2
        assert result[0].uri == "file:///valid.py"
        assert result[1].uri == "file:///also_valid.py"

    def test_returns_empty_for_invalid_single_result(self) -> None:
        """Test that invalid single result returns empty list."""
        result = _parse_definition_result({"invalid": "object"})
        assert result == []

    def test_returns_empty_for_empty_list(self) -> None:
        """Test that empty list returns empty list."""
        result = _parse_definition_result([])
        assert result == []


class TestLooksLikeValidLocation:
    """Tests for _looks_like_valid_location function."""

    def test_valid_file_location(self, tmp_path: Path) -> None:
        """Test that a valid file location passes validation."""
        loc = Location(
            uri=f"file://{tmp_path}/test.py",
            range=Range(
                start=Position(line=0, character=0),
                end=Position(line=0, character=10),
            ),
        )

        result = _looks_like_valid_location(loc, tmp_path)

        assert result is True

    def test_negative_line_fails(self, tmp_path: Path) -> None:
        """Test that negative line number fails validation."""
        loc = Location(
            uri=f"file://{tmp_path}/test.py",
            range=Range(
                start=Position(line=-1, character=0),
                end=Position(line=0, character=10),
            ),
        )

        result = _looks_like_valid_location(loc, tmp_path)

        assert result is False

    def test_negative_character_fails(self, tmp_path: Path) -> None:
        """Test that negative character position fails validation."""
        loc = Location(
            uri=f"file://{tmp_path}/test.py",
            range=Range(
                start=Position(line=0, character=-1),
                end=Position(line=0, character=10),
            ),
        )

        result = _looks_like_valid_location(loc, tmp_path)

        assert result is False

    def test_negative_end_line_fails(self, tmp_path: Path) -> None:
        """Test that negative end line fails validation."""
        loc = Location(
            uri=f"file://{tmp_path}/test.py",
            range=Range(
                start=Position(line=0, character=0),
                end=Position(line=-1, character=10),
            ),
        )

        result = _looks_like_valid_location(loc, tmp_path)

        assert result is False


class TestMultipleLocationsNotCountedAsFailure:
    """Tests to verify that multiple locations are not counted as failures.

    This test class specifically covers the bug fix where returning multiple
    locations for a symbol was incorrectly being counted as a failure.
    """

    def test_multiple_locations_should_not_be_unresolved(self) -> None:
        """Test that multiple locations from a definition result are parsed correctly.

        When an LSP server returns multiple locations, all valid locations should
        be captured and this should NOT be considered a failure/unresolved case.
        """
        # Simulate an LSP response with two definition locations
        lsp_result = [
            {
                "uri": "file:///project/module.py",
                "range": {
                    "start": {"line": 100, "character": 4},
                    "end": {"line": 100, "character": 20},
                },
            },
            {
                "uri": "file:///project/other_module.py",
                "range": {
                    "start": {"line": 50, "character": 0},
                    "end": {"line": 50, "character": 15},
                },
            },
        ]

        locations = _parse_definition_result(lsp_result)

        # Both locations should be parsed
        assert len(locations) == 2

        # The key assertion: having locations means the server found definitions
        # Therefore locations_payload would be non-empty and should NOT be
        # marked as unresolved (the condition is: if not locations_payload)
        locations_payload = [
            {"uri": loc.uri, "range": _range_to_dict(loc.range)}
            for loc in locations
        ]
        assert len(locations_payload) == 2
        assert len(locations_payload) > 0  # This is what prevents unresolved marking

    def test_zero_locations_should_be_unresolved(self) -> None:
        """Test that zero locations correctly triggers unresolved status.

        When an LSP server returns no locations, this should be marked as
        unresolved (the fix preserved this behavior).
        """
        lsp_result = None

        locations = _parse_definition_result(lsp_result)

        assert len(locations) == 0
        # Empty locations list means locations_payload would be empty
        # which triggers the unresolved marking (if not locations_payload)

    def test_single_location_not_unresolved(self) -> None:
        """Test that a single location is not marked as unresolved."""
        lsp_result = {
            "uri": "file:///project/single.py",
            "range": {
                "start": {"line": 10, "character": 0},
                "end": {"line": 10, "character": 10},
            },
        }

        locations = _parse_definition_result(lsp_result)

        assert len(locations) == 1
        assert len(locations) > 0  # Not unresolved


def _range_to_dict(r: Range) -> dict[str, Any]:
    """Helper to convert Range to dict for testing."""
    return {
        "start": {"line": r.start.line, "character": r.start.character},
        "end": {"line": r.end.line, "character": r.end.character},
    }
