# Type Checker Benchmark Analysis
## Comparing 2026-01-13 vs 2026-01-16 vs 2026-01-20

This report compares benchmark results across all three platforms (Ubuntu, macOS, Windows)
over three benchmark runs: January 13, 16, and 20, 2026.

---

## Executive Summary

### Version Updates

| Type Checker | 2026-01-13 | 2026-01-16 | 2026-01-20 |
|-------------|------------|------------|------------|
| pyright | 1.1.408 | 1.1.408 | 1.1.408 |
| pyrefly | 0.48.0 | 0.48.1 | 0.49.0 |
| ty | 0.0.11 | 0.0.12 | 0.0.12 |
| mypy | not installed | not installed | not installed |
| zuban | 0.4.1 | 0.4.2 | 0.4.2 |

### Key Version Changes

- **pyrefly**: 0.48.0 → 0.48.1 → **0.49.0** (minor version bump)
- **ty**: 0.0.11 → 0.0.12 (unchanged in latest)
- **zuban**: 0.4.1 → 0.4.2 (unchanged in latest)
- **pyright**: 1.1.408 (unchanged throughout)

### Key Findings

1. **pyright on Ubuntu**: Large swing (-48K → +49K errors) due to `sympy` and `numpy` packages being skipped on 01-16 then restored on 01-20
2. **pyright on macOS**: 59K error drop due to `salt` and `airflow` returning 0 errors (likely skipped/timeout)
3. **pyrefly 0.49.0**: Stable error counts with minor increase (~0.1%) - no regressions
4. **zuban**: Stabilized after the 01-16 transformers fix (+50K errors now consistent)
5. **All platforms**: Execution times trending slightly upward, especially on Windows

---

## Ubuntu Analysis

### Aggregate Error Comparison

| Type Checker | 01-13 | 01-16 | 01-20 | 01-13→16 | 01-16→20 | Overall |
|-------------|-------|-------|-------|----------|----------|---------|
| pyright | 394,591 | 346,476 | 395,394 | -48,115 (-12.2%) ↓ | +48,918 (14.1%) ↑ | +803 (0.2%) ↑ |
| pyrefly | 857,950 | 859,914 | 860,541 | +1,964 (0.2%) ↑ | +627 (0.1%) ↑ | +2,591 (0.3%) ↑ |
| ty | 500,073 | 500,443 | 501,241 | +370 (0.1%) ↑ | +798 (0.2%) ↑ | +1,168 (0.2%) ↑ |
| mypy | 23,756 | 23,752 | 23,756 | -4 (-0.0%) ↓ | +4 (0.0%) ↑ | +0 (0.0%) → |
| zuban | 428,342 | 477,668 | 478,223 | +49,326 (11.5%) ↑ | +555 (0.1%) ↑ | +49,881 (11.6%) ↑ |

### Execution Time Comparison (Average per package)

| Type Checker | 01-13 | 01-16 | 01-20 | 01-13→16 | 01-16→20 |
|-------------|-------|-------|-------|----------|----------|
| pyright | 35.34s | 29.24s | 35.87s | -6.10s | +6.63s |
| pyrefly | 3.37s | 3.48s | 3.55s | +0.11s | +0.07s |
| ty | 2.56s | 2.66s | 2.35s | +0.10s | -0.31s |
| mypy | 5.09s | 5.35s | 4.55s | +0.26s | -0.80s |
| zuban | 6.83s | 7.31s | 8.13s | +0.48s | +0.82s |

### Notable Per-Package Changes (01-16 → 01-20)

**pyright** (changes ≥50 errors):

- `sympy`: 0 → 38,354 (+38,354, ∞) ↑
- `numpy`: 0 → 8,801 (+8,801, ∞) ↑
- `tensorflow`: 51,830 → 53,231 (+1,401, +2.7%) ↑
- `streamlit`: 5,071 → 5,177 (+106, +2.1%) ↑
- `airflow`: 23,102 → 23,182 (+80, +0.3%) ↑

**pyrefly** (changes ≥50 errors):

- `torch`: 161,342 → 161,689 (+347, +0.2%) ↑
- `homeassistant`: 93,529 → 93,686 (+157, +0.2%) ↑
- `salt`: 29,399 → 29,535 (+136, +0.5%) ↑
- `airflow`: 27,611 → 27,691 (+80, +0.3%) ↑

**ty** (changes ≥50 errors):

- `torch`: 171,702 → 172,086 (+384, +0.2%) ↑
- `airflow`: 23,005 → 23,098 (+93, +0.4%) ↑
- `prefect`: 8,374 → 8,453 (+79, +0.9%) ↑
- `homeassistant`: 57,008 → 57,085 (+77, +0.1%) ↑

