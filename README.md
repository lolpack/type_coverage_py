# type_coverage_py ✅

Calculate the Type Coverage for top Python packages. This analysis aims to determine how well typed popular Python packages are and compares the coverage of exported APIs and the whole package (including tests). [PEP-561](https://peps.python.org/pep-0561/) defines the creation, location and MRO of Python type hints which can be inline with the code or stored as separate stubs (.pyi files). Indicate that your package is type checked, by including a `py.typed` file in distribution.

## Coverage Reports

- Daily coverage calculator: [https://python-type-checking.com](https://python-type-checking.com/)
- Coverage Trends: [https://python-type-checking.com/historical_data/coverage-trends.html](https://python-type-checking.com/historical_data/coverage-trends.html)
- Prioritized Coverage Reports: [https://python-type-checking.com/prioritized/](https://python-type-checking.com/prioritized/)
- LSP Performance Benchmark: [https://python-type-checking.com/lsp/benchmark/](https://python-type-checking.com/lsp/benchmark/)

- Prioritized list of packages included in analysis with Pyright: https://github.com/lolpack/type_coverage_py/blob/main/included_packages.txt
- Coverage trends for prioritized list: [https://python-type-checking.com/prioritized/historical_data/coverage-trends.html](https://python-type-checking.com/prioritized/historical_data/coverage-trends.html)

Top pypi packages pulled from this project [https://github.com/hugovk/top-pypi-packages](https://github.com/hugovk/top-pypi-packages)

## Methodology

This section outlines how the script analyzes Python packages, checks for typeshed availability, and calculates type coverage. The process involves three key steps: package extraction, typeshed check, and type coverage calculation.

### **Package Extraction**

- **Downloading**: The script downloads the source distribution of each selected package from PyPI and extracts it into a temporary directory.
- **File Extraction**: It identifies and extracts all Python files (`.py`) and type stub files (`.pyi`) from the package for analysis.

### **Typeshed Check**

- **Typeshed Directory**: The script checks if a corresponding stub exists in the `typeshed` repository, which contains type stubs for standard library modules and popular third-party packages.
- **Existence Check**: If a typeshed stub exists, it is recorded as `HasTypeShed: Yes`; otherwise, it is marked as `HasTypeShed: No`.
- **Typeshed Merge**: Pull available typestubs from typeshed with the same package name. If a local `.pyi` file exists, prefer it over typeshed.

### **Stubs Package Check**

If a package has a corresponding stubs package (`[package name]-stubs`), then we pull the stubs package and merge it with the source files the same way we would for typeshed stubs. This happens before typeshed stubs are merged, so in any conflict the stubs package would take priority.

If a stubs package exists, it is recorded as `HasStubsPackage: Yes`; otherwise, it is marked as `HasStubsPackage: No`.

### **Stubs package Check**

- Check pypi for a package called {package}-stubs like https://pypi.org/project/pandas-stubs/ for stubs hosted outside of typeshed.

### **Type Coverage Calculation**

- **Parameter Coverage**:
  - The script analyzes function definitions in the extracted files and calculates the percentage of function parameters that have type annotations.
  - **Handling `.pyi` files**: If a function is defined in a `.pyi` file, it takes precedence over any corresponding function in a `.py` file. The parameter counts from `.pyi` files will overwrite those from `.py` files for the same function.
  - The formula used:
  $$\[
  \text{Parameter Coverage} = \left( \frac{\text{Number of Parameters with Type Annotations}}{\text{Total Number of Parameters}} \right) \times 100
  \]$$

- **Return Type Coverage**:
  - The script calculates the percentage of functions that have return type annotations.
  - **Handling `.pyi` files**: Similar to parameter coverage, if a function is defined in a `.pyi` file, the return type annotations from the `.pyi` file will overwrite those from any corresponding `.py` file.
  - The formula used:
  $$\[
  \text{Return Type Coverage} = \left( \frac{\text{Number of Functions with Return Type Annotations}}{\text{Total Number of Functions}} \right) \times 100
  \]$$

- **Skipped Files**:
  - Files that cannot be processed due to syntax or encoding errors are skipped, and the number of skipped files is recorded.

- **Overall Coverage**:
  - The script calculates and returns the overall coverage, combining parameter coverage and return type coverage. The maximum number of skipped files between the parameter and return type calculations is recorded.

This methodology ensures an accurate and detailed analysis of type coverage for popular Python packages, taking into account the presence of type stub files (`.pyi`) which are prioritized over implementation files (`.py`) for the same functions.

### Pyright Stats Integration
- **Exposed package APIs:** Pyright will calculatue coverage for stubs and packages installed with pip or other package managers looking at just the exposed APIs. Include `py.typed` in your package to calculate coverage: `pyright --ignoreexternal --verifytypes {package}
- **Pyright Analysis:** The script can optionally run Pyright to gather additional type information statistics for each package.
- **Stats Structure:** Pyright stats include counts of known, ambiguous, and unknown types for each package.

## Branching Strategy

- **`main`** — Development branch. All code changes (Python, TypeScript, HTML, CSS, workflow YAML) are made here.
- **`published-report`** — Deploy-only branch. Contains only the generated site files (HTML, CSS, compiled JS, data JSON) served by GitHub Pages. Never commit code changes directly to this branch.

All four CI workflows check out `main` for code, fetch accumulated data from `published-report`, run their task, build the frontend, and deploy results back to `published-report` via a shallow-clone push. This one-way flow ensures workflow YAML always comes from `main` and prevents build artifacts (e.g. `node_modules`, `.pyright_output`) from being committed to the deploy branch.

## GitHub Actions Workflows

### Daily Package Data Update (`main.yml`)
Runs daily at 8 AM EST. Analyzes the top 2000 PyPI packages for type coverage using Pyright and typeshed stubs. Generates `package_report.json` and a daily historical snapshot in `historical_data/json/`. Deploys data files plus all site assets (HTML, JS, CSS) to `published-report`.

### Daily Prioritized List Runner (`prioritized.yaml`)
Runs daily at 10 AM EST. Analyzes a curated list of packages (defined in `included_packages.txt`) with Pyright stats. Generates `prioritized/package_report.json` and daily snapshots in `prioritized/historical_data/json/`. Deploys prioritized data and site files to `published-report`.

### Daily LSP Benchmark (`lsp-benchmark.yml`)
Runs daily at 3 AM UTC on Ubuntu and Windows, weekly on Tuesdays for macOS. Benchmarks LSP performance (time-to-first-diagnostic, completions, hover) across Pyright, Pyrefly, ty, and Zuban on the prioritized package list. Each OS produces a separate results JSON. Deploys to `published-report` with retry logic for concurrent matrix job pushes.

### Daily Type Checker Timing Benchmark (`typecheck-benchmark.yml`)
Runs daily at 5 AM UTC on Ubuntu and Windows, weekly on Wednesdays for macOS. Measures full type-checking time across Pyright, Pyrefly, ty, mypy, and Zuban on packages with install configurations. Each OS produces a separate results JSON. Deploys to `published-report` with retry logic for concurrent matrix job pushes.

## Development

Clone the typeshed repo into the root of the project

`git clone git@github.com:python/typeshed.git`

Call the main function with the top N packages to analyze, the max is 8,000.

`python main.py 100`

Alternatively call with a single package

`python main.py --package-name flask`

Analyze the top N packages and generate both JSON and HTML reports:

`python main.py 100 --write-json --write-html`

Run daily command for Github Actions: Generate historical coverage report to create the file historical_data/coverage-trends.html

`python main.py 2000 --create-daily`

Generate report from a specific list of packages

`python main.py --pyright-stats --package-list included_packages.txt --write-json --write-html --output-list-only`

Run daily command for prioritized list:

`python main.py --package-list included_packages.txt  --archive-prioritized`

### Type check the project (of course!)

We use [Pyrefly](https://pyrefly.org/) to check the project. You can also use the accompanying IDE extension in [VSCode](https://marketplace.visualstudio.com/items?itemName=meta.pyrefly).

`$ pyrefly check`

