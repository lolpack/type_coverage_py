# Cross-Project Pyrefly False Positive Analysis

**Generated:** 2026-02-04T18:02:43.393521+00:00

**Projects Analyzed:** 10

## Summary

| Project | False Positives | False Negatives |
|---------|-----------------|----------------|
| requests | 21 | 42 |
| flask | 43 | 47 |
| django | 100 | 100 |
| fastapi | 42 | 100 |
| starlette | 18 | 8 |
| uvicorn | 11 | 26 |
| aiohttp | 100 | 100 |
| httpx | 24 | 8 |
| numpy | 100 | 100 |
| pandas | 100 | 0 |
| **Total** | **559** | **531** |

## False Positive Error Codes by Frequency

| Error Code | Count | Packages |
|------------|-------|----------|
| `bad-override` | 174 | aiohttp, django, fastapi, flask, httpx, numpy, pandas, requests |
| `no-matching-overload` | 60 | aiohttp, django, fastapi, flask, httpx, numpy, pandas, starlette, uvicorn |
| `missing-attribute` | 58 | aiohttp, django, fastapi, flask, httpx, numpy, pandas, requests, starlette, uvicorn |
| `bad-argument-type` | 48 | aiohttp, django, flask, httpx, pandas, starlette |
| `bad-assignment` | 33 | aiohttp, django, fastapi, flask, httpx, numpy, pandas, requests, starlette |
| `unbound-name` | 32 | aiohttp, django, fastapi, flask, numpy, pandas, requests, starlette |
| `unsupported-operation` | 29 | aiohttp, httpx, numpy, pandas, requests, starlette, uvicorn |
| `missing-import` | 24 | flask, pandas, requests |
| `bad-typed-dict-key` | 12 | aiohttp, fastapi |
| `bad-param-name-override` | 9 | aiohttp, django, httpx, starlette |
| `not-iterable` | 9 | aiohttp, django, uvicorn |
| `unexpected-keyword` | 8 | aiohttp, requests |
| `not-callable` | 7 | fastapi, flask, numpy, pandas, starlette |
| `inconsistent-overload` | 7 | aiohttp, starlette |
| `unreachable` | 7 | aiohttp, httpx, starlette |

## Top 10 False Positive Patterns



