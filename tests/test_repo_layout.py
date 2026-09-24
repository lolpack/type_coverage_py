"""Guardrails for the retired coverage pipeline and the two live benchmarks.

Package type-coverage generation was retired; the LSP and type-checker timing
benchmarks were not. These tests make that boundary explicit so a future
change has to be deliberate about crossing it.

Everything here is deterministic (no network, no subprocesses, no cloned
projects), so it belongs in the fast required CI checks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

LSP_WORKFLOW = WORKFLOWS / "lsp-benchmark.yml"
TYPECHECK_WORKFLOW = WORKFLOWS / "typecheck-benchmark.yml"


def load_workflow(path: Path) -> dict[str, Any]:
    """Parse a workflow file, normalising the ``on`` key.

    PyYAML implements YAML 1.1, where a bare ``on`` key resolves to the
    boolean ``True``. Moving it back to the string key keeps the assertions
    below readable.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path} did not parse to a mapping"
    if True in data and "on" not in data:
        data["on"] = data.pop(True)
    return data


class TestCoverageGenerationIsRetired:
    """No scheduled or manual job may recompute package type coverage."""

    @pytest.mark.parametrize("name", ["main.yml", "prioritized.yaml"])
    def test_producer_workflow_is_gone(self, name: str) -> None:
        assert not (WORKFLOWS / name).exists(), f"{name} must stay deleted"

    @pytest.mark.parametrize(
        "relative",
        [
            "main.py",
            "analyzer",
            "coverage_sources",
            "badge.py",
            "regenerate_html_report.py",
            "stub_package_staleness_script.py",
        ],
    )
    def test_generator_code_is_gone(self, relative: str) -> None:
        assert not (REPO_ROOT / relative).exists(), f"{relative} was coverage-only"

    def test_no_workflow_invokes_a_coverage_entry_point(self) -> None:
        offenders: list[str] = []
        for workflow in sorted(WORKFLOWS.glob("*.y*ml")):
            text = workflow.read_text(encoding="utf-8")
            for needle in ("main.py", "--create-daily", "--archive-prioritized", "--pyright-stats"):
                if needle in text:
                    offenders.append(f"{workflow.name}: {needle}")
        assert not offenders, f"retired coverage commands still referenced: {offenders}"

    def test_no_workflow_clones_typeshed(self) -> None:
        """Typeshed was cloned only to compute coverage."""
        for workflow in sorted(WORKFLOWS.glob("*.y*ml")):
            assert "python/typeshed" not in workflow.read_text(encoding="utf-8"), workflow.name


class TestHistoricalDataIsLeftInPlace:
    """Retired does not mean deleted: the existing data stays where it is."""

    @pytest.mark.parametrize(
        "relative",
        [
            "package_report.json",
            "stats_as_csv.csv",
            "historical_data/json/dates.json",
            "prioritized/package_report.json",
            "prioritized/historical_data/json/dates.json",
        ],
    )
    def test_existing_data_file_still_present(self, relative: str) -> None:
        assert (REPO_ROOT / relative).is_file(), f"{relative} must be preserved in place"

    @pytest.mark.parametrize(
        "relative",
        ["historical_data/html", "prioritized/historical_data/html"],
    )
    def test_dated_report_snapshots_are_retained(self, relative: str) -> None:
        directory = REPO_ROOT / relative
        assert directory.is_dir()
        assert list(directory.glob("*.html")), f"{relative} should still hold dated reports"

    @pytest.mark.parametrize(
        "relative",
        ["historical_data/chart.min.js", "historical_data/graph.css"],
    )
    def test_snapshot_viewing_dependencies_are_retained(self, relative: str) -> None:
        """The dated HTML snapshots need these to render; keep them."""
        assert (REPO_ROOT / relative).is_file()


