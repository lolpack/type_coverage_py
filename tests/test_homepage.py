"""Content and structure checks for the Python Type Checking homepage.

The homepage is hand-authored static HTML. These tests are the safety net that
makes that safe: they pin the required narrative sections, the curated
milestones that carry the story, the survey links, and the editorial rules the
page must not break, in particular that the 2026 survey stays unpublished and
that every factual claim keeps a source link.

Parsing uses html.parser from the standard library, so there is no new
dependency and no browser needed.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOMEPAGE = REPO_ROOT / "index.html"
NOT_FOUND_PAGE = REPO_ROOT / "404.html"

TYPESTATS_URL = "https://jorenham.github.io/typestats/dashboard/"
DISCOURSE_URL = "https://discuss.python.org/c/typing/32"
SURVEY_2024_URL = (
    "https://engineering.fb.com/2024/12/09/developer-tools/typed-python-2024-survey-meta/"
)
SURVEY_2025_URL = (
    "https://engineering.fb.com/2025/12/22/developer-tools/"
    "python-typing-survey-2025-code-quality-flexibility-typing-adoption/"
)


class PageParser(HTMLParser):
    """Collect the bits of structure the assertions below need."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.section_ids: list[str] = []
        self.all_ids: list[str] = []
        self.links: list[str] = []
        self.headings: list[tuple[str, str]] = []
        self.landmarks: list[str] = []
        self.timeline_categories: list[str] = []
        self.stylesheets: list[str] = []
        self.scripts: list[str] = []
        self._heading: str | None = None
        self._heading_text: list[str] = []
        self._in_tag_span = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        if "id" in attr:
            self.all_ids.append(attr["id"])
        if tag in ("section", "article") and "id" in attr:
            self.section_ids.append(attr["id"])
        if tag == "a" and "href" in attr:
            self.links.append(attr["href"])
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._heading = tag
            self._heading_text = []
        if tag in ("main", "header", "footer", "nav"):
            self.landmarks.append(tag)
        if tag == "link" and attr.get("rel") == "stylesheet":
            self.stylesheets.append(attr.get("href", ""))
        if tag == "script":
            self.scripts.append(attr.get("src", "inline"))
        if "class" in attr and "timeline__tag" in attr["class"]:
            self._in_tag_span = True

    def handle_endtag(self, tag: str) -> None:
        if self._heading and tag == self._heading:
            self.headings.append((tag, "".join(self._heading_text).strip()))
            self._heading = None
        if tag == "span":
            self._in_tag_span = False

    def handle_data(self, data: str) -> None:
        if self._heading:
            self._heading_text.append(data)
        if self._in_tag_span:
            self.timeline_categories.append(data.strip())


@pytest.fixture(scope="module")
def html() -> str:
    return HOMEPAGE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def text(html: str) -> str:
    """Whitespace-collapsed HTML, for prose assertions that span source lines."""
    return re.sub(r"\s+", " ", html)


@pytest.fixture(scope="module")
def page(html: str) -> PageParser:
    parser = PageParser()
    parser.feed(html)
    return parser


# --------------------------------------------------------------- structure --


class TestPageStructure:
    def test_homepage_exists(self) -> None:
        assert HOMEPAGE.is_file()

    def test_is_no_longer_the_coverage_dashboard(self, html: str) -> None:
        assert "Package Type Coverage Report" not in html
        assert "package_report.json" not in html, (
            "the homepage must not fetch retired coverage data"
        )

    def test_has_exactly_one_h1(self, page: PageParser) -> None:
        assert len([h for h, _ in page.headings if h == "h1"]) == 1

    def test_heading_levels_are_not_skipped(self, page: PageParser) -> None:
        levels = [int(tag[1]) for tag, _ in page.headings]
        for previous, current in zip(levels, levels[1:]):
            assert current <= previous + 1, f"jumped from h{previous} to h{current}"

    def test_has_the_required_landmarks(self, page: PageParser) -> None:
        for landmark in ("header", "nav", "main", "footer"):
            assert landmark in page.landmarks

    def test_has_a_skip_link_to_main(self, html: str, page: PageParser) -> None:
        assert 'class="skip-link" href="#main"' in html
        assert "main" in page.all_ids

    def test_declares_language_and_viewport(self, html: str) -> None:
        assert '<html lang="en">' in html
        assert 'name="viewport"' in html


