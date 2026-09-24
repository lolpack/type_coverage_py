# Claude Code Instructions for type_coverage_py

## ⚠️ CRITICAL: Always Activate Virtual Environment First!

Before running ANY Python command, terminal command, or pip install:

```bash
source .venv/bin/activate
```

Then verify with: `which python` (should show `.venv/bin/python`)

## Quick Reference

| Task | Command (after activating venv) |
|------|--------------------------------|
| Run tests | `python -m pytest tests/ -v` |
| Type check | `pyrefly check` |
| Install deps | `pip install -r requirements.txt` |
| Run LSP benchmark | `python -m lsp.benchmark.daily_runner --packages 5 --runs 3` |
| Run benchmark on local dir | `python -m typecheck_benchmark --local /path/to/project` |

## Project Overview

This project publishes [python-type-checking.com](https://python-type-checking.com/):
an editorial homepage about the history and state of typed Python, plus two
performance benchmarks (language server latency and type checker timing).

Package type-coverage generation is **retired**. The historical data stays in
the repository at its existing paths, but nothing recomputes it. Don't add a
replacement crawler. Current package typing metrics live at
[Typestats](https://jorenham.github.io/typestats/dashboard/).

## Key Rules

1. **Virtual environment**: ALWAYS `source .venv/bin/activate` first
2. **Type checker**: Use `pyrefly check` (not pyright/mypy for linting)
3. **Typeshed**: Don't modify files in `typeshed/` - it's a git submodule
4. **Type annotations**: Required on all functions
5. **Python version**: 3.12
6. **Git workflow**: NEVER commit or push directly to main. Always create a feature branch, push it to origin, and let the user merge.

## Pre-Commit Checklist

Before every commit, run ALL of these checks:

```bash
source .venv/bin/activate
python -m pytest tests/ -v          # Python tests
pyrefly check                       # Python type checking
npm run check                       # TypeScript type checking (runs tsc --noEmit)
```

Type check **all** modified Python files, including files in `tests/`, `lsp/`, and `typecheck_benchmark/`.

## Package Source

Both the LSP benchmark and typecheck benchmark use `typecheck_benchmark/install_envs.json` as their single source of truth for packages. They must always test the same set of packages.

## Site structure

| Path | What it is |
|------|------------|
| `index.html` | The homepage. Hand-authored static HTML, no JavaScript. See `docs/content-maintenance.md` before editing content. |
| `assets/styles/tokens.css` | Shared design tokens. Both dashboards and the homepage consume these, so don't fork them. |
| `assets/styles/site.css` | Shared header, nav, footer and common components. No chart or table selectors belong here. |
| `assets/styles/home.css` | Homepage only. |
| `lsp/benchmark/`, `typecheck_benchmark/` | The two dashboards, at their canonical URLs. |
| `historical_data/`, `prioritized/`, `package_report.json` | Frozen coverage data and its viewers. Leave alone. |

### Publishing ownership

- `deploy.yml` publishes **site assets only** (HTML, CSS, JS, favicon, sitemap, robots, CNAME).
- Each benchmark workflow publishes **only its own results** under `*/results/`.

Never cross these. A site deploy that writes result JSON can overwrite newer
published results with the sparse copy on `main`; a benchmark job that writes
page assets can revert a newer UI release.