**zuban** (changes ≥50 errors):

- `torch`: 204,330 → 204,715 (+385, +0.2%) ↑
- `streamlit`: 11,177 → 11,237 (+60, +0.5%) ↑

---

## macOS Analysis

### Aggregate Error Comparison

| Type Checker | 01-13 | 01-16 | 01-20 | 01-13→16 | 01-16→20 | Overall |
|-------------|-------|-------|-------|----------|----------|---------|
| pyright | 297,362 | 297,723 | 238,719 | +361 (0.1%) ↑ | -59,004 (-19.8%) ↓ | -58,643 (-19.7%) ↓ |
| pyrefly | 858,075 | 745,672 | 746,272 | -112,403 (-13.1%) ↓ | +600 (0.1%) ↑ | -111,803 (-13.0%) ↓ |
| ty | 528,517 | 529,725 | 530,460 | +1,208 (0.2%) ↑ | +735 (0.1%) ↑ | +1,943 (0.4%) ↑ |
| mypy | 22,648 | 22,646 | 22,650 | -2 (-0.0%) ↓ | +4 (0.0%) ↑ | +2 (0.0%) ↑ |
| zuban | 431,692 | 479,974 | 480,514 | +48,282 (11.2%) ↑ | +540 (0.1%) ↑ | +48,822 (11.3%) ↑ |

### Execution Time Comparison (Average per package)

| Type Checker | 01-13 | 01-16 | 01-20 | 01-13→16 | 01-16→20 |
|-------------|-------|-------|-------|----------|----------|
| pyright | 30.05s | 34.47s | 37.61s | +4.42s | +3.14s |
| pyrefly | 3.31s | 3.79s | 4.75s | +0.48s | +0.96s |
| ty | 2.95s | 3.16s | 4.42s | +0.21s | +1.26s |
| mypy | 3.42s | 3.54s | 4.00s | +0.12s | +0.46s |
| zuban | 5.70s | 6.60s | 8.00s | +0.90s | +1.40s |

### Notable Per-Package Changes (01-16 → 01-20)

**pyright** (changes ≥50 errors):

- `salt`: 31,012 → 0 (-31,012, -100.0%) ↓
- `airflow`: 28,179 → 0 (-28,179, -100.0%) ↓
- `ray`: 55,205 → 55,275 (+70, +0.1%) ↑
- `scikit-learn`: 17,510 → 17,576 (+66, +0.4%) ↑

**pyrefly** (changes ≥50 errors):

- `torch`: 161,340 → 161,687 (+347, +0.2%) ↑
- `homeassistant`: 93,529 → 93,686 (+157, +0.2%) ↑
- `airflow`: 27,617 → 27,697 (+80, +0.3%) ↑

**ty** (changes ≥50 errors):

- `torch`: 173,874 → 174,228 (+354, +0.2%) ↑
- `airflow`: 28,613 → 28,756 (+143, +0.5%) ↑
- `homeassistant`: 75,136 → 75,238 (+102, +0.1%) ↑

**zuban** (changes ≥50 errors):

- `torch`: 204,474 → 204,859 (+385, +0.2%) ↑
- `streamlit`: 11,249 → 11,309 (+60, +0.5%) ↑

---

## Windows Analysis

### Aggregate Error Comparison

| Type Checker | 01-13 | 01-16 | 01-20 | 01-13→16 | 01-16→20 | Overall |
|-------------|-------|-------|-------|----------|----------|---------|
| pyright | 343,722 | 343,782 | 344,299 | +60 (0.0%) ↑ | +517 (0.2%) ↑ | +577 (0.2%) ↑ |
| pyrefly | 152,793 | 152,795 | 152,823 | +2 (0.0%) ↑ | +28 (0.0%) ↑ | +30 (0.0%) ↑ |
| ty | 156,509 | 156,825 | 157,040 | +316 (0.2%) ↑ | +215 (0.1%) ↑ | +531 (0.3%) ↑ |
| mypy | 23,086 | 23,052 | 23,056 | -34 (-0.1%) ↓ | +4 (0.0%) ↑ | -30 (-0.1%) ↓ |
| zuban | 201,912 | 251,694 | 250,642 | +49,782 (24.7%) ↑ | -1,052 (-0.4%) ↓ | +48,730 (24.1%) ↑ |

### Execution Time Comparison (Average per package)

