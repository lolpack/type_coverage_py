#!/usr/bin/env python3
"""
Generate shareable sandbox links for Pyrefly and Pyright playgrounds.

Both playgrounds use lz-string compression with compressToEncodedURIComponent.
- Pyrefly: Compresses JSON {files: {filename: content}, activeFile: string}
- Pyright: Compresses the raw code string

Usage:
    python sandbox_links.py <file.py>
    python sandbox_links.py --code "def foo(): pass"

Requires: pip install lzstring
"""

import argparse
import json
import sys
from urllib.parse import urlencode

try:
    import lzstring
except ImportError:
    print("Error: lzstring package required. Install with: pip install lzstring")
    sys.exit(1)


def compress_to_encoded_uri(text: str) -> str:
    """Compress text using lz-string's compressToEncodedURIComponent."""
    lz = lzstring.LZString()
    return lz.compressToEncodedURIComponent(text)


def decompress_from_encoded_uri(compressed: str) -> str:
    """Decompress text using lz-string's decompressFromEncodedURIComponent."""
    lz = lzstring.LZString()
    return lz.decompressFromEncodedURIComponent(compressed)


def generate_pyrefly_link(
    code: str,
    filename: str = "sandbox.py",
    version: str | None = None,
) -> str:
    """
    Generate a Pyrefly sandbox link.

    Pyrefly uses a project parameter containing compressed JSON:
    {files: {filename: content}, activeFile: string}
    """
    project_state = {
        "files": {filename: code},
        "activeFile": filename,
    }
    compressed = compress_to_encoded_uri(json.dumps(project_state))

    params = {"project": compressed}
    if version:
        params["version"] = version

    return f"https://pyrefly.org/sandbox/?{urlencode(params)}"


def generate_pyright_link(
    code: str,
    strict: bool = False,
    python_version: str | None = None,
    pyright_version: str | None = None,
) -> str:
    """
    Generate a Pyright playground link.

    Pyright uses a code parameter containing the compressed raw code.
    """
    compressed = compress_to_encoded_uri(code)

    params = {"code": compressed}
    if strict:
        params["strict"] = "true"
    if python_version:
        params["pythonVersion"] = python_version
    if pyright_version:
        params["pyrightVersion"] = pyright_version

    return f"https://pyright-play.net/?{urlencode(params)}"


def decode_pyrefly_link(url: str) -> dict:
    """Decode a Pyrefly sandbox link back to its components."""
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    if "project" in params:
        decompressed = decompress_from_encoded_uri(params["project"][0])
        return json.loads(decompressed)
    elif "code" in params:
        # Legacy single-file format
        decompressed = decompress_from_encoded_uri(params["code"][0])
        return {"files": {"sandbox.py": decompressed}, "activeFile": "sandbox.py"}

    return {}


def decode_pyright_link(url: str) -> str:
    """Decode a Pyright playground link back to code."""
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    if "code" in params:
        return decompress_from_encoded_uri(params["code"][0])

    return ""


def main():
    parser = argparse.ArgumentParser(
        description="Generate Pyrefly and Pyright sandbox links"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("file", nargs="?", help="Python file to encode")
    group.add_argument("--code", "-c", help="Python code string to encode")
    group.add_argument(
        "--decode", "-d", metavar="URL", help="Decode a sandbox URL"
    )

    parser.add_argument(
        "--filename", "-f", default="sandbox.py",
        help="Filename for Pyrefly (default: sandbox.py)"
    )
    parser.add_argument("--strict", "-s", action="store_true", help="Pyright strict mode")
    parser.add_argument("--python-version", help="Python version (e.g., 3.12)")

    args = parser.parse_args()

    if args.decode:
        url = args.decode
        if "pyrefly.org" in url:
            result = decode_pyrefly_link(url)
            print("Pyrefly project:")
            print(json.dumps(result, indent=2))
        elif "pyright-play" in url:
            code = decode_pyright_link(url)
            print("Pyright code:")
            print(code)
        else:
            print("Unknown URL format. Trying both decoders...")
            try:
                result = decode_pyrefly_link(url)
                print("Pyrefly format:", json.dumps(result, indent=2))
            except Exception:
                pass
            try:
                code = decode_pyright_link(url)
                print("Pyright format:", code)
            except Exception:
                pass
        return

    if args.file:
        with open(args.file) as f:
            code = f.read()
    else:
        code = args.code

    print("=" * 60)
    print("PYREFLY")
    print("=" * 60)
    print(generate_pyrefly_link(code, filename=args.filename))
    print()
    print("=" * 60)
    print("PYRIGHT")
    print("=" * 60)
    print(generate_pyright_link(
        code,
        strict=args.strict,
        python_version=args.python_version,
    ))


if __name__ == "__main__":
    main()
