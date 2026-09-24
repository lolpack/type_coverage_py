# Python Type Checking

Source for [python-type-checking.com](https://python-type-checking.com/): the
story, state, and future of typed Python, plus two performance benchmarks for
Python type checkers.

## What this site publishes

| Page | What it is |
|---|---|
| [`/`](https://python-type-checking.com/) | Editorial homepage: how Python typing developed, what the annual surveys say, where to compare tools, and how to contribute. |
| [`/lsp/benchmark/`](https://python-type-checking.com/lsp/benchmark/) | **Language server performance.** `textDocument/definition` (Go to Definition) latency, completion/error rates, and returned-location validity across Pyright, Pyrefly, ty, and Zuban. |
| [`/typecheck_benchmark/`](https://python-type-checking.com/typecheck_benchmark/) | **Type checker performance.** Wall-clock execution time and peak memory across mypy, Pyright, Pyrefly, ty, and Zuban. |

### Looking for package type coverage?

This project originally measured type-annotation coverage across popular PyPI
packages, because incomplete library typing was, and remains, a real
ecosystem problem. **That measurement is retired.** For current package typing
metrics, use [Joren's Typestats dashboard](https://jorenham.github.io/typestats/dashboard/).

The historical coverage data this project collected stays in the repository and
at its existing URLs. It is frozen: nothing recomputes or refreshes it.

- Last report: [`package_report.json`](package_report.json), [`stats_as_csv.csv`](stats_as_csv.csv)
- Dated snapshots: `historical_data/json/`, `historical_data/html/`
- Prioritized list: `prioritized/`

## Benchmarks

Both benchmarks draw their corpus from a single source of truth,
[`typecheck_benchmark/install_envs.json`](typecheck_benchmark/install_envs.json),
selecting packages with `install: true` or a non-empty `deps` list. They always
measure the same set of projects.

### Language server benchmark (`lsp-benchmark.yml`)

Runs daily at 03:00 UTC on Ubuntu, and on demand. Measures the
`textDocument/definition` request against Pyright, Pyrefly, ty, and Zuban.

It reports request latency, how often a request completed without error, and
whether the returned location is structurally valid. **A location that exists is
not necessarily the semantically correct definition.** This is a performance
and liveness measurement, not a correctness one.

### Type checker timing benchmark (`typecheck-benchmark.yml`)

Runs daily at 05:00 UTC on Ubuntu, and on demand. Measures wall-clock time and
peak memory for mypy, Pyright, Pyrefly, ty, and Zuban.

The scheduled run defaults to **one warmup run plus one measured run** per
package (`runs_per_package: 1`, `warmup_runs: 1`). Warmup runs are discarded.
Both values are adjustable when dispatching the workflow manually, and the local
CLI takes the same flags.

> macOS and Windows CI benchmarks were discontinued because of GitHub Actions
> runner cost. Results for those platforms are historical; current runs on them
> are local. See [BENCHMARKS.md](BENCHMARKS.md).

Performance is one dimension of choosing a tool. These measurements do not
establish type-checking correctness, language-feature completeness, or which
checker is best for a given project.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

npm ci
```

| Task | Command |
|---|---|
| Run tests | `pytest` |
| Type check Python | `pyrefly check` |
| Type check TypeScript | `npm run check` |
| Compile TypeScript | `npm run build` |
| Lint hooks | `pre-commit run --all-files` |

### Running the benchmarks locally

```bash
# Language server benchmark
python -m lsp.benchmark.daily_runner --packages 5 --runs 3

# Type checker timing benchmark, against a local project
python -m typecheck_benchmark --local /path/to/project
```

## Branching strategy

- **`main`**: development branch. All code, content, and workflow changes.
- **`published-report`**: deploy-only branch served by GitHub Pages. Never
  commit code changes here directly.

Workflows check out `main`, run their task, and push their own output to
`published-report`. The benchmark workflows publish only their own results; site
assets are published by `deploy.yml`.

## Contributing

Corrections to the site's history, sources, or wording are welcome. Open an
issue or a pull request. For Python typing language design, use the
[Python Typing Discourse](https://discuss.python.org/c/typing/32).

This is an independent resource, not an official Python project.
