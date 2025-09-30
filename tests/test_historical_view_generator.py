import pytest
import os
import json
import tempfile
from datetime import datetime
from unittest.mock import patch, mock_open
from analyzer.historical_view_generator import (
    collect_historical_data,
    generate_html,
    generate_historical_graphs
)


class TestCollectHistoricalData:
    """Test class for collect_historical_data function."""

    def test_collect_historical_data_valid_files(self, tmp_path):
        """Test collecting historical data from valid JSON files."""
        # Create test data files
        test_data_1 = {
            "package1": {
                "DownloadRanking": 1,
                "CoverageData.parameter_coverage": 85.5,
                "CoverageData.return_type_coverage": 90.2,
                "CoverageData.parameter_coverage_with_stubs": 92.1,
                "CoverageData.return_type_coverage_with_stubs": 95.3,
                "pyright_stats": {"coverage": 88.7}
            },
            "package2": {
                "DownloadRanking": 2,
                "CoverageData.parameter_coverage": 75.2,
                "CoverageData.return_type_coverage": 80.1,
                "CoverageData.parameter_coverage_with_stubs": 82.4,
                "CoverageData.return_type_coverage_with_stubs": 87.9,
                "pyright_stats": {"coverage": 79.3}
            }
        }

        test_data_2 = {
            "package1": {
                "DownloadRanking": 1,
                "CoverageData.parameter_coverage": 87.1,
                "CoverageData.return_type_coverage": 91.5,
                "CoverageData.parameter_coverage_with_stubs": 93.8,
                "CoverageData.return_type_coverage_with_stubs": 96.2,
                "pyright_stats": {"coverage": 90.1}
            },
            "package3": {
                "DownloadRanking": 15,
                "CoverageData.parameter_coverage": 65.8,
                "CoverageData.return_type_coverage": 70.3,
                "CoverageData.parameter_coverage_with_stubs": 72.1,
                "CoverageData.return_type_coverage_with_stubs": 77.6,
                "pyright_stats": {"coverage": 68.9}
            }
        }

        # Write test files
        file1_path = tmp_path / "package_report-2023-01-01.json"
        file2_path = tmp_path / "package_report-2023-01-02.json"

        with open(file1_path, "w") as f:
            json.dump(test_data_1, f)

        with open(file2_path, "w") as f:
            json.dump(test_data_2, f)

        # Test the function
        result = collect_historical_data(str(tmp_path))

        # Verify results
        assert len(result) == 3  # package1, package2, package3
        assert "package1" in result
        assert "package2" in result
        assert "package3" in result

        # Check package1 data
        package1_data = result["package1"]
        assert len(package1_data) == 2
        assert package1_data[0]["date"] == "2023-01-01"
        assert package1_data[0]["DownloadRanking"] == 1
        assert package1_data[0]["pyright_coverage"] == 88.7
        assert package1_data[1]["date"] == "2023-01-02"
        assert package1_data[1]["pyright_coverage"] == 90.1

        # Check package2 data (only appears in first file)
        package2_data = result["package2"]
        assert len(package2_data) == 1
        assert package2_data[0]["date"] == "2023-01-01"
        assert package2_data[0]["DownloadRanking"] == 2

        # Check package3 data (only appears in second file)
        package3_data = result["package3"]
        assert len(package3_data) == 1
        assert package3_data[0]["date"] == "2023-01-02"
        assert package3_data[0]["DownloadRanking"] == 15

    def test_collect_historical_data_missing_pyright_stats(self, tmp_path):
        """Test handling of missing pyright_stats field."""
        test_data = {
            "package1": {
                "DownloadRanking": 1,
                "CoverageData.parameter_coverage": 85.5,
                # No pyright_stats field
            }
        }

        file_path = tmp_path / "package_report-2023-01-01.json"
        with open(file_path, "w") as f:
            json.dump(test_data, f)

        result = collect_historical_data(str(tmp_path))

        assert "package1" in result
        assert result["package1"][0]["pyright_coverage"] == 0.0

    def test_collect_historical_data_invalid_date_format(self, tmp_path, capsys):
        """Test handling of files with invalid date formats."""
        test_data = {"package1": {"DownloadRanking": 1}}

        # Create files with invalid date formats
        invalid_file = tmp_path / "package_report-invalid-date.json"
        valid_file = tmp_path / "package_report-2023-01-01.json"

        with open(invalid_file, "w") as f:
            json.dump(test_data, f)

        with open(valid_file, "w") as f:
            json.dump(test_data, f)

        result = collect_historical_data(str(tmp_path))

        # Should only include the valid file
        assert len(result) == 1
        assert "package1" in result
        assert len(result["package1"]) == 1
        assert result["package1"][0]["date"] == "2023-01-01"

        # Check that warning message was printed
        captured = capsys.readouterr()
        assert "Skipping file with invalid date format: package_report-invalid-date.json" in captured.out

    def test_collect_historical_data_empty_directory(self, tmp_path):
        """Test behavior with empty directory."""
        result = collect_historical_data(str(tmp_path))
        assert result == {}

    def test_collect_historical_data_no_json_files(self, tmp_path):
        """Test behavior with directory containing no JSON files."""
        # Create some non-JSON files
        (tmp_path / "not_json.txt").write_text("not json")
        (tmp_path / "another.py").write_text("python code")

        result = collect_historical_data(str(tmp_path))
        assert result == {}

    def test_collect_historical_data_malformed_json(self, tmp_path):
        """Test handling of malformed JSON files."""
        malformed_file = tmp_path / "package_report-2023-01-01.json"
        malformed_file.write_text("{ invalid json")

        with pytest.raises(json.JSONDecodeError):
            collect_historical_data(str(tmp_path))


