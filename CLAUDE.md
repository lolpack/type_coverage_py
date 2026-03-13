# Claude Code Instructions for type_coverage_py

## CRITICAL: Always Activate Virtual Environment First!

Before running ANY Python command, terminal command, or pip install:

```bash
source .venv/bin/activate
```

Then verify with: `which python` (should show `.venv/bin/python`)

## Quick Reference

| Task | Command (after activating venv) |
|------|--------------------------------|
| Run tests | `python -m pytest tests/ -v` |
| Python type check | `pyrefly check` |
| TypeScript type check | `npm run check` |
| Install Python deps | `pip install -r requirements.txt` |
| Install TS deps | `npm ci` |
| Run main | `python main.py <num_packages>` |
| Run LSP benchmark | `python -m lsp.benchmark.daily_runner --packages 5 --runs 3` |

## Before Committing: Always Run All Checks

Before every commit, run ALL of these and fix any failures:

```bash
source .venv/bin/activate
python -m pytest tests/ -v    # All tests must pass
pyrefly check                 # 0 errors required
npm run check                 # TypeScript must pass (run npm ci first if needed)
```

Do NOT commit if any check fails. Fix the issue first.

## Project Overview

This project analyzes Python type coverage across popular PyPI packages and benchmarks LSP performance.

## Key Rules

1. **Virtual environment**: ALWAYS `source .venv/bin/activate` first
2. **Type checker**: Use `pyrefly check` (not pyright/mypy for linting)
3. **Typeshed**: Don't modify files in `typeshed/` - it's a git submodule
4. **Type annotations**: Required on all functions
5. **Python version**: 3.12

## Architecture: Shared Package Configuration

Both benchmarks (typecheck and LSP) use `typecheck_benchmark/install_envs.json` as the single source of truth for:
- Which packages to benchmark (github_url)
- How to install dependencies (install, deps, install_env fields)
- Which paths to check (check_paths)

When adding a new package, add it to `install_envs.json` — it will automatically be available to both benchmarks. Do NOT maintain separate package lists.

The LSP benchmark's `lsp/benchmark/daily_runner.py` loads packages via `load_packages_from_install_envs()` and installs deps via `typecheck_benchmark.daily_runner.install_deps()`.

## LSP Benchmark

- `lsp/lsp_benchmark.py` — Core benchmark logic (go-to-definition accuracy/latency)
- `lsp/benchmark/daily_runner.py` — Orchestration: clone, install deps, run benchmarks, save results
- Import-line filter: Results pointing to `import`/`from...import` in the same file are rejected as invalid
- `--install-deps` flag installs each package's dependencies before benchmarking (uses install_envs.json config)

## CI Workflows

- `.github/workflows/lsp-benchmark.yml` — Daily LSP benchmark (prod)
- `.github/workflows/lsp-benchmark-install-deps.yml` — Test workflow for install-deps feature branch
- `.github/workflows/typecheck-benchmark.yml` — Daily typecheck benchmark
- Test workflows trigger on push to their feature branch; delete them after merging
