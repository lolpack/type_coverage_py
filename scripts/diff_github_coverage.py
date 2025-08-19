#!/usr/bin/env python3

# USAGE
# python3 diff_github_coverage.py https://raw.githubusercontent.com/nenb/pytorch/498bbdbaa15331f2ee328765b0821520e041b17c/pyright_main.json https://raw.githubusercontent.com/nenb/pytorch/498bbdbaa15331f2ee328765b0821520e041b17c/pyright_device_type_complete.json --out diff_filenew.txt

from __future__ import annotations
import argparse, json, os, pathlib, sys, urllib.parse, urllib.request
from typing import Any, Dict, List, Optional

# ---------- fetch / parse ----------

def to_raw_github_url(s: str) -> str:
    try:
        u = urllib.parse.urlparse(s)
    except Exception:
        return s
    if u.netloc == "github.com":
        parts = u.path.strip("/").split("/")
        if len(parts) >= 5 and parts[2] == "blob":
            return f"https://raw.githubusercontent.com/{parts[0]}/{parts[1]}/{parts[3]}/{'/'.join(parts[4:])}"
    return s

def load_json(source: str) -> Any:
    p = pathlib.Path(source)
    if p.exists() and p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    url = to_raw_github_url(source)
    req = urllib.request.Request(url, headers={"User-Agent": "json-diff/1.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

# ---------- helpers ----------

def jdump(x: Any, maxlen: int = 200) -> str:
    s = json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return s if len(s) <= maxlen else s[: maxlen - 1] + "…"

def get(d: Any, path: List[Any], default: Any=None) -> Any:
    cur = d
    try:
        for k in path:
            cur = cur[k]
        return cur
    except Exception:
        return default

# ---------- structural diff (only for --show-full) ----------

def path_join(parent: str, key: str | int) -> str:
    if isinstance(key, int): return f"{parent}[{key}]"
    return f"{parent}.{key}" if (isinstance(key, str) and key.isidentifier()) else f'{parent}["{key}"]'

def diff_json(a: Any, b: Any, path: str = "$") -> List[str]:
    out: List[str] = []
    if a == b: return out
    if isinstance(a, dict) and isinstance(b, dict):
        akeys, bkeys = set(a.keys()), set(b.keys())
        for k in sorted(akeys - bkeys, key=str):
            out.append(f"- {path_join(path, k)}: {jdump(a[k])}  (removed)")
        for k in sorted(bkeys - akeys, key=str):
            out.append(f"+ {path_join(path, k)}: {jdump(b[k])}  (added)")
        for k in sorted(akeys & bkeys, key=str):
            out.extend(diff_json(a[k], b[k], path_join(path, k)))
        return out
    if isinstance(a, list) and isinstance(b, list):
        m = min(len(a), len(b))
        for i in range(m):
            out.extend(diff_json(a[i], b[i], path_join(path, i)))
        for i in range(m, len(a)):
            out.append(f"- {path_join(path, i)}: {jdump(a[i])}  (removed)")
        for i in range(m, len(b)):
            out.append(f"+ {path_join(path, i)}: {jdump(b[i])}  (added)")
        if not out and len(a) != len(b):
            out.append(f"~ {path}: list length {len(a)} → {len(b)}")
        return out
    if type(a) is not type(b):
        out.append(f"~ {path}: type {type(a).__name__} → {type(b).__name__}")
        return out
    out.append(f"~ {path}: {jdump(a)} → {jdump(b)}")
    return out

# ---------- formatting sections ----------

SUMMARY_KEYS = [
    ["time"],
    ["typeCompleteness","completenessScore"],
    ["typeCompleteness","exportedSymbolCounts","withKnownType"],
    ["typeCompleteness","exportedSymbolCounts","withUnknownType"],
    ["typeCompleteness","exportedSymbolCounts","withAmbiguousType"],
    ["typeCompleteness","otherSymbolCounts","withKnownType"],
    ["typeCompleteness","otherSymbolCounts","withUnknownType"],
    ["typeCompleteness","otherSymbolCounts","withAmbiguousType"],
]

def summarize_top(a: Dict[str, Any], b: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for keypath in SUMMARY_KEYS:
        al = get(a, keypath, None)
        bl = get(b, keypath, None)
        if al != bl:
            dotted = "$." + ".".join(k if isinstance(k, str) else f"[{k}]" for k in keypath)
            lines.append(f"~ {dotted}: {jdump(al)} → {jdump(bl)}")
    return lines

def map_by_name(symbols: Any) -> Dict[str, Dict[str, Any]]:
    return {
        s.get("name",""): s
        for s in (symbols or [])
        if isinstance(s, dict) and s.get("name")
    }

def exported_symbol_type_changes(a: Dict[str, Any], b: Dict[str, Any]) -> List[str]:
    """
    Compare by stable key = name. Ignore list order.
    Emit lines ONLY when:
      - category (exported type) changed, and/or
      - isExported flipped (became exported / ceased to be exported)
    For signal, we require the symbol to be exported in either version.
    """
    lines: List[str] = []
    A = map_by_name(get(a, ["typeCompleteness","symbols"], []))
    B = map_by_name(get(b, ["typeCompleteness","symbols"], []))
    names = set(A) | set(B)

    for name in sorted(names):
        sa, sb = A.get(name), B.get(name)

        # quick field accessor
        f = lambda s,k,default=None: s.get(k, default) if isinstance(s, dict) else default

        exp_a, exp_b = bool(f(sa,"isExported",False)), bool(f(sb,"isExported",False))
        if not (exp_a or exp_b):
            continue  # only track exported-world changes here

        cat_a, cat_b = f(sa,"category",None), f(sb,"category",None)
        changed_cat = (sa is not None and sb is not None and cat_a != cat_b)
        changed_export = (exp_a != exp_b)

        if not (changed_cat or changed_export):
            continue

        parts = []
        if changed_cat:
            parts.append(f'exported type: {jdump(cat_a)} → {jdump(cat_b)}')
        if changed_export:
            parts.append(f"isExported: {exp_a} → {exp_b}")
        path = f'$.typeCompleteness.symbols["{name}"]'
        lines.append(f"~ {path}: " + " | ".join(parts))

    return lines

def unexported_isTypeKnown_flips(a: Dict[str, Any], b: Dict[str, Any], limit: int) -> Tuple[List[str], int]:
    """
    Symbols unexported in both versions where isTypeKnown flipped.
    This explains changes in otherSymbolCounts.withKnown/UnknownType.
    """
    A = map_by_name(get(a, ["typeCompleteness","symbols"], []))
    B = map_by_name(get(b, ["typeCompleteness","symbols"], []))
    names = sorted(set(A) & set(B))

    results: List[str] = []
    total = 0
    for name in names:
        sa, sb = A[name], B[name]
        exp_a = bool(sa.get("isExported", False))
        exp_b = bool(sb.get("isExported", False))
        if exp_a or exp_b:
            continue  # this section is strictly for unexported→unexported

        itk_a = bool(sa.get("isTypeKnown", False))
        itk_b = bool(sb.get("isTypeKnown", False))
        if itk_a == itk_b:
            continue

        total += 1
        if limit <= 0 or len(results) < limit:
            path = f'$.typeCompleteness.symbols["{name}"]'
            results.append(f'~ {path}: isTypeKnown: {itk_a} → {itk_b}')

    return results, total

# ---------- IO ----------

def write_stdout(text: str) -> None:
    os.write(1, text.encode("utf-8"))

def write_file(path: str, text: str) -> None:
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))
        f.flush(); os.fsync(f.fileno())

def main() -> int:
    ap = argparse.ArgumentParser(description="Readable JSON diff: summary + exported type changes (+ optional details).")
    ap.add_argument("left")
    ap.add_argument("right")
    ap.add_argument("--out", help="Write result to this file")
    ap.add_argument("--show-full", action="store_true", help="Append a full structural diff at the end")
    ap.add_argument("--limit-unexported", type=int, default=300, help="Max lines to print for unexported isTypeKnown flips (0 = no limit)")
    args = ap.parse_args()

    try:
        A, B = load_json(args.left), load_json(args.right)
    except Exception as e:
        os.write(2, f"Error: {e}\n".encode("utf-8"))
        return 2

    out_lines: List[str] = []

    # Section 1 — Summary
    out_lines.append("# Summary changes")
    summ = summarize_top(A, B)
    out_lines.extend(summ if summ else ["No summary changes."])

    # Section 2 — Exported symbol type changes
    out_lines.append("\n# Exported symbol type changes")
    sym_lines = exported_symbol_type_changes(A, B)
    out_lines.extend(sym_lines if sym_lines else ["No exported symbol type changes."])

    # Section 3 — Unexported isTypeKnown flips
    out_lines.append("\n# Unexported isTypeKnown flips")
    flips, total = unexported_isTypeKnown_flips(A, B, args.limit_unexported)
    if flips:
        out_lines.extend(flips)
        if total > len(flips):
            out_lines.append(f"... (+{total - len(flips)} more; raise --limit-unexported to see all)")
    else:
        out_lines.append("None.")

    # Optional: full structural diff
    if args.show_full:
        out_lines.append("\n# Full structural diff")
        out_lines.extend(diff_json(A, B))

    text = "\n".join(out_lines) + "\n"

    if args.out:
        write_file(args.out, text)
    else:
        write_stdout(text)

    changed = bool(summ or sym_lines or flips)
    return 0 if not changed else 1

if __name__ == "__main__":
    raise SystemExit(main())
