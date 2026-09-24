"""End-to-end link and asset resolution across every maintained page.

Each page's own test module checks its content. This one checks the seams:
that no maintained page links to a file that does not exist, that the pages
reference each other consistently, and that everything a page loads is
actually copied by the deploy workflow.

No network access: external links are only checked for scheme safety, not
reachability. Manual link checking before a release is covered in
docs/content-maintenance.md.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Every page the redesign maintains. The frozen coverage pages are checked
#: separately and more loosely, since they are historical artifacts.
MAINTAINED_PAGES = {
    "/": REPO_ROOT / "index.html",
    "/404.html": REPO_ROOT / "404.html",
    "/lsp/benchmark/": REPO_ROOT / "lsp" / "benchmark" / "index.html",
    "/typecheck_benchmark/": REPO_ROOT / "typecheck_benchmark" / "index.html",
}

FROZEN_PAGES = {
    "/prioritized/": REPO_ROOT / "prioritized" / "index.html",
    "/historical_data/coverage-trends.html": (
        REPO_ROOT / "historical_data" / "coverage-trends.html"
    ),
    "/prioritized/historical_data/coverage-trends.html": (
        REPO_ROOT / "prioritized" / "historical_data" / "coverage-trends.html"
    ),
}


class RefCollector(HTMLParser):
    """Collect every URL a page references, tagged by how it is used."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self.assets: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        if "id" in attr:
            self.ids.add(attr["id"])
        if tag == "a" and "href" in attr:
            self.hrefs.append(attr["href"])
        if tag == "link" and "href" in attr:
            self.assets.append(attr["href"])
        if tag in ("script", "img") and attr.get("src"):
            self.assets.append(attr["src"])


def collect(page_path: Path) -> RefCollector:
    parser = RefCollector()
    parser.feed(page_path.read_text(encoding="utf-8"))
    return parser


def resolve(reference: str, page_route: str) -> Path | None:
    """Map a same-site reference to the file that provides it.

    Returns None for external references.

    Compiled JavaScript is gitignored (see the ``npm run build`` outputs listed
    in ``.gitignore``), so on a fresh checkout it does not exist yet. What the
    reference needs is a *source* that the build will turn into that file, so a
    missing ``.js`` resolves to its ``.ts`` sibling. That keeps the check
    meaningful (a script with no source anywhere still fails) without requiring
    tests to run after a build.
    """
    parsed = urlparse(reference)
    if parsed.scheme or parsed.netloc:
        return None
    path = parsed.path
    if not path:
        return None

    if path.startswith("/"):
        target = REPO_ROOT / path.lstrip("/")
    else:
        base = (REPO_ROOT / page_route.lstrip("/")).parent
        if page_route.endswith("/"):
            base = REPO_ROOT / page_route.strip("/")
        target = (base / path).resolve()

    if target.is_dir():
        target = target / "index.html"

    if target.suffix == ".js" and not target.exists():
        source = target.with_suffix(".ts")
        if source.exists():
            return source

    return target


@pytest.fixture(params=sorted(MAINTAINED_PAGES), ids=lambda r: r)
def maintained(request: pytest.FixtureRequest) -> tuple[str, RefCollector]:
    route = request.param
    return route, collect(MAINTAINED_PAGES[route])


class TestEveryMaintainedPageResolves:
    def test_internal_links_point_at_real_files(
        self, maintained: tuple[str, RefCollector]
    ) -> None:
        route, refs = maintained
        missing = [
            link
            for link in refs.hrefs
            if (target := resolve(link, route)) is not None and not target.exists()
        ]
        assert not missing, f"{route} links to missing files: {missing}"

    def test_loaded_assets_exist(self, maintained: tuple[str, RefCollector]) -> None:
        route, refs = maintained
        missing = [
            asset
            for asset in refs.assets
            if (target := resolve(asset, route)) is not None and not target.exists()
        ]
        assert not missing, f"{route} loads missing assets: {missing}"

    def test_same_page_anchors_have_targets(
        self, maintained: tuple[str, RefCollector]
    ) -> None:
        route, refs = maintained
        anchors = {
            link[1:] for link in refs.hrefs if link.startswith("#") and len(link) > 1
        }
        missing = anchors - refs.ids
        assert not missing, f"{route} has dangling anchors: {sorted(missing)}"

    def test_external_links_are_https(self, maintained: tuple[str, RefCollector]) -> None:
        route, refs = maintained
        bad = [
            link
            for link in refs.hrefs + refs.assets
            if (scheme := urlparse(link).scheme) and scheme != "https"
        ]
        assert not bad, f"{route} has non-https links: {bad}"

    def test_page_uses_the_shared_tokens(
        self, maintained: tuple[str, RefCollector]
    ) -> None:
        _, refs = maintained
        assert "/assets/styles/tokens.css" in refs.assets


