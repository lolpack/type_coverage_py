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
```

**Dashboard:** [https://python-type-checking.com/typecheck_benchmark/](https://python-type-checking.com/typecheck_benchmark/)

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