class TestBenchmarksStayHealthy:
    """Both performance benchmarks keep their schedules, inputs and routes."""

    def test_lsp_benchmark_runs_daily(self) -> None:
        triggers = load_workflow(LSP_WORKFLOW)["on"]
        assert [entry["cron"] for entry in triggers["schedule"]] == ["0 3 * * *"]

    def test_typecheck_benchmark_runs_daily(self) -> None:
        triggers = load_workflow(TYPECHECK_WORKFLOW)["on"]
        assert [entry["cron"] for entry in triggers["schedule"]] == ["0 5 * * *"]

    @pytest.mark.parametrize("path", [LSP_WORKFLOW, TYPECHECK_WORKFLOW])
    def test_manual_runs_with_inputs_are_supported(self, path: Path) -> None:
        dispatch = load_workflow(path)["on"]["workflow_dispatch"]
        assert isinstance(dispatch, dict) and dispatch.get("inputs")

    @pytest.mark.parametrize("path", [LSP_WORKFLOW, TYPECHECK_WORKFLOW])
    def test_still_ubuntu_only(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        assert "ubuntu-latest" in text
        assert "macos-latest" not in text and "windows-latest" not in text

    def test_lsp_checker_set_is_unchanged(self) -> None:
        text = LSP_WORKFLOW.read_text(encoding="utf-8")
        assert "--checkers pyright pyrefly ty zuban" in text

    def test_typecheck_checker_set_is_unchanged(self) -> None:
        text = TYPECHECK_WORKFLOW.read_text(encoding="utf-8")
        assert "--checkers pyright pyrefly ty mypy zuban" in text

    @pytest.mark.parametrize(
        "relative",
        [
            "lsp/benchmark/index.html",
            "lsp/benchmark/scripts/lsp-benchmark.ts",
            "lsp/benchmark/styles/lsp-benchmark.css",
            "typecheck_benchmark/index.html",
            "typecheck_benchmark/scripts/typecheck-benchmark.ts",
            "typecheck_benchmark/styles/typecheck-benchmark.css",
        ],
    )
    def test_canonical_route_asset_exists(self, relative: str) -> None:
        assert (REPO_ROOT / relative).is_file()

    def test_custom_domain_is_retained(self) -> None:
        assert (REPO_ROOT / "CNAME").read_text(encoding="utf-8").strip() == (
            "python-type-checking.com"
        )


class TestSharedCorpus:
    """``install_envs.json`` stays the single source of truth for both runners."""

    @pytest.fixture(scope="class")
    @staticmethod
    def corpus() -> dict[str, Any]:
        path = REPO_ROOT / "typecheck_benchmark" / "install_envs.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_corpus_is_non_empty(self, corpus: dict[str, Any]) -> None:
        assert corpus["packages"]

    def test_every_package_has_a_github_url(self, corpus: dict[str, Any]) -> None:
        for package in corpus["packages"]:
            assert package.get("github_url", "").startswith("https://github.com/")

    def test_check_paths_when_present_is_a_non_empty_list(self, corpus: dict[str, Any]) -> None:
        # ``check_paths`` is optional. A few entries (ComfyUI, for one) omit it
        # and let the runner fall back to the repository root. Characterise the
        # current behaviour rather than tightening it during the redesign.
        for package in corpus["packages"]:
            if "check_paths" in package:
                assert isinstance(package["check_paths"], list)
                assert package["check_paths"], f"{package['github_url']} has empty check_paths"

    def test_lsp_runner_reads_the_shared_corpus(self) -> None:
        source = (REPO_ROOT / "lsp" / "benchmark" / "daily_runner.py").read_text(encoding="utf-8")
        assert "install_envs.json" in source

    def test_selection_filter_is_install_or_deps(self, corpus: dict[str, Any]) -> None:
        from lsp.benchmark.daily_runner import load_packages_from_install_envs

        selected = load_packages_from_install_envs()
        expected = [
            package
            for package in corpus["packages"]
            if package.get("install") is True or bool(package.get("deps"))
        ]
        assert selected, "the shared corpus filter must select at least one package"
        assert len(selected) == len(expected)


class TestBenchmarkPagesDoNotDependOnCoverage:
    @pytest.mark.parametrize(
        "relative", ["lsp/benchmark/index.html", "typecheck_benchmark/index.html"]
    )
    def test_no_coverage_report_fetch(self, relative: str) -> None:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "package_report.json" not in text


class TestDependenciesMatchTheRemainingCode:
    """Coverage-only dependencies are gone; benchmark ones are not."""

    @pytest.fixture(scope="class")
    @staticmethod
    def requirements() -> str:
        return (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")

    @pytest.mark.parametrize("package", ["requests", "jinja2", "tabulate", "pyright"])
    def test_coverage_only_dependency_is_removed(self, requirements: str, package: str) -> None:
        lines = [
            line.strip()
            for line in requirements.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        assert not any(line.lower().startswith(package) for line in lines), (
            f"{package} was only used by the retired coverage pipeline"
        )

    @pytest.mark.parametrize("package", ["pytest", "pyrefly", "PyYAML"])
    def test_retained_dependency_is_present(self, requirements: str, package: str) -> None:
        assert package.lower() in requirements.lower()

    def test_npm_pyright_dependency_is_removed(self) -> None:
        # The benchmarks install pyright globally in their workflows
        # (`npm install -g pyright`); the local dependency existed only for
        # coverage_sources/get_pyright_stats.py.
        package_json = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
        assert "pyright" not in package_json.get("dependencies", {})