class TestCrossPageNavigation:
    """The three maintained pages must reference each other consistently."""

    def test_homepage_links_both_benchmarks(self) -> None:
        refs = collect(MAINTAINED_PAGES["/"])
        assert "/typecheck_benchmark/" in refs.hrefs
        assert "/lsp/benchmark/" in refs.hrefs

    @pytest.mark.parametrize(
        ("page", "sibling"),
        [
            ("/lsp/benchmark/", "/typecheck_benchmark/"),
            ("/typecheck_benchmark/", "/lsp/benchmark/"),
        ],
    )
    def test_each_benchmark_links_home_and_its_sibling(
        self, page: str, sibling: str
    ) -> None:
        refs = collect(MAINTAINED_PAGES[page])
        assert "/" in refs.hrefs, f"{page} must link back to the homepage"
        assert sibling in refs.hrefs

    def test_no_page_advertises_current_coverage(self) -> None:
        """No stale 'latest coverage' wording in active navigation or metadata."""
        for route, path in MAINTAINED_PAGES.items():
            text = path.read_text(encoding="utf-8").lower()
            for stale in ("daily coverage calculator", "back to type coverage",
                          "package type coverage report"):
                assert stale not in text, f"{route} still says {stale!r}"


class TestFrozenPagesStillWork:
    @pytest.fixture(params=sorted(FROZEN_PAGES), ids=lambda r: r)
    def frozen(self, request: pytest.FixtureRequest) -> tuple[str, RefCollector]:
        return request.param, collect(FROZEN_PAGES[request.param])

    def test_still_loads_its_own_assets(self, frozen: tuple[str, RefCollector]) -> None:
        route, refs = frozen
        missing = [
            asset
            for asset in refs.assets
            if (target := resolve(asset, route)) is not None and not target.exists()
        ]
        assert not missing, f"{route} loads missing assets: {missing}"

    def test_frozen_banner_links_resolve(self, frozen: tuple[str, RefCollector]) -> None:
        route, refs = frozen
        missing = [
            link
            for link in refs.hrefs
            if (target := resolve(link, route)) is not None and not target.exists()
        ]
        assert not missing, f"{route} links to missing files: {missing}"


class TestNoDeadBuildConfig:
    """The retired homepage controller is gone from every place that named it."""

    def test_root_scripts_directory_is_gone(self) -> None:
        assert not (REPO_ROOT / "scripts").exists()

    def test_tsconfig_no_longer_compiles_it(self) -> None:
        text = (REPO_ROOT / "tsconfig.json").read_text(encoding="utf-8")
        assert '"scripts/*.ts"' not in text

    def test_tsconfig_still_compiles_every_live_controller(self) -> None:
        import json

        includes = json.loads((REPO_ROOT / "tsconfig.json").read_text(encoding="utf-8"))
        for pattern in includes["include"]:
            directory = REPO_ROOT / pattern.rsplit("/", 1)[0]
            assert directory.is_dir(), f"tsconfig includes a missing directory: {pattern}"
            assert list(directory.glob("*.ts")), f"no sources match {pattern}"

    def test_deploy_no_longer_copies_it(self) -> None:
        text = (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text(
            encoding="utf-8"
        )
        assert "cp scripts/main.js" not in text

    def test_every_compiled_output_in_gitignore_has_a_source(self) -> None:
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        for line in gitignore.splitlines():
            line = line.strip()
            if not line.endswith(".js") or line.startswith("#"):
                continue
            source = REPO_ROOT / line.replace(".js", ".ts")
            assert source.is_file(), f".gitignore lists {line} but {source.name} is gone"


class TestDeployPublishesEverythingThePagesLoad:
    """A linked asset that the deploy never copies is a broken page in production."""

    @pytest.fixture(scope="class")
    @staticmethod
    def deploy_text() -> str:
        return (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text(
            encoding="utf-8"
        )

    def test_all_root_relative_assets_are_published(self, deploy_text: str) -> None:
        staged = deploy_text.split("git add")[1].split("git diff")[0]
        wanted: set[str] = set()
        for route, path in {**MAINTAINED_PAGES, **FROZEN_PAGES}.items():
            for asset in collect(path).assets:
                if asset.startswith("/") and not asset.startswith("//"):
                    wanted.add(asset.lstrip("/"))
        missing = [asset for asset in sorted(wanted) if asset not in staged]
        assert not missing, f"pages load assets the deploy never stages: {missing}"

    def test_cname_is_preserved(self, deploy_text: str) -> None:
        # CNAME lives on published-report and must survive every publication:
        # the deploy stages an explicit file list, never a wholesale replace.
        assert "rsync" not in deploy_text
        assert "--delete" not in deploy_text
        assert "git clean" not in deploy_text
        assert not re.search(r"git add\s+(-A|--all|\.)\b", deploy_text)

    def test_deploy_never_force_pushes(self, deploy_text: str) -> None:
        assert "--force" not in deploy_text and "-f origin" not in deploy_text