class TestRequiredSections:
    #: The narrative arc. Order is part of the story, so it is asserted too.
    REQUIRED = [
        "orientation",
        "history",
        "surveys",
        "ecosystem",
        "benchmarks",
        "contribute",
        "future",
        "get-involved",
    ]

    @pytest.mark.parametrize("section_id", REQUIRED)
    def test_section_exists(self, page: PageParser, section_id: str) -> None:
        assert section_id in page.all_ids

    def test_sections_appear_in_narrative_order(self, page: PageParser) -> None:
        present = [i for i in page.section_ids if i in self.REQUIRED]
        assert present == self.REQUIRED

    def test_every_nav_anchor_resolves(self, page: PageParser) -> None:
        anchors = {link[1:] for link in page.links if link.startswith("#")}
        missing = anchors - set(page.all_ids)
        assert not missing, f"anchors with no target: {sorted(missing)}"


# ----------------------------------------------------------------- content --


class TestTimeline:
    #: Curated milestones the story cannot be told without. Each entry is a
    #: substring that must appear in a timeline heading.
    REQUIRED_MILESTONES = [
        "Function annotations provide the syntax",   # PEP 3107
        "Google starts building pytype",             # pytype begins, 2012
        "mypy's source becomes public",
        "PEP 484 standardizes type hints",
        "Typeshed becomes shared infrastructure",
        "Variable annotations become syntax",        # PEP 526
        "Pyre is open-sourced",
        "Types travel with packages",                # PEP 561
        "Pyright joins the ecosystem",
        "Protocols describe structural interfaces",  # PEP 544
        "Everyday annotations get shorter",          # PEP 585/604/673
        "Type parameters get dedicated syntax",      # PEP 695
        "PEP 729 establishes the Typing Council",
        "The 2024 typing survey",
        "Pyrefly's public alpha",
        "ZubanLS reaches public alpha",
        "pytype winds down feature development",
        "ty reaches beta",
        "The 2025 survey",
        "Pyrefly reaches version 1.0",
        "What are types for in an agentic world?",   # 2026, open question
    ]

    @pytest.fixture(scope="class")
    @staticmethod
    def headings(page: PageParser) -> list[str]:
        return [text for _, text in page.headings]

    @pytest.mark.parametrize("milestone", REQUIRED_MILESTONES)
    def test_milestone_is_present(self, headings: list[str], milestone: str) -> None:
        assert any(milestone in h for h in headings), milestone

    def test_both_pytype_milestones_are_present(self, headings: list[str]) -> None:
        """pytype opens and closes a chapter of this history; both ends matter."""
        assert any("Google starts building pytype" in h for h in headings)
        assert any("pytype winds down feature development" in h for h in headings)

    def test_pytype_wind_down_is_not_overstated(self, text: str) -> None:
        assert "Python 3.12 is its final supported version" in text
        # The FAQ still allows bug fixes, so the page must say "feature
        # development" is ending, and must not claim the project ended.
        assert "not a statement that the repository was archived" in text
        for overstatement in ("abandoned", "layoff", "no longer maintained"):
            assert overstatement not in text.lower(), overstatement

    def test_pytype_history_cites_google_not_hacker_news(self, html: str) -> None:
        assert "github.com/google/pytype" in html
        assert "news.ycombinator.com" not in html

    def test_every_timeline_item_has_a_category_label(self, html: str) -> None:
        items = html.count('<li class="timeline__item timeline__item--')
        tags = html.count('class="timeline__tag"')
        assert items == tags == len(self.REQUIRED_MILESTONES)

    def test_categories_are_spelled_out_not_colour_coded(
        self, page: PageParser
    ) -> None:
        assert set(page.timeline_categories) <= {
            "Language",
            "Tools",
            "Ecosystem",
            "Governance",
            "Open question",
        }
        assert all(text for text in page.timeline_categories)

    def test_every_historical_event_cites_a_source(self, html: str) -> None:
        items = re.findall(r'<li class="timeline__item.*?</li>', html, re.S)
        assert len(items) == len(self.REQUIRED_MILESTONES)
        for item in items:
            if "timeline__item--open" in item:
                continue  # a question about 2026 has nothing to cite
            assert 'class="sources"' in item, item[:200]

    def test_timeline_is_an_ordered_list(self, html: str) -> None:
        assert '<ol class="timeline">' in html

    def test_ends_with_an_open_next_chapter(self, html: str) -> None:
        assert "The next chapter is open" in html
        assert 'href="#future"' in html

    def test_the_2026_entry_is_marked_as_an_open_question(self, text: str) -> None:
        """The last entry has not happened; it must not read like an event."""
        entry = text.split('timeline__item--open')[1].split("</li>")[0]
        assert "Open question" in entry, "the category badge must say so in text"
        assert "Every entry above already happened. This one has not." in entry
        assert "#future" in entry

    def test_the_2026_entry_predicts_nothing(self, text: str) -> None:
        entry = text.split('timeline__item--open')[1].split("</li>")[0]
        assert "%" not in entry
        for claim in ("will become", "is becoming", "proves", "shows that"):
            assert claim not in entry.lower(), claim

    def test_only_the_2026_entry_lacks_a_source(self, html: str) -> None:
        """An unanswered question has nothing to cite; every event does."""
        items = re.findall(r'<li class="timeline__item.*?</li>', html, re.S)
        unsourced = [i for i in items if 'class="sources"' not in i]
        assert len(unsourced) == 1
        assert "timeline__item--open" in unsourced[0]

    def test_no_invented_january_first_dates(self, html: str) -> None:
        """Year-only sources must stay year-only."""
        dates = re.findall(r'class="timeline__date">([^<]+)<', html)
        assert dates
        for date in dates:
            assert "January 1" not in date

    def test_proposal_and_shipping_years_are_not_conflated(self, text: str) -> None:
        """PEP 3107 was proposed in 2006; Python 3.0 shipped in 2008."""
        entry = text.split('<ol class="timeline">')[1].split("</li>")[0]
        assert "Proposed 2006" in entry
        assert "2008" in entry, "the Python 3.0 release year must be stated"
        assert "shipped 2008 in Python 3.0" in entry

    def test_pep_484_does_not_claim_runtime_semantics(self, text: str) -> None:
        """PEP 484 gives annotations a conventional static, not runtime, meaning."""
        entry = text.split("PEP 484 standardizes type hints")[1].split("</li>")[0]
        assert "static type checkers" in entry
        assert "runtime meaning" in entry
        assert "turned annotations from a general-purpose hook into" not in entry

    def test_pep_695_is_not_reduced_to_cosmetic_syntax(self, text: str) -> None:
        """The PEP also specifies annotation scopes and lazy evaluation."""
        entry = text.split("Type parameters get dedicated syntax")[1].split("</li>")[0]
        assert "annotation scope" in entry
        assert "lazy evaluation" in entry
        assert "not new expressive power" not in entry

    def test_pep_729_describes_council_responsibilities(self, text: str) -> None:
        """The PEP assigns stewardship; it did not create every listed artifact."""
        entry = text.split("PEP 729 establishes the Typing Council")[1].split("</li>")[0]
        assert "made it responsible for" in entry
        assert "maintained typing specification" in entry

    def test_key_dates_are_stated_with_the_precision_the_source_supports(
        self, html: str
    ) -> None:
        dates = re.findall(r'class="timeline__date">([^<]+)<', html)
        joined = " | ".join(dates)
        assert "2012" in joined                    # pytype: year only
        assert "December 7, 2012" in joined        # mypy: exact
        assert "November 20, 2023" in joined       # PEP 729 resolution
        assert "August 20, 2025" in joined         # pytype FAQ
        assert "December 16, 2025" in joined       # ty beta
        assert "May 12, 2026" in joined                # Pyrefly 1.0


