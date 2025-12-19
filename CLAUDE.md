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
| Run main | `python main.py <num_packages>` |
| Run LSP benchmark | `python -m lsp.benchmark.daily_runner --packages 5 --runs 3` |

## Project Overview

This project analyzes Python type coverage across popular PyPI packages and benchmarks LSP performance.

## Key Rules

1. **Virtual environment**: ALWAYS `source .venv/bin/activate` first
2. **Type checker**: Use `pyrefly check` (not pyright/mypy for linting)
3. **Typeshed**: Don't modify files in `typeshed/` - it's a git submodule
4. **Type annotations**: Required on all functions
5. **Python version**: 3.12
