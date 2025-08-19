#!/usr/bin/env python3

# USAGE
# python3 diff_github_coverage.py https://raw.githubusercontent.com/nenb/pytorch/498bbdbaa15331f2ee328765b0821520e041b17c/pyright_main.json https://raw.githubusercontent.com/nenb/pytorch/498bbdbaa15331f2ee328765b0821520e041b17c/pyright_device_type_complete.json --out diff_filenew.txt

from __future__ import annotations
import argparse, json, os, pathlib, sys, urllib.parse, urllib.request
from typing import Any, Dict, List, Tuple, Optional

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
    req = urllib.request.Request(url, headers={"User-Agent": "json-diff/1.2"})
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

def map_by_name(symbols: Any) -> Dict[str, Dict[str, Any]]:
    return {
        s.get("name",""): s
        for s in (symbols or [])
        if isinstance(s, dict) and s.get("name")
    }

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

# --- diagnostics comparison ---

def diag_map(sym: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """
    Return {message -> severity} for a symbol's diagnostics.
    Message text is what we care about (it encodes type info).
    """
    if not isinstance(sym, dict):
        return {}
    out: Dict[str, str] = {}
    for d in sym.get("diagnostics", []) or []:
        if not isinstance(d, dict): continue
        msg = d.get("message")
        sev = d.get("severity")
        if isinstance(msg, str):
            out[msg] = str(sev) if isinstance(sev, str) else ""
    return out

def diag_diffs(sa: Optional[Dict[str, Any]], sb: Optional[Dict[str, Any]], limit: int) -> Tuple[List[str], int]:
    """
    Compute per-symbol diagnostic message changes:
      - added / removed messages
      - same message but severity changed
    Returns (lines, total_changes).
    """
    A = diag_map(sa)
    B = diag_map(sb)
    adds = sorted([m for m in B.keys() - A.keys()])
    rems = sorted([m for m in A.keys() - B.keys()])
    both = sorted([m for m in A.keys() & B.keys() if A[m] != B[m]])

    lines: List[str] = []
    total = len(adds) + len(rems) + len(both)

    def add_line(prefix: str, msg: str, sev: Optional[Tuple[str,str]]=None):
        # Use JSON quoting so newlines show as \n inline
        if sev is None:
            lines.append(f"  {prefix} diag.message: {jdump(msg)}")
        else:
            a,b = sev
            lines.append(f"  {prefix} diag.message: {jdump(msg)} (severity: {a} → {b})")

    # Emit up to 'limit' lines (fairly split between classes of change)
    emitted = 0
    for m in adds:
        if limit and emitted >= limit: break
        add_line("+", m); emitted += 1
    for m in rems:
        if limit and emitted >= limit: break
        add_line("-", m); emitted += 1
    for m in both:
        if limit and emitted >= limit: break
        add_line("~", m, (A[m], B[m])); emitted += 1

    return lines, total

# --- exported symbol changes ---

def exported_symbol_changes(
    a: Dict[str, Any],
    b: Dict[str, Any],
    *,
    include_diag: bool,
    diag_limit: int,
    include_msg_only: bool
) -> List[str]:
    """
    Compare by stable key = name. Ignore list order.
    Emit when:
      - category (exported type) changed
      - isExported flipped
      - (optional) diagnostics changed for exported symbols even if neither of the above changed
    """
    lines: List[str] = []
    A = map_by_name(get(a, ["typeCompleteness","symbols"], []))
    B = map_by_name(get(b, ["typeCompleteness","symbols"], []))
    names = set(A) | set(B)

    for name in sorted(names):
        sa, sb = A.get(name), B.get(name)
        f = lambda s,k,default=None: s.get(k, default) if isinstance(s, dict) else default

        exp_a, exp_b = bool(f(sa,"isExported",False)), bool(f(sb,"isExported",False))
        if not (exp_a or exp_b):
            continue  # exported-world only

        cat_a, cat_b = f(sa,"category",None), f(sb,"category",None)
        changed_cat = (sa is not None and sb is not None and cat_a != cat_b)
        changed_export = (exp_a != exp_b)

        # Diagnostics-only?
        diag_lines: List[str] = []
        diag_total = 0
        if include_diag or include_msg_only:
            diag_lines, diag_total = diag_diffs(sa, sb, diag_limit)

        if not (changed_cat or changed_export):
            if include_msg_only and diag_total:
                path = f'$.typeCompleteness.symbols["{name}"]'
                lines.append(f"~ {path}: diagnostics changed")
                if include_diag and diag_lines:
                    lines.extend(diag_lines)
            continue

        path = f'$.typeCompleteness.symbols["{name}"]'
        parts = []
        if changed_cat:
            parts.append(f'exported type: {jdump(cat_a)} → {jdump(cat_b)}')
        if changed_export:
            parts.append(f"isExported: {exp_a} → {exp_b}")
        lines.append(f"~ {path}: " + " | ".join(parts))
        if include_diag and diag_lines:
            lines.extend(diag_lines)
            if diag_total > len(diag_lines):
                lines.append(f"  ... (+{diag_total - len(diag_lines)} more diagnostic changes)")

    return lines

# --- unexported flips ---

def unexported_isTypeKnown_flips(
    a: Dict[str, Any],
    b: Dict[str, Any],
    *,
    include_diag: bool,
    diag_limit: int,
    limit: int
) -> Tuple[List[str], int]:
    """
    Symbols unexported in both versions where isTypeKnown flipped.
    Attach diagnostic message changes to judge whether the type text changed.
    """
    A = map_by_name(get(a, ["typeCompleteness","symbols"], []))
    B = map_by_name(get(b, ["typeCompleteness","symbols"], []))
    names = sorted(set(A) & set(B))

    results: List[str] = []
    total = 0
    for name in names:
        sa, sb = A[name], B[name]
        if bool(sa.get("isExported", False)) or bool(sb.get("isExported", False)):
            continue  # strictly unexported→unexported

        itk_a = bool(sa.get("isTypeKnown", False))
        itk_b = bool(sb.get("isTypeKnown", False))
        if itk_a == itk_b:
            continue

        total += 1
        if limit and len(results) >= limit:
            continue

        path = f'$.typeCompleteness.symbols["{name}"]'
        results.append(f'~ {path}: isTypeKnown: {itk_a} → {itk_b}')

        if include_diag:
            dlines, dtotal = diag_diffs(sa, sb, diag_limit)
            if dlines:
                results.extend(dlines)
                if dtotal > len(dlines):
                    results.append(f"  ... (+{dtotal - len(dlines)} more diagnostic changes)")

    return results, total

# ---------- IO ----------

def write_stdout(text: str) -> None:
    os.write(1, text.encode("utf-8"))

def write_file(path: str, text: str) -> None:
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))
        f.flush(); os.fsync(f.fileno())

