"""House style: no em dashes in the site's copy or in the files this redesign owns.

Use a colon, a comma, parentheses, or a second sentence instead. The check
catches the literal character and both of its HTML entity spellings.

Scope is the site content, the shared stylesheets, the workflows, the project
docs and this test suite. Deliberately out of scope:

* frozen coverage snapshots under ``historical_data/`` and ``prioritized/``,
  which are historical artifacts and must not be edited;
* the benchmark runners, whose docstrings predate this convention and are not
  user-facing copy;
* anything vendored or untracked.

En dashes are not checked. They carry meaning in ranges such as ``2020-2022``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Assembled rather than written out, so this file does not trip its own check:
# the literal character and both HTML entity spellings of it.
EM_DASH = chr(0x2014)
EM_DASHES = (EM_DASH, "&" + "mdash;", "&#" + "8212;")

#: Files and directories whose copy this project authors and maintains.
OWNED = (
    "index.html",
    "404.html",
    "robots.txt",
    "sitemap.xml",
    "favicon.svg",
    "README.md",
    "CLAUDE.md",
    "BENCHMARKS.md",
    "requirements.txt",
    "assets/",
    "docs/",
    ".github/workflows/",
    "tests/",
    "lsp/benchmark/index.html",
    "typecheck_benchmark/index.html",
)

#: Predates this convention and is not user-facing copy.
EXEMPT = (
    "tests/test_typecheck_benchmark_configs.py",
)


def owned_files() -> list[Path]:
    """Tracked files under the owned paths, via git so nothing untracked leaks in."""
    listing = subprocess.run(
        ["git", "ls-files", "-z", *OWNED],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(
        REPO_ROOT / name
        for name in listing.split("\0")
        if name and name not in EXEMPT
    )


OWNED_FILES = owned_files()
IDS = [str(p.relative_to(REPO_ROOT)) for p in OWNED_FILES]


def test_the_check_covers_the_site_copy() -> None:
    """A path-filter bug that matched nothing would make this suite vacuous."""
    assert len(OWNED_FILES) > 15
    for expected in (
        "index.html",
        "404.html",
        "README.md",
        "assets/styles/home.css",
        "assets/styles/tokens.css",
    ):
        assert expected in IDS, f"{expected} should be covered by the style check"


@pytest.mark.parametrize("path", OWNED_FILES, ids=IDS)
def test_file_has_no_em_dash(path: Path) -> None:
    offenders: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for number, line in enumerate(text.splitlines(), start=1):
        if any(dash in line for dash in EM_DASHES):
            offenders.append(f"line {number}: {line.strip()[:90]}")
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)} uses an em dash; "
        "use a colon, comma, parentheses, or a second sentence:\n  "
        + "\n  ".join(offenders)
    )
