# Maintaining the homepage content

The homepage (`index.html`) is hand-authored static HTML. There is no content
pipeline, no template engine, and no build step between editing the file and
seeing the result. Open it in a browser.

That choice is deliberate. The page is a curated narrative that changes a few
times a year. A JSON content model plus a renderer would be more machinery to
maintain than the thing it maintains.

The safety net is `tests/test_homepage.py`. It pins the required sections, every
curated milestone, the survey rules, and the editorial constraints below. If you
change content, run it.

```bash
source .venv/bin/activate
pytest tests/test_homepage.py -q
```

## Adding a timeline event

Copy an existing `<li class="timeline__item timeline__item--CATEGORY">` block and
place it in chronological order. Categories are `language`, `tools`, `ecosystem`
and `governance`.

```html
<li class="timeline__item timeline__item--tools">
    <div class="timeline__meta">
        <span class="timeline__date">March 3, 2027</span>
        <span class="timeline__tag">Tools</span>
    </div>
    <h3>Short, concrete headline</h3>
    <p>One or two sentences. What happened, and why it mattered.</p>
    <p class="sources"><a href="https://example.com/primary-source">Source title</a></p>
</li>
```

Then add the headline to `REQUIRED_MILESTONES` in `tests/test_homepage.py`, so a
later edit cannot drop it silently.

### Rules the tests enforce

- **The category badge text is required.** The coloured dot is decorative; a
  reader who cannot distinguish the colours must still get the category.
- **Every item cites a primary source** in a `<p class="sources">`.
- **Date precision matches the source.** If the source says "2012", write
  `2012`, and never invent a January 1. Distinguish a proposal from a release from
  a beta from a standard-library version from a wind-down, and say which one
  the entry is about.
- **Primary sources beat commentary.** Google's pytype README over a Hacker News
  thread; a PEP over a blog post summarising it.
- **`<details>` for depth.** If an entry needs more than two sentences, the extra
  goes in a collapsible block rather than expanding the card.

## Publishing the 2026 survey

The 2026 card is deliberately inert: no results, no report URL, no release date,
and no disabled button. `tests/test_homepage.py::TestSurveys` fails if any of
those appear.

When the real report is out:

1. Verify the official report URL in a browser.
2. Replace the `card--forthcoming` article with one shaped like the 2025 card.
3. Add the publication date, the report link, and a one- or two-sentence summary.
4. Add a statistic **only** with its population and its caveat, in a
   `<span class="stat__caveat">` next to the number, not behind a hover.
5. Add a matching timeline entry.
6. Update `tests/test_homepage.py`: move the year out of the forthcoming
   assertions and add the new report URL.

Do not turn three self-selected annual samples into a longitudinal population
study. They are separate samples of people who chose to answer a survey about
typing, and the page says so.

## Editorial boundaries

These are not style preferences; they are what keeps the page trustworthy.

- **Never invent** a date, a survey result, a paper finding, a citation, or a URL.
  If a fact cannot be sourced, cut it. The story survives losing a detail.
- **No overall checker winner.** The benchmarks measure performance. They do not
  measure correctness, conformance, or fitness for a project.
- **Don't relabel the LSP benchmark.** It measures `textDocument/definition`.
  Not completions, not hover, not diagnostics, not "editor responsiveness". A
  returned location that exists is not necessarily the right definition.
- **Agents are an open question.** No productivity or success-rate numbers.
- **Coverage is not quality.** Annotation coverage is not test coverage, not type
  completeness, and not correctness.
- **Disclose the affiliation.** The footer notes that the maintainer works on
  Pyrefly, and that this is an independent, unendorsed resource. Pyrefly appears
  on the page as one option among several, never as the site's default.
- **Old coverage data and Typestats are not comparable.** Different
  methodologies. Never draw one trend line through both.

## Retired coverage pages

`/prioritized/`, `/historical_data/coverage-trends.html` and
`/prioritized/historical_data/coverage-trends.html` still work and still render
their frozen data. Each opens with a "This data is frozen" banner pointing at
Typestats and the homepage.

Leave the data alone. Nothing recomputes it, and it should not be reformatted,
regenerated, or migrated.

## Checking links

External links are living documents and they rot. Before a release, click
through the source links in the timeline and the survey cards. When one breaks,
find the official replacement rather than substituting a secondary source. If
there isn't one, remove the unsupported detail rather than the milestone.