class TestGenerateHtml:
    """Test class for generate_html function."""

    def test_generate_html_basic(self, tmp_path):
        """Test basic HTML generation."""
        historical_data = {
            "package1": [
                {
                    "date": "2023-01-01",
                    "DownloadRanking": 1,
                    "CoverageData.parameter_coverage": 85.5,
                    "CoverageData.return_type_coverage": 90.2,
                    "CoverageData.parameter_coverage_with_stubs": 92.1,
                    "CoverageData.return_type_coverage_with_stubs": 95.3,
                    "pyright_coverage": 88.7
                },
                {
                    "date": "2023-01-02",
                    "DownloadRanking": 1,
                    "CoverageData.parameter_coverage": 87.1,
                    "CoverageData.return_type_coverage": 91.5,
                    "CoverageData.parameter_coverage_with_stubs": 93.8,
                    "CoverageData.return_type_coverage_with_stubs": 96.2,
                    "pyright_coverage": 90.1
                }
            ]
        }

        output_file = tmp_path / "test_output.html"
        generate_html(historical_data, str(output_file))

        # Verify file was created and contains expected content
        assert output_file.exists()
        content = output_file.read_text()

        # Check for key HTML elements
        assert "<!DOCTYPE html>" in content
        assert "<title>Type Coverage Visualization</title>" in content
        assert "Type Coverage Historical Trends" in content
        assert "package1" in content
        assert "chart-package1" in content
        assert "2023-01-01" in content
        assert "2023-01-02" in content

    def test_generate_html_empty_data(self, tmp_path):
        """Test HTML generation with empty data."""
        historical_data = {}
        output_file = tmp_path / "empty_output.html"

        generate_html(historical_data, str(output_file))

        assert output_file.exists()
        content = output_file.read_text()
        assert "<!DOCTYPE html>" in content
        assert "Type Coverage Historical Trends" in content

    def test_generate_html_multiple_packages(self, tmp_path):
        """Test HTML generation with multiple packages."""
        historical_data = {
            "package1": [
                {
                    "date": "2023-01-01",
                    "DownloadRanking": 1,
                    "CoverageData.parameter_coverage": 85.5,
                    "CoverageData.return_type_coverage": 90.2,
                    "CoverageData.parameter_coverage_with_stubs": 92.1,
                    "CoverageData.return_type_coverage_with_stubs": 95.3,
                    "pyright_coverage": 88.7
                }
            ],
            "package2": [
                {
                    "date": "2023-01-01",
                    "DownloadRanking": 5,
                    "CoverageData.parameter_coverage": 75.2,
                    "CoverageData.return_type_coverage": 80.1,
                    "CoverageData.parameter_coverage_with_stubs": 82.4,
                    "CoverageData.return_type_coverage_with_stubs": 87.9,
                    "pyright_coverage": 79.3
                }
            ]
        }

        output_file = tmp_path / "multi_package_output.html"
        generate_html(historical_data, str(output_file))

        content = output_file.read_text()
        assert "package1" in content
        assert "package2" in content
        assert "chart-package1" in content
        assert "chart-package2" in content

    @patch("builtins.print")
    def test_generate_html_print_confirmation(self, mock_print, tmp_path):
        """Test that success message is printed."""
        historical_data = {"package1": [{"date": "2023-01-01", "DownloadRanking": 1}]}
        output_file = tmp_path / "test_output.html"

        generate_html(historical_data, str(output_file))

        mock_print.assert_called_with("HTML generated successfully.")