class TestSurveys:
    def test_2024_report_is_linked(self, page: PageParser) -> None:
        assert SURVEY_2024_URL in page.links

    def test_2025_report_is_linked(self, page: PageParser) -> None:
        assert SURVEY_2025_URL in page.links

    def test_2026_is_labelled_coming_soon(self, html: str) -> None:
        assert "Results coming soon" in html

    def test_2026_has_no_fabricated_results(self, html: str) -> None:
        card = html.split('card--forthcoming')[1].split("</article>")[0]
        assert "%" not in card, "no invented statistic for an unpublished survey"
        assert "2026" in card
        for fabricated in ("engineering.fb.com/2026", "survey-2026"):
            assert fabricated not in card

    def test_2026_card_has_no_dead_or_disabled_button(self, html: str) -> None:
        card = html.split('card--forthcoming')[1].split("</article>")[0]
        assert "<button" not in card, "a coming-soon card should contain text, not a dead control"
        assert "disabled" not in card

    def test_statistics_carry_their_self_selection_caveat(self, html: str) -> None:
        """The caveat sits next to the number, not behind a hover."""
        stats = re.findall(r'<p class="stat">.*?</p>', html, re.S)
        assert len(stats) == 2
        for stat in stats:
            assert "Self-selected sample" in stat

    def test_two_samples_are_not_presented_as_a_trend(self, html: str) -> None:
        assert "should not be read as a trend line" in html


class TestEcosystemHandoff:
    def test_typestats_is_linked(self, page: PageParser) -> None:
        assert TYPESTATS_URL in page.links

    def test_typestats_is_named_as_the_current_destination(self, html: str) -> None:
        assert "Explore package typing with Typestats" in html

    def test_retirement_is_stated_plainly(self, text: str) -> None:
        assert "That measurement is now retired" in text

    def test_original_purpose_is_explained(self, text: str) -> None:
        assert "type-annotation coverage" in text
        assert "make the gap visible" in text

    def test_old_and_new_data_are_not_presented_as_one_trend(self, text: str) -> None:
        assert "different methodologies" in text

    def test_historical_data_remains_reachable(self, page: PageParser) -> None:
        assert "/historical_data/coverage-trends.html" in page.links

    def test_handoff_notice_is_near_the_top(self, html: str) -> None:
        """A visitor looking for coverage must not have to read the whole page."""
        assert html.index("Typestats") < html.index('id="history"')

    def test_handoff_notice_is_not_dismissible(self, html: str) -> None:
        notice = html.split('class="site-notice site-notice--archive handoff"')[1]
        assert "<button" not in notice.split("</div>")[0]


class TestBenchmarkCards:
    def test_both_benchmarks_are_linked(self, page: PageParser) -> None:
        assert "/typecheck_benchmark/" in page.links
        assert "/lsp/benchmark/" in page.links

    def test_typecheck_checker_set_is_listed(self, html: str) -> None:
        assert "mypy · Pyright · Pyrefly · ty · Zuban" in html

    def test_lsp_checker_set_is_listed(self, html: str) -> None:
        assert "Pyright · Pyrefly · ty · Zuban" in html

    def test_lsp_measurement_is_described_accurately(self, html: str) -> None:
        assert "textDocument/definition" in html
        for wrong in ("time-to-first-diagnostic", "hover latency"):
            assert wrong not in html

    def test_scope_note_limits_the_claim(self, text: str) -> None:
        assert "Performance is one dimension" in text
        assert "say nothing about type-checking" in text

    def test_no_overall_winner_is_declared(self, html: str) -> None:
        for claim in ("fastest type checker", "the best checker", "winner"):
            assert claim not in html.lower()

    def test_conformance_results_are_linked(self, page: PageParser) -> None:
        """Speed is not the only axis; point at the correctness one too."""
        assert (
            "https://htmlpreview.github.io/?https://github.com/python/typing/"
            "blob/main/conformance/results/results.html" in page.links
        )

    def test_conformance_link_is_framed_as_the_other_dimension(self, text: str) -> None:
        assert "conformance test suite and results" in text
        assert "a fast checker that disagrees with the spec" in text


class TestContributeSection:
    def test_typeshed_contributing_guide_is_linked(self, page: PageParser) -> None:
        assert (
            "https://github.com/python/typeshed/blob/main/CONTRIBUTING.md" in page.links
        )

    def test_coverage_gate_example_is_shown(self, html: str) -> None:
        assert "pyrefly coverage check src/ --fail-under 80" in html

    def test_pyrefly_is_framed_as_one_option(self, text: str) -> None:
        assert "Pyrefly is one" in text
        assert "other checkers offer comparable" in text

    def test_pyrefly_docs_are_linked(self, page: PageParser) -> None:
        assert "https://pyrefly.org/en/docs/report/" in page.links

    def test_coverage_is_not_sold_as_a_quality_score(self, text: str) -> None:
        assert "Annotation coverage is not a quality score" in text
        assert "not test coverage" in text
        assert "Never add" in text and "to move a number" in text


class TestFutureSection:
    def test_framed_as_an_open_question(self, text: str) -> None:
        assert (
            "Could static types become part of the interface between code and agents?"
            in text
        )
        assert "This is a question, not a finding" in text

    def test_no_fabricated_productivity_numbers(self, html: str) -> None:
        future = html.split('id="future"')[1].split("</section>")[0]
        assert not re.search(r"\d+\s*%", future), "no invented agent-success statistic"

    def test_states_that_type_checking_is_not_correctness(self, text: str) -> None:
        assert "passing a type checker has never meant a program is correct" in text.lower()

    def test_mentions_non_agent_directions_too(self, text: str) -> None:
        assert "easier adoption" in text
        assert "more consistent behaviour between checkers" in text


class TestGetInvolved:
    def test_discourse_is_linked(self, page: PageParser) -> None:
        assert DISCOURSE_URL in page.links

    def test_closing_line_is_present(self, text: str) -> None:
        assert "Python typing is still evolving. Help shape what comes next." in text

    def test_affiliation_is_disclosed_in_the_footer(self, text: str) -> None:
        footer = text.split('class="site-footer"')[1]
        assert "who works on Pyrefly" in footer
        assert "not an official Python project" in footer

    def test_no_endorsement_is_implied(self, html: str) -> None:
        assert "not endorsed by" in html

    def test_correction_route_is_offered(self, page: PageParser) -> None:
        assert any("issues" in link for link in page.links)


# ------------------------------------------------------- links and assets --


class TestLinksAndAssets:
    def test_all_external_links_use_https(self, page: PageParser) -> None:
        for link in page.links:
            scheme = urlparse(link).scheme
            assert scheme in ("", "https"), f"unsafe or non-https link: {link}"

    def test_no_javascript_urls(self, page: PageParser) -> None:
        assert not [link for link in page.links if link.lower().startswith("javascript:")]

    def test_internal_links_resolve_to_a_file_in_the_repo(self, page: PageParser) -> None:
        missing = []
        for link in page.links:
            if not link.startswith("/") or link.startswith("//"):
                continue
            target = REPO_ROOT / link.lstrip("/").split("#")[0]
            if target.is_dir():
                target = target / "index.html"
            if not target.exists():
                missing.append(link)
        assert not missing, f"internal links with no file: {missing}"

    def test_uses_the_shared_design_system(self, page: PageParser) -> None:
        assert page.stylesheets == [
            "/assets/styles/tokens.css",
            "/assets/styles/site.css",
            "/assets/styles/home.css",
        ]

    def test_page_works_without_javascript(self, page: PageParser) -> None:
        assert page.scripts == [], "the homepage narrative must not require JavaScript"

    def test_no_remote_font_or_script_requests(self, html: str) -> None:
        for host in ("fonts.googleapis.com", "fonts.gstatic.com", "cdn.jsdelivr.net"):
            assert host not in html

    def test_has_canonical_title_and_description(self, html: str) -> None:
        assert (
            "<title>Python Type Checking: History, Surveys, and Benchmarks</title>" in html
        )
        assert 'rel="canonical" href="https://python-type-checking.com/"' in html
        assert 'name="description"' in html

    def test_has_open_graph_metadata(self, html: str) -> None:
        for prop in ("og:title", "og:description", "og:url", "og:type"):
            assert f'property="{prop}"' in html

    def test_favicon_is_local(self, html: str) -> None:
        assert 'href="/favicon.svg"' in html
        assert (REPO_ROOT / "favicon.svg").is_file()

    def test_first_party_payload_is_within_budget(self) -> None:
        """Keep the homepage cheap: HTML plus its three stylesheets."""
        total = HOMEPAGE.stat().st_size + sum(
            (REPO_ROOT / "assets" / "styles" / name).stat().st_size
            for name in ("tokens.css", "site.css", "home.css")
        )
        assert total < 100 * 1024, f"first-party payload is {total} bytes"


class TestNotFoundPage:
    @pytest.fixture(scope="class")
    @staticmethod
    def not_found() -> str:
        return NOT_FOUND_PAGE.read_text(encoding="utf-8")

    def test_exists(self) -> None:
        assert NOT_FOUND_PAGE.is_file()

    def test_is_not_indexed(self, not_found: str) -> None:
        assert 'content="noindex, follow"' in not_found

    def test_offers_the_useful_destinations(self, not_found: str) -> None:
        for destination in (
            'href="/"',
            "/typecheck_benchmark/",
            "/lsp/benchmark/",
            TYPESTATS_URL,
            "/historical_data/coverage-trends.html",
        ):
            assert destination in not_found

    def test_uses_the_shared_theme(self, not_found: str) -> None:
        assert "/assets/styles/tokens.css" in not_found
        assert 'class="site-header"' in not_found

    def test_has_exactly_one_h1(self, not_found: str) -> None:
        """A page with no h1 has no accessible name for its main content."""
        parser = PageParser()
        parser.feed(not_found)
        h1s = [text for tag, text in parser.headings if tag == "h1"]
        assert len(h1s) == 1, f"404 page should have exactly one h1, found {h1s}"

    def test_heading_levels_are_not_skipped(self, not_found: str) -> None:
        parser = PageParser()
        parser.feed(not_found)
        levels = [int(tag[1]) for tag, _ in parser.headings]
        for previous, current in zip(levels, levels[1:]):
            assert current <= previous + 1, f"jumped from h{previous} to h{current}"

    def test_has_the_required_landmarks(self, not_found: str) -> None:
        parser = PageParser()
        parser.feed(not_found)
        for landmark in ("header", "nav", "main", "footer"):
            assert landmark in parser.landmarks


class TestRetiredCoveragePages:
    """Old URLs keep working, and say plainly that their data is frozen."""

    PAGES = [
        "prioritized/index.html",
        "historical_data/coverage-trends.html",
        "prioritized/historical_data/coverage-trends.html",
    ]

    @pytest.mark.parametrize("relative", PAGES)
    def test_page_still_exists(self, relative: str) -> None:
        assert (REPO_ROOT / relative).is_file()

    @pytest.mark.parametrize("relative", PAGES)
    def test_page_declares_its_data_frozen(self, relative: str) -> None:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "This data is frozen" in text

    @pytest.mark.parametrize("relative", PAGES)
    def test_page_points_to_typestats_and_home(self, relative: str) -> None:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert TYPESTATS_URL in text
        assert 'href="/"' in text

    @pytest.mark.parametrize("relative", PAGES)
    def test_no_stale_back_link_to_the_coverage_report(self, relative: str) -> None:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        for stale in ("Back to All Packages", "Back to Package Report",
                      "Back to Prioritized Package Report"):
            assert stale not in text


class TestDeployPublishesTheNewPages:
    @pytest.fixture(scope="class")
    @staticmethod
    def deploy_text() -> str:
        return (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text(
            encoding="utf-8"
        )

    @pytest.mark.parametrize(
        "asset",
        [
            "index.html",
            "404.html",
            "favicon.svg",
            "robots.txt",
            "sitemap.xml",
            "assets/styles/home.css",
        ],
    )
    def test_asset_is_copied_and_staged(self, deploy_text: str, asset: str) -> None:
        assert f"cp {asset}" in deploy_text
        assert asset in deploy_text.split("git add")[1]


class TestSitemapAndRobots:
    def test_sitemap_lists_the_maintained_routes(self) -> None:
        text = (REPO_ROOT / "sitemap.xml").read_text(encoding="utf-8")
        for route in ("/", "/typecheck_benchmark/", "/lsp/benchmark/"):
            assert f"https://python-type-checking.com{route}</loc>" in text

    def test_sitemap_excludes_frozen_snapshots(self) -> None:
        text = (REPO_ROOT / "sitemap.xml").read_text(encoding="utf-8")
        assert "historical_data/html" not in text

    def test_robots_points_at_the_sitemap(self) -> None:
        text = (REPO_ROOT / "robots.txt").read_text(encoding="utf-8")
        assert "Sitemap: https://python-type-checking.com/sitemap.xml" in text
