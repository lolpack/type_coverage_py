# Project: type_coverage_py

## Environment Setup
- **Always activate the virtual environment first** before running any Python commands:
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```
- The project uses Python 3.12

## Type Checking
- **Use Pyrefly** for type checking (not Pyright):
  ```bash
  pyrefly check
  ```
- Configuration is in `pyrefly.toml`
- The `typeshed/` directory is excluded from type checking

## Testing
- **Use pytest** to run tests:
  ```powershell
  python -m pytest tests/ -v
  ```
- Tests are in the `tests/` directory
- The `typeshed/` directory is ignored in pytest (configured in `pytest.ini`)
- Test files follow the pattern `test_*.py`

## Project Structure
- `analyzer/` - Core analysis modules (coverage calculator, report generator, etc.)
- `coverage_sources/` - Type coverage data sources
- `lsp/` - LSP benchmarking tools
  - `lsp/benchmark.py` - Main LSP benchmark module
  - `lsp/benchmark/` - Daily runner and web dashboard
- `prioritized/` - Prioritized package data and reports
- `historical_data/` - Historical coverage data and graphs
- `typeshed/` - Git submodule (Python typeshed), excluded from analysis

## Key Dependencies
- `jinja2` - Template rendering
- `requests` - HTTP client
- `pyright` - Type checking (also used programmatically)
- `pyrefly` - Type checking
- `tabulate` - Table formatting
- `pytest` - Testing

## Coding Standards
- Use type annotations on all functions
- Use `from __future__ import annotations` for modern type syntax
- Follow PEP 8 style guidelines
- Use TypedDict for complex dictionary structures
- Add docstrings with Args/Returns sections

## GitHub Actions
- Workflows are in `.github/workflows/`
- `main.yml` - Daily package data update
- `prioritized.yaml` - Prioritized package analysis
- `lsp-benchmark.yml` - Daily LSP benchmarks
- CI runs on `published-report` branch

## Common Commands
```powershell
# Activate venv
.\.venv\Scripts\Activate.ps1

# Type check
pyrefly check

# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_lsp_benchmark_daily_runner.py -v

# Run main script
python main.py <num_packages> --create-daily

# Run LSP benchmark
python -m lsp.benchmark.daily_runner --packages 5 --runs 3
```

## Notes
- The `typeshed/` directory is a git submodule - don't modify files there
- Package data comes from `top-pypi-packages-30-days.min.json`
- Results are published to `published-report` branch
- Web dashboards are in `index.html` and `lsp/benchmark/index.html`
