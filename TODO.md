# TODO

## 1. Fix mypy benchmark accuracy (HIGH PRIORITY)

**Goal:** Fix two bugs that cause mypy's benchmark times to be wildly inaccurate.

**Root cause (confirmed via local experiments):**

**Bug A: `run_checker()` never checks the process return code.**
In `typecheck_benchmark/daily_runner.py:607-625`, the function always returns `ok: True` unless timeout or OOM. mypy exits with code 2 (fatal error) but the benchmark reports it as a successful run.

**Bug B: mypy hits early fatal errors and bails out without type-checking.**
When mypy encounters structural issues (duplicate module names from test `conftest.py` files, syntax errors in test fixtures), it prints `errors prevented further checking` and exits immediately. The benchmark config (`files = src`) doesn't exclude test directories, so mypy discovers these problematic files and stops.

**Impact — 3 packages with bogus results (latest ubuntu run):**
| Package | mypy (bogus) | pyrefly (real) | ty (real) | mypy (real, tested locally) |
|---------|---:|---:|---:|---:|
| prefect | 0.5s | 4.8s | 3.4s | 7.5s |
| ComfyUI | 0.3s | 3.9s | 2.8s | ? |
| homeassistant | 0.4s | 12.3s | 11.0s | ? |

**Fixes needed in `typecheck_benchmark/daily_runner.py`:**

1. **Check return code in `run_checker()`** (line ~621): If `result["returncode"] != 0`, set `ok: False` and capture stderr as `error_message`. Type checkers finding type errors also return non-zero, so we need to distinguish fatal errors from normal type errors:
   - mypy: return code 2 = fatal error (not type errors, which are code 1)
   - pyright: non-zero can mean type errors found (not fatal)
   - Simplest approach: always mark as `ok: True` for non-timeout/OOM (current behavior) BUT capture stderr and check for `"errors prevented further checking"` in mypy output → mark as `ok: False`

2. **Add `--no-incremental` to mypy invocation** (line ~586): Prevents `.mypy_cache` from affecting results between runs. Change:
   ```python
   cmd = [sys.executable, "-m", "mypy", "--config-file", str(config_path)]
   ```
   to:
   ```python
   cmd = [sys.executable, "-m", "mypy", "--no-incremental", "--config-file", str(config_path)]
   ```

3. **Add `--exclude tests` to mypy dummy config** (function `_write_dummy_mypy_config`, line ~508): This avoids mypy tripping on duplicate `conftest.py` modules and test fixture syntax errors. Other checkers handle these gracefully; mypy does not. Update to:
   ```python
   def _write_dummy_mypy_config(
       package_path: Path, check_paths: list[str] | None = None,
   ) -> Path:
       config_path = package_path / "mypy.benchmark.ini"
       with open(config_path, "w", encoding="utf-8") as f:
           f.write("[mypy]\n")
           if check_paths:
               f.write(f"files = {', '.join(check_paths)}\n")
           f.write("exclude = (?x)(\n    tests/\n    | test_\n  )\n")
       return config_path
   ```

4. **Detect and flag early-exit in results**: After running mypy, check stderr for `"errors prevented further checking"`. If present, mark `ok: False` with `error_message: "Fatal error: errors prevented further checking"`.

**Files:**
- `typecheck_benchmark/daily_runner.py` — all fixes go here

---

## 2. Restructure dashboard routes

**Goal:** Change URL structure from the current layout to a cleaner `/benchmark/lsp` and `/benchmark/typechecking` hierarchy.

**Current routes (on `python-type-checking.com`):**
| URL path | Dashboard |
|----------|-----------|
| `/` | Main package coverage |
| `/prioritized/` | Prioritized package coverage |
| `/historical_data/coverage-trends.html` | Coverage trends (all) |
| `/prioritized/historical_data/coverage-trends.html` | Coverage trends (prioritized) |
| `/lsp/benchmark/` | LSP benchmark |
| `/typecheck_benchmark/` | Typecheck timing benchmark |

**Target routes:**
| URL path | Dashboard |
|----------|-----------|
| `/` | Main package coverage (unchanged) |
| `/prioritized/` | Prioritized package coverage (unchanged) |
| `/historical_data/coverage-trends.html` | Coverage trends (unchanged) |
| `/prioritized/historical_data/coverage-trends.html` | Coverage trends (unchanged) |
| `/benchmark/lsp/` | LSP benchmark |
| `/benchmark/typechecking/` | Typecheck timing benchmark |

**Recommended approach — symlinks or redirects, not file moves:**

Moving the actual directories would break all internal imports in the Python code (`from lsp.benchmark.daily_runner import ...`, `from typecheck_benchmark import ...`). The best approach is:

**Option A: Directory restructure for web assets only (recommended)**
1. Create a `benchmark/` directory at the repo root
2. Move only the web-facing files (HTML, CSS, scripts, results) into `benchmark/lsp/` and `benchmark/typechecking/`
3. Keep the Python source modules where they are (`lsp/benchmark/`, `typecheck_benchmark/`)
4. Update the Python runners' `--output` paths in CI workflows to point to the new locations
5. Update all cross-page links in HTML files

**Option B: GitHub Pages redirects**
1. Keep files where they are
2. Add redirect HTML files at the new paths that redirect to the old paths
3. Simpler but results in two working URLs for each page