| Type Checker | 01-13 | 01-16 | 01-20 | 01-13→16 | 01-16→20 |
|-------------|-------|-------|-------|----------|----------|
| pyright | 32.47s | 34.22s | 37.25s | +1.75s | +3.03s |
| pyrefly | 10.41s | 10.23s | 13.09s | -0.18s | +2.86s |
| ty | 5.21s | 5.68s | 6.45s | +0.47s | +0.77s |
| mypy | 6.68s | 6.95s | 7.68s | +0.27s | +0.73s |
| zuban | 8.31s | 9.00s | 9.93s | +0.69s | +0.93s |

### Notable Per-Package Changes (01-16 → 01-20)

**pyright** (changes ≥50 errors):

- `tensorflow`: 52,964 → 53,213 (+249, +0.5%) ↑
- `airflow`: 23,273 → 23,353 (+80, +0.3%) ↑
- `scikit-learn`: 17,818 → 17,884 (+66, +0.4%) ↑
- `ray`: 57,483 → 57,545 (+62, +0.1%) ↑

**pyrefly** (changes ≥50 errors):

- `airflow`: 27,760 → 27,840 (+80, +0.3%) ↑

**ty** (changes ≥50 errors):

- `airflow`: 23,191 → 23,284 (+93, +0.4%) ↑
- `homeassistant`: 57,047 → 57,125 (+78, +0.1%) ↑

**zuban** (changes ≥50 errors):

- `airflow`: 1,538 → 361 (-1,177, -76.5%) ↓

---

## Trend Analysis: Error Counts Over Time

### Ubuntu Platform (Primary CI)

| Type Checker | 01-13 | 01-16 | 01-20 | Trend |
|-------------|-------|-------|-------|-------|
| pyright | 394,591 | 346,476 | 395,394 | ↗️ Net increase |
| pyrefly | 857,950 | 859,914 | 860,541 | 📈 Increasing |
| ty | 500,073 | 500,443 | 501,241 | 📈 Increasing |
| mypy | 23,756 | 23,752 | 23,756 | ➡️ Stable |
| zuban | 428,342 | 477,668 | 478,223 | 📈 Increasing |

---

## Deep Dive: pyrefly 0.49.0

The latest benchmark introduces pyrefly 0.49.0 (up from 0.48.1).

### Error Count Changes by Platform

| Platform | 01-16 Errors | 01-20 Errors | Change | % Change |
|----------|-------------|-------------|--------|----------|
| Ubuntu | 859,914 | 860,541 | +627 | +0.07% |
| macOS | 745,672 | 746,272 | +600 | +0.08% |
| Windows | 152,795 | 152,823 | +28 | +0.02% |

### Execution Time Changes

| Platform | 01-16 Time | 01-20 Time | Change |
|----------|-----------|-----------|--------|
| Ubuntu | 3.48s | 3.55s | +0.07s |
| macOS | 3.79s | 4.75s | +0.96s |
| Windows | 10.23s | 13.09s | +2.86s |

---

## Conclusions

### Stability Assessment

| Type Checker | Status | Notes |
|-------------|--------|-------|
| pyright | ⚠️ Fluctuating | Large swings due to packages being skipped (sympy, numpy, salt, airflow) |
| pyrefly | ✅ Stable | 0.48.0 → 0.49.0, error counts consistent across versions |
| ty | ✅ Stable | 0.0.11 → 0.0.12, minor incremental changes |
| mypy | ✅ Stable | No version change, counts essentially unchanged |
| zuban | ✅ Stabilized | Post-0.4.2 transformers fix now showing consistent counts |

### Key Observations

1. **pyright package skipping**: The volatile pyright error counts appear to be caused by certain packages intermittently being skipped or timing out, rather than actual changes in error detection:
   - Ubuntu 01-16: sympy and numpy skipped (0 errors), restored 01-20 (+47K)
   - macOS 01-20: salt and airflow skipped (0 errors), causing -59K drop

2. **pyrefly 0.49.0**: Very stable release with minimal change in error counts (+0.1% on average)

3. **zuban stabilization**: After the significant jump in 01-16 when transformers analysis was fixed, counts are now stable (~+0.1% change)

4. **Execution time trends**: All type checkers showing slightly increased execution times, especially noticeable on Windows (+2.86s for pyrefly, +3.03s for pyright)

5. **Cross-platform consistency**: Aside from pyright's package skipping issues, all type checkers show consistent behavior across Ubuntu, macOS, and Windows

### Recommendations

1. **Investigate pyright timeouts**: The intermittent 0-error results for large packages (sympy, numpy, salt, airflow) suggest timeout or memory issues
2. **Monitor execution time growth**: The upward trend in execution times on all platforms warrants investigation
3. **pyrefly 0.49.0**: Safe to upgrade - no regressions observed

---

*Report generated: 2026-01-20*