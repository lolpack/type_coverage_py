# Pyrefly False Positive Analysis

This tool analyzes pyrefly false positives across popular Python packages and generates verified minimal reproductions with sandbox links.

## Features

- Runs pyright and pyrefly on multiple Python packages
- Identifies false positives (pyrefly reports error, pyright does not)
- Uses Claude CLI to create minimal standalone reproductions
- Generates sandbox URLs for easy browser-based verification
- Produces a summary markdown report with all findings

## Requirements

- Python 3.12+
- pyright
- pyrefly
- git
- Claude CLI (for automated repro generation)

## Installation

```bash
pip install -r requirements.txt
```

Make sure you have pyright and pyrefly installed:
```bash
pip install pyright pyrefly
```

## Usage

### Analyze N packages from the default list

```bash
python analyze.py --batch 10
```

This will:
1. Clone and analyze the first 10 packages from the default list
2. Run pyright and pyrefly on each
3. Identify false positives
4. Generate intermediate JSON files
5. Use Claude to create verified repros for top error codes
6. Generate a report with sandbox URLs

### Analyze specific packages

```bash
python analyze.py --packages requests flask django
```

### Re-analyze existing intermediate files

```bash
python analyze.py --analyze-cross output/intermediate_*.json
```

### Options

- `--output, -o DIR`: Output directory (default: output)
- `--timeout, -t SECONDS`: Timeout per type checker (default: 300)
- `--top-n N`: Number of top error codes to create repros for (default: 10)
- `--max-repros-per-code N`: Max repros per error code (default: 3)

## Output

The tool generates:

- `output/intermediate_*.json`: Raw analysis data for each package
- `output/repros/*.py`: Verified minimal reproduction files
- `output/report_*.md`: Summary report with sandbox links

## Example Report

The report includes for each verified reproduction:

1. Error code and package
2. Link to original source in GitHub
3. Error message from pyrefly
4. Sandbox links:
   - Pyrefly sandbox (shows the error)
   - Pyright playground (shows no error)
5. The complete reproduction code

## Default Packages

The tool includes these packages by default:

- requests, flask, django, fastapi
- starlette, uvicorn, aiohttp, httpx
- pydantic, rich, click, trio

## Files

- `analyze.py`: Main analysis script
- `sandbox_links.py`: Utility for generating pyrefly/pyright sandbox URLs
- `requirements.txt`: Python dependencies
