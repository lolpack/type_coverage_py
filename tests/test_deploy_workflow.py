"""Deployment ownership checks.

Site publication and benchmark result publication write to the same branch.
They must not write each other's files: `main` carries only a sparse subset of
benchmark results, so a site deploy that copies them could replace a newer
published result with an older one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
DEPLOY = WORKFLOWS / "deploy.yml"


@pytest.fixture(scope="module")
def deploy_text() -> str:
    return DEPLOY.read_text(encoding="utf-8")


class TestSiteDeployOwnsAssetsOnly:
    def test_deploy_workflow_exists(self) -> None:
        assert DEPLOY.is_file()

    def test_does_not_copy_benchmark_results(self, deploy_text: str) -> None:
        for pattern in (
            "lsp/benchmark/results/",
            "typecheck_benchmark/results/",
        ):
            assert pattern not in deploy_text, (
                f"site deployment must not write {pattern}; "
                "the benchmark workflows own their results"
            )

    def test_publishes_both_benchmark_pages(self, deploy_text: str) -> None:
        for asset in (
            "lsp/benchmark/index.html",
            "lsp/benchmark/scripts/lsp-benchmark.js",
            "lsp/benchmark/styles/lsp-benchmark.css",
            "typecheck_benchmark/index.html",
            "typecheck_benchmark/scripts/typecheck-benchmark.js",
            "typecheck_benchmark/styles/typecheck-benchmark.css",
        ):
            assert asset in deploy_text, f"{asset} must still be published"

    def test_publishes_the_homepage(self, deploy_text: str) -> None:
        assert "cp index.html /tmp/deploy/" in deploy_text

    def test_does_not_run_retired_coverage_commands(self, deploy_text: str) -> None:
        for needle in ("main.py", "--create-daily", "--archive-prioritized"):
            assert needle not in deploy_text


class TestBenchmarkWorkflowsOwnTheirResults:
    @pytest.mark.parametrize(
        ("workflow", "own", "other"),
        [
            ("lsp-benchmark.yml", "lsp/benchmark/results", "typecheck_benchmark/results"),
            (
                "typecheck-benchmark.yml",
                "typecheck_benchmark/results",
                "lsp/benchmark/results",
            ),
        ],
    )
    def test_each_benchmark_writes_only_its_own_results(
        self, workflow: str, own: str, other: str
    ) -> None:
        text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
        assert own in text, f"{workflow} should publish {own}"
        assert other not in text, f"{workflow} must not write {other}"

    @pytest.mark.parametrize(
        "workflow", ["lsp-benchmark.yml", "typecheck-benchmark.yml"]
    )
    def test_benchmarks_do_not_publish_the_homepage(self, workflow: str) -> None:
        text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
        assert "cp index.html" not in text, (
            f"{workflow} must not republish the homepage; a late benchmark run "
            "would revert a newer site deployment"
        )