**Files to update (Option A):**
- Move `lsp/benchmark/index.html` → `benchmark/lsp/index.html`
- Move `lsp/benchmark/styles/` → `benchmark/lsp/styles/`
- Move `lsp/benchmark/scripts/` → `benchmark/lsp/scripts/`
- Move `lsp/benchmark/results/` → `benchmark/lsp/results/`
- Move `typecheck_benchmark/index.html` → `benchmark/typechecking/index.html`
- Move `typecheck_benchmark/styles/` → `benchmark/typechecking/styles/`
- Move `typecheck_benchmark/scripts/` → `benchmark/typechecking/scripts/`
- Move `typecheck_benchmark/results/` → `benchmark/typechecking/results/`
- Update `tsconfig.json` include paths
- Update `.gitignore` compiled JS paths
- Update all 4 deploy workflow `file_pattern` and `--output` paths
- Update back-links in `lsp/benchmark/index.html` and `typecheck_benchmark/index.html` (`href="/index.html"`)
- Add redirect HTML at old paths (`lsp/benchmark/index.html`, `typecheck_benchmark/index.html`) for bookmarked URLs

**Cross-page links to update:**
- `lsp/benchmark/index.html:37` — `<a href="/index.html">← Back to Type Coverage</a>`
- `typecheck_benchmark/index.html:37` — `<a href="/index.html">← Back to Type Coverage</a>`
- Any links from the main `index.html` or `prioritized/index.html` pointing to benchmark pages

---

## 3. Finish TypeScript migration for remaining inline JS

**Status: IN PROGRESS**

**Goal:** Extract inline `<script>` blocks from 4 HTML files into separate `.ts` files, following the same pattern used for `lsp-benchmark.ts` and `typecheck-benchmark.ts`.

**What's been done:**
- Created all 4 `.ts` files with type annotations and `export {}` for module isolation:
  - `scripts/main.ts`
  - `prioritized/scripts/main.ts`
  - `historical_data/scripts/coverage-trends.ts`
  - `prioritized/historical_data/scripts/coverage-trends.ts`
- Updated all 4 HTML files to use `<script type="module" src="scripts/....js">` instead of inline scripts
- Updated `tsconfig.json` include array with the 4 new glob patterns
- Updated `.gitignore` with the 4 new compiled JS paths

**What still needs to be done:**
1. Run `npm run build` to compile TypeScript and fix any compilation errors
2. Run `npm run check` to verify no type errors
3. Start a local web server (`python -m http.server 8000`) and verify all 6 HTML pages render correctly:
   - `http://localhost:8000/index.html` — main coverage table
   - `http://localhost:8000/prioritized/index.html` — prioritized coverage table
   - `http://localhost:8000/historical_data/coverage-trends.html` — coverage trends charts
   - `http://localhost:8000/prioritized/historical_data/coverage-trends.html` — prioritized coverage trends
   - `http://localhost:8000/lsp/benchmark/index.html` — LSP benchmark dashboard
   - `http://localhost:8000/typecheck_benchmark/index.html` — typecheck benchmark dashboard
4. **Known issue:** A pre-commit hook has been reverting `type="module"` from HTML script tags. If this happens, the hook needs to be investigated and fixed, or the approach needs to change (e.g., IIFE wrapping instead of ES modules).

**Files to migrate:**

| HTML file | Inline JS lines | Target TS file |
|-----------|---:|----------------|
| `index.html` | ~200 | `scripts/main.ts` |
| `prioritized/index.html` | ~198 | `prioritized/scripts/main.ts` |
| `historical_data/coverage-trends.html` | ~341 | `historical_data/scripts/coverage-trends.ts` |
| `prioritized/historical_data/coverage-trends.html` | ~354 | `prioritized/historical_data/scripts/coverage-trends.ts` |

---

## 4. Address PR feedback on initial TypeScript migration

**PR branch:** `add-typescript-ci`

### 4a. Add `--force` to git-auto-commit add_options

**Problem:** The compiled `.js` files are in `.gitignore` but need to be committed on `published-report`. If the files ever become untracked on that branch (e.g., after `git rm --cached` or branch reset), `git add` would refuse to stage them because `.gitignore` blocks it.

**Fix:** Add `add_options: '--force'` to all `stefanzweifel/git-auto-commit-action@v4` steps that commit compiled JS:

- `.github/workflows/lsp-benchmark.yml` — add `add_options: '--force'` to the auto-commit step
- `.github/workflows/typecheck-benchmark.yml` — add `add_options: '--force'` to the auto-commit step

Example:
```yaml
      - name: Commit and Push Results
        uses: stefanzweifel/git-auto-commit-action@v4
        with:
          commit_message: "Update LSP benchmark results [skip ci]"
          branch: published-report
          file_pattern: 'lsp/benchmark/results/*.json lsp/benchmark/scripts/lsp-benchmark.js'
          add_options: '--force'
```

### 4b. Remove redundant `actions/setup-node@v4` steps

**Problem:** The lsp-benchmark and typecheck-benchmark workflows already set up Node.js 20 earlier in the job (for installing Pyright). The second `actions/setup-node@v4` step added for the TypeScript build is redundant.

**Fix:** Remove the duplicate setup-node steps and keep only the `npm ci && npm run build` commands:

- `.github/workflows/lsp-benchmark.yml` — remove lines 132–135 (the second `Setup Node.js for TypeScript build` step), keep the `Build and validate frontend` run step
- `.github/workflows/typecheck-benchmark.yml` — remove lines 126–129 (the second `Setup Node.js for TypeScript build` step), keep the `Build and validate frontend` run step

Note: The `main.yml` and `prioritized.yaml` workflows do NOT already have Node.js setup, so their setup-node steps should remain.