class TestGenerateHistoricalGraphs:
    """Test class for generate_historical_graphs function."""

    def test_generate_historical_graphs_integration(self, tmp_path):
        """Test the complete integration of collect_historical_data and generate_html."""
        # Create test data
        test_data = {
            "package1": {
                "DownloadRanking": 1,
                "CoverageData.parameter_coverage": 85.5,
                "CoverageData.return_type_coverage": 90.2,
                "CoverageData.parameter_coverage_with_stubs": 92.1,
                "CoverageData.return_type_coverage_with_stubs": 95.3,
                "pyright_stats": {"coverage": 88.7}
            }
        }

        # Create data directory and file
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        data_file = data_dir / "package_report-2023-01-01.json"

        with open(data_file, "w") as f:
            json.dump(test_data, f)

        # Generate historical graphs
        output_file = tmp_path / "output.html"

        with patch("builtins.print") as mock_print:
            generate_historical_graphs(str(data_dir), str(output_file))

        # Verify output file was created
        assert output_file.exists()
        content = output_file.read_text()
        assert "package1" in content
        assert "Type Coverage Historical Trends" in content

        # Verify print statements were called
        assert mock_print.call_count == 2  # One from collect_historical_data, one from generate_html

    def test_generate_historical_graphs_with_empty_directory(self, tmp_path):
        """Test generate_historical_graphs with empty data directory."""
        data_dir = tmp_path / "empty_data"
        data_dir.mkdir()
        output_file = tmp_path / "output.html"

        generate_historical_graphs(str(data_dir), str(output_file))

        # Should still generate HTML file, even with no data
        assert output_file.exists()
        content = output_file.read_text()
        assert "Type Coverage Historical Trends" in content


class TestEdgeCases:
    """Test class for edge cases and error conditions."""

    def test_collect_historical_data_with_none_pyright_coverage(self, tmp_path):
        """Test handling when pyright_stats contains None coverage."""
        test_data = {
            "package1": {
                "DownloadRanking": 1,
                "pyright_stats": {"coverage": None}
            }
        }

        file_path = tmp_path / "package_report-2023-01-01.json"
        with open(file_path, "w") as f:
            json.dump(test_data, f)

        result = collect_historical_data(str(tmp_path))

        assert "package1" in result
        assert result["package1"][0]["pyright_coverage"] == 0.0

    def test_collect_historical_data_filters_pyright_stats_from_record(self, tmp_path):
        """Test that pyright_stats is filtered out from the record data."""
        test_data = {
            "package1": {
                "DownloadRanking": 1,
                "CoverageData.parameter_coverage": 85.5,
                "pyright_stats": {"coverage": 88.7, "other_field": "should_not_appear"}
            }
        }

        file_path = tmp_path / "package_report-2023-01-01.json"
        with open(file_path, "w") as f:
            json.dump(test_data, f)

        result = collect_historical_data(str(tmp_path))

        record = result["package1"][0]
        assert "pyright_stats" not in record
        assert "pyright_coverage" in record
        assert record["pyright_coverage"] == 88.7
        assert record["DownloadRanking"] == 1
        assert record["CoverageData.parameter_coverage"] == 85.5

    def test_collect_historical_data_sorts_files_by_name(self, tmp_path):
        """Test that files are processed in sorted order."""
        test_data_base = {"package1": {"DownloadRanking": 1}}

        # Create files in non-alphabetical order
        files = [
            "package_report-2023-01-03.json",
            "package_report-2023-01-01.json",
            "package_report-2023-01-02.json"
        ]

        for filename in files:
            file_path = tmp_path / filename
            with open(file_path, "w") as f:
                json.dump(test_data_base, f)

        result = collect_historical_data(str(tmp_path))

        # Verify dates are in sorted order
        dates = [record["date"] for record in result["package1"]]
        assert dates == ["2023-01-01", "2023-01-02", "2023-01-03"]

    @patch("builtins.print")
    def test_collect_historical_data_prints_summary(self, mock_print, tmp_path):
        """Test that summary message is printed with correct package count."""
        test_data = {
            "package1": {"DownloadRanking": 1},
            "package2": {"DownloadRanking": 2},
            "package3": {"DownloadRanking": 3}
        }

        file_path = tmp_path / "package_report-2023-01-01.json"
        with open(file_path, "w") as f:
            json.dump(test_data, f)

        collect_historical_data(str(tmp_path))

        mock_print.assert_called_with("Collected data for 3 packages.")