# Running Benchmarks Locally

Automated macOS and Windows benchmarks have been discontinued. Ubuntu benchmarks continue to run daily via CI. Use this guide to run benchmarks locally on macOS or Windows.

## Prerequisites

- Python 3.12
- Node.js 20+ (for Pyright)
- Type checkers installed: `pip install pyrefly ty mypy zuban` and `npm install -g pyright`

## Setup

```bash
git clone git@github.com:lolpack/type_coverage_py.git
cd type_coverage_py
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

## Type Checker Timing Benchmark

Measures wall-clock execution time and peak memory when type checking popular Python packages.

**Run all packages with all checkers (default: 5 runs + 1 warmup):**

```bash
python -m typecheck_benchmark
```

**Run with specific options:**

```bash
# Specific checkers
python -m typecheck_benchmark --checkers pyrefly pyright

# Specific packages
python -m typecheck_benchmark --package-names requests flask

# Limit number of packages
python -m typecheck_benchmark --packages 10

# Custom output directory
python -m typecheck_benchmark --output typecheck_benchmark/results/local-myplatform

# Adjust runs and warmup
python -m typecheck_benchmark --runs 3 --warmup 1

# Benchmark a local project directory
python -m typecheck_benchmark --local /path/to/your/project --checkers pyrefly

# Skip the runs with the opposite return type inference setting
python -m typecheck_benchmark --no-alternate-inference
```

Each checker runs in its default configuration. Pyrefly, ty and Zuban can switch
return type inference, so each of them also runs with the opposite of its default:
Pyrefly and Zuban with it off, ty with it on. Pyright can't turn it off, and mypy
never infers return types. In the results JSON, `metrics` holds the default
configurations, `alternate_metrics` the opposite setting, and
`return_type_inference_default` says which setting each checker's default is.

**Dashboard:** [https://python-type-checking.com/typecheck_benchmark/](https://python-type-checking.com/typecheck_benchmark/)

### Interpreter-query audit

**\* The benchmark includes process startup and Python interpreter queries in its
wall-clock timings.** This cost is not subtracted, and can account for a substantial
share of the time for small packages. Each measured run starts a fresh checker
process, so discarding a warmup does not remove subsequent interpreter queries.

Verified locally on November 19, 2026, after upgrading all five checkers to the
latest releases available from PyPI and npm, using macOS 14.7.4 and Python 3.12.11:

| Checker | Version | Package-environment flag | Interpreter launches per run |
|---------|---------|--------------------------|------------------------------|
| Pyrefly | 1.5.0 | `--python-interpreter-path <venv>/bin/python` | 1 |
| Pyright | 1.1.414 | `--pythonpath <venv>/bin/python` | 2 |
| mypy | 2.4.1 | `--python-executable <venv>/bin/python` | 1 |
| ty | 0.0.107 | `--python <venv>` | 0 observed |
| Zuban | 0.10.2 | `--python-executable <venv>/bin/python` | 0 observed |

These are observations for the runner's per-package virtual environments, not
universal claims about every configuration or historical benchmark version.

- [Pyrefly](https://pyrefly.org/en/docs/configuration/#skip-interpreter-query)
  queries Python for version, platform, and import paths. Its
  `--skip-interpreter-query` control eliminated the query when those settings
  were supplied explicitly. The regular benchmark keeps discovery enabled.
- [Pyright](https://github.com/microsoft/pyright/blob/main/docs/import-resolution.md#configuring-your-python-environment)
  can inspect a configured virtual-environment directory, but the runner passes
  an interpreter path. We observed separate version and search-path queries.
- [mypy](https://mypy.readthedocs.io/en/stable/command_line.html#cmdoption-mypy-python-executable)
  queries the separate package interpreter for import paths. Its installed
  `mypy/modulefinder.py:get_search_dirs` uses in-process information when the
  selected interpreter is `sys.executable`, so that configuration differs.
- [ty](https://docs.astral.sh/ty/modules/#python-environment) and
  [Zuban](https://docs.zubanls.com/en/latest/usage.html) accept an environment or
  interpreter location; this does not imply launching it. Neither launched the
  instrumented interpreter for this virtual-environment layout.

To upgrade locally and reproduce on macOS or Linux:

```bash
source .venv/bin/activate
python -m pip install --upgrade pyrefly ty mypy zuban
# Use the native npm Pyright CLI, as CI does, without a Python launcher.
npm install --prefix .venv/pyright-node --no-package-lock pyright@latest
export PATH="$PWD/.venv/pyright-node/node_modules/.bin:$PATH"
python -m typecheck_benchmark.interpreter_probe --output /tmp/interpreter-audit.json
```

The probe uses the real runner's commands and generated configs with a temporary
package environment. It logs arguments to that environment's Python aliases,
alternates normal and artificially delayed queries, and discards one warmup for
each condition. A typed dependency verifies environment discovery. A Pyrefly
skip-query control supplies equivalent environment settings explicitly. The JSON
records versions, commands, query arguments, exit codes, and timing samples.
Injected delays establish that queries fall inside the measured process; they
are not estimates of normal overhead. These instrumented timings must not be
published as package benchmark results.

Interpreter queries supply environment details directly from the selected Python,
such as import search paths, version, and platform. These help checkers find
installed packages and select version-dependent types. The tradeoff is an extra
process launch and its latency. Reading environment metadata can avoid that
launch, but relies on recognizing the installation layout; unusual environments
or search paths may need explicit configuration. Both approaches can resolve a
standard virtual environment correctly. Query counts alone do not establish
type-checking correctness.

## LSP Benchmark

Measures `textDocument/definition` (Go to Definition) latency and accuracy across Python language servers.

**Run all packages with all LSPs (default: 100 runs):**

```bash
python -m lsp.benchmark.daily_runner
```

**Run with specific options:**

```bash
# Specific checkers
python -m lsp.benchmark.daily_runner --checkers pyrefly pyright

# Limit number of packages
python -m lsp.benchmark.daily_runner --packages 5

# Custom number of runs
python -m lsp.benchmark.daily_runner --runs 50

# Custom output directory
python -m lsp.benchmark.daily_runner --output lsp/benchmark/results/local-myplatform
```

**Dashboard:** [https://python-type-checking.com/lsp/benchmark/](https://python-type-checking.com/lsp/benchmark/)

## CLI Reference

| Flag | Typecheck | LSP | Description |
|------|:---------:|:---:|-------------|
| `--packages N` | Y | Y | Max number of packages to benchmark |
| `--package-names a b` | Y | N | Specific package names |
| `--checkers a b` | Y | Y | Which type checkers/LSPs to run |
| `--runs N` | Y | Y | Number of measured runs (default: 5 / 100) |
| `--warmup N` | Y | N | Warmup runs to discard (default: 1) |
| `--output DIR` | Y | Y | Output directory for results |
| `--os-name NAME` | Y | Y | OS label for output filename |
| `--timeout N` | Y | N | Timeout per checker in seconds |
| `--local PATH` | Y | N | Benchmark a local directory |
| `--no-alternate-inference` | Y | N | Skip the runs with the opposite return type inference setting |
