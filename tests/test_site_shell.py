"""Checks for the shared design system and page shell.

The two dashboards and the homepage must look like one site and must all
resolve the same stylesheets once deployed. These tests are static: they read
the checked-in HTML and CSS rather than rendering a browser, so they stay fast
enough for the required CI checks.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS = REPO_ROOT / "assets" / "styles"
TOKENS = ASSETS / "tokens.css"
SITE_CSS = ASSETS / "site.css"

DASHBOARDS = {
    "lsp": REPO_ROOT / "lsp" / "benchmark" / "index.html",
    "typecheck": REPO_ROOT / "typecheck_benchmark" / "index.html",
}
DASHBOARD_CSS = {
    "lsp": REPO_ROOT / "lsp" / "benchmark" / "styles" / "lsp-benchmark.css",
    "typecheck": REPO_ROOT / "typecheck_benchmark" / "styles" / "typecheck-benchmark.css",
}

#: Every token the dashboards reference. Losing one silently degrades a chart
#: or a surface colour to the browser default.
REQUIRED_TOKENS = [
    "--color-bg",
    "--color-bg-secondary",
    "--color-bg-tertiary",
    "--color-border",
    "--color-text",
    "--color-text-muted",
    "--color-text-bright",
    "--color-accent",
    "--color-success",
    "--color-warning",
    "--color-error",
    "--color-pyright",
    "--color-pyrefly",
    "--color-ty",
    "--color-mypy",
    "--color-zuban",
    "--font-mono",
    "--font-sans",
    "--shadow-sm",
    "--shadow-md",
    "--shadow-lg",
    "--radius-sm",
    "--radius-md",
    "--radius-lg",
]

#: Chart series identity. These are the colours readers have been comparing in
#: every historical chart; the extraction must not have changed any of them.
CHECKER_COLORS = {
    "--color-pyright": "#3178c6",
    "--color-pyrefly": "#e74c3c",
    "--color-ty": "#9b59b6",
    "--color-mypy": "#2ecc71",
    "--color-zuban": "#f39c12",
}


@pytest.fixture(scope="module")
def tokens_css() -> str:
    return TOKENS.read_text(encoding="utf-8")


class TestSharedTokens:
    def test_tokens_file_exists(self) -> None:
        assert TOKENS.is_file()

    @pytest.mark.parametrize("token", REQUIRED_TOKENS)
    def test_token_is_defined(self, tokens_css: str, token: str) -> None:
        assert re.search(rf"^\s*{re.escape(token)}\s*:", tokens_css, re.M), token

    @pytest.mark.parametrize(("token", "value"), sorted(CHECKER_COLORS.items()))
    def test_checker_color_is_unchanged(self, tokens_css: str, token: str, value: str) -> None:
        match = re.search(rf"^\s*{re.escape(token)}\s*:\s*([^;]+);", tokens_css, re.M)
        assert match, token
        assert match.group(1).strip().lower() == value

    @pytest.mark.parametrize("name", sorted(DASHBOARD_CSS))
    def test_dashboard_css_no_longer_redefines_tokens(self, name: str) -> None:
        text = DASHBOARD_CSS[name].read_text(encoding="utf-8")
        assert ":root" not in text, (
            f"{name} dashboard still defines its own tokens; they must come from tokens.css"
        )

    @pytest.mark.parametrize("name", sorted(DASHBOARD_CSS))
    def test_dashboard_css_still_consumes_tokens(self, name: str) -> None:
        text = DASHBOARD_CSS[name].read_text(encoding="utf-8")
        assert "var(--color-bg)" in text


class TestSharedShellStylesheet:
    def test_site_css_exists(self) -> None:
        assert SITE_CSS.is_file()

    def test_site_css_does_not_ship_a_second_global_reset(self) -> None:
        """A second `* { }` reset could change dashboard chart rendering."""
        text = SITE_CSS.read_text(encoding="utf-8")
        assert not re.search(r"^\s*\*\s*\{", text, re.M)

    def test_site_css_does_not_style_charts_or_tables(self) -> None:
        text = SITE_CSS.read_text(encoding="utf-8")
        for selector in (".chart-card", ".results-table", "canvas", ".summary-grid"):
            assert selector not in text, f"{selector} belongs to a dashboard stylesheet"

    def test_reduced_motion_is_respected(self) -> None:
        assert "prefers-reduced-motion" in SITE_CSS.read_text(encoding="utf-8")

    def test_only_the_homepage_header_is_sticky(self) -> None:
        """The dashboards already have a sticky .nav-bar at top: 0."""
        text = SITE_CSS.read_text(encoding="utf-8")
        assert ".site-header--sticky" in text
        header_block = text.split(".site-header--sticky")[0].split(".site-header {")[1]
        assert "position: sticky" not in header_block


class TestDashboardPagesUseTheSharedShell:
    @pytest.fixture(params=sorted(DASHBOARDS), ids=sorted(DASHBOARDS))
    def page(self, request: pytest.FixtureRequest) -> str:
        return DASHBOARDS[request.param].read_text(encoding="utf-8")

    def test_links_shared_stylesheets_before_its_own(self, page: str) -> None:
        tokens = page.index('href="/assets/styles/tokens.css"')
        site = page.index('href="/assets/styles/site.css"')
        own = page.index('href="styles/')
        assert tokens < site < own, "cascade order must let the dashboard sheet win"

    def test_has_the_shared_header_and_brand(self, page: str) -> None:
        assert 'class="site-header"' in page
        assert ">Python Type Checking</a>" in page

    def test_has_a_skip_link_targeting_main(self, page: str) -> None:
        assert 'class="skip-link" href="#main"' in page
        assert 'id="main"' in page

    def test_has_exactly_one_main_landmark(self, page: str) -> None:
        assert page.count("<main") == 1
        assert page.count("</main>") == 1

    def test_has_exactly_one_h1(self, page: str) -> None:
        assert len(re.findall(r"<h1[\s>]", page)) == 1

    def test_uses_the_shared_footer(self, page: str) -> None:
        assert 'class="site-footer"' in page
        assert 'class="footer"' not in page

    def test_homepage_anchors_are_root_relative(self, page: str) -> None:
        """On a deep page, `#history` would target the current page."""
        for anchor in ("history", "surveys", "benchmarks", "contribute"):
            assert f'href="/#{anchor}"' in page, anchor

    def test_no_back_to_type_coverage_wording_remains(self, page: str) -> None:
        assert "Back to Type Coverage" not in page
        assert "Python Type Coverage" not in page

    def test_declares_a_canonical_url_and_description(self, page: str) -> None:
        assert 'rel="canonical"' in page
        assert 'name="description"' in page

    def test_title_is_scoped_to_the_site(self, page: str) -> None:
        title = re.search(r"<title>(.*?)</title>", page)
        assert title and title.group(1).endswith("| Python Type Checking")


class TestSharedAssetsArePublished:
    """A page that links an asset the deploy never copies is a broken page."""

    @pytest.fixture(scope="class")
    @staticmethod
    def deploy_text() -> str:
        return (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    @pytest.mark.parametrize("asset", ["assets/styles/tokens.css", "assets/styles/site.css"])
    def test_shared_stylesheet_is_copied_and_staged(self, deploy_text: str, asset: str) -> None:
        assert f"cp {asset}" in deploy_text
        assert asset in deploy_text.split("git add")[1]

    @pytest.mark.parametrize(
        ("workflow", "own_prefix"),
        [
            ("lsp-benchmark.yml", "lsp/benchmark/"),
            ("typecheck-benchmark.yml", "typecheck_benchmark/"),
        ],
    )
    def test_benchmark_workflow_ships_the_shared_sheets_with_its_page(
        self, workflow: str, own_prefix: str
    ) -> None:
        """Each benchmark publishes its own dashboard, so it must publish the
        stylesheets that dashboard links. Otherwise a benchmark run landing
        before deploy.yml would put an unstyled page live."""
        text = (REPO_ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
        staged = text.split("git add")[1].split("git diff")[0]
        assert f"{own_prefix}index.html" in staged
        for sheet in ("assets/styles/tokens.css", "assets/styles/site.css"):
            assert sheet in staged, f"{workflow} publishes a page that links {sheet}"
            assert f"cp {sheet}" in text

    @pytest.mark.parametrize(
        ("workflow", "other_prefix"),
        [
            ("lsp-benchmark.yml", "typecheck_benchmark/"),
            ("typecheck-benchmark.yml", "lsp/benchmark/"),
        ],
    )
    def test_benchmark_workflow_stays_out_of_the_other_subtrees(
        self, workflow: str, other_prefix: str
    ) -> None:
        """A benchmark owns its own subtree plus the shared sheets. It must not
        touch the homepage or the other benchmark."""
        text = (REPO_ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
        staged = text.split("git add")[1].split("git diff")[0]
        assert other_prefix not in staged

        # Root-level site files belong to deploy.yml alone. Compare bare tokens
        # so that "lsp/benchmark/index.html" does not read as the homepage.
        staged_paths = {token.strip() for token in staged.replace("\\", " ").split()}
        for forbidden in ("index.html", "404.html", "sitemap.xml", "robots.txt", "favicon.svg"):
            assert forbidden not in staged_paths, (
                f"{workflow} must not publish the homepage or its metadata"
            )