def main() -> int:
    ap = argparse.ArgumentParser(description="Readable JSON diff: summary + exported type changes + diagnostic messages.")
    ap.add_argument("left")
    ap.add_argument("right")
    ap.add_argument("--out", help="Write result to this file")
    ap.add_argument("--show-full", action="store_true", help="Append a full structural diff at the end")
    ap.add_argument("--limit-unexported", type=int, default=300, help="Max lines for unexported isTypeKnown flips (0 = no limit)")
    ap.add_argument("--no-diagnostics", action="store_true", help="Do not show diagnostic message changes")
    ap.add_argument("--diag-limit", type=int, default=3, help="Max diagnostic lines per symbol (0 = no limit)")
    ap.add_argument("--include-exported-message-only", action="store_true",
                    help="Also show exported symbols where only diagnostics changed (no category/export flip)")
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

    # Section 2 — Exported symbol changes (type/export + optional diagnostics)
    out_lines.append("\n# Exported symbol type changes")
    sym_lines = exported_symbol_changes(
        A, B,
        include_diag = (not args.no_diagnostics),
        diag_limit = args.diag_limit,
        include_msg_only = args.include_exported_message_only
    )
    out_lines.extend(sym_lines if sym_lines else ["No exported symbol type changes."])

    # Section 3 — Unexported isTypeKnown flips (with optional diagnostics)
    out_lines.append("\n# Unexported isTypeKnown flips")
    flips, total = unexported_isTypeKnown_flips(
        A, B,
        include_diag = (not args.no_diagnostics),
        diag_limit = args.diag_limit,
        limit = args.limit_unexported
    )
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
