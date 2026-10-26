"""LspClient must reassemble a response body that arrives over several pipe reads."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lsp.lsp_benchmark import LspClient

# A minimal LSP server that answers every request, sending the header and each
# half of the body as separate writes with a pause, so the client sees the
# body in more than one read.
FAKE_SERVER = r'''
import json, sys, time
inp, out = sys.stdin.buffer, sys.stdout.buffer
while True:
    headers = {}
    while True:
        line = inp.readline()
        if not line:
            sys.exit(0)
        if line in (b"\r\n", b"\n"):
            break
        k, v = line.decode().split(":", 1)
        headers[k.strip().lower()] = v.strip()
    msg = json.loads(inp.read(int(headers["content-length"])))
    if "id" not in msg:
        continue
    body = json.dumps({"jsonrpc": "2.0", "id": msg["id"],
                       "result": {"capabilities": {"pad": "x" * 2000}}}).encode()
    out.write(b"Content-Length: %d\r\n\r\n" % len(body)); out.flush()
    half = len(body) // 2
    out.write(body[:half]); out.flush()
    time.sleep(0.05)
    out.write(body[half:]); out.flush()
'''


def test_response_split_across_reads_is_received(tmp_path: Path) -> None:
    server = tmp_path / "fake_server.py"
    server.write_text(FAKE_SERVER)
    client = LspClient("fake", [sys.executable, str(server)], tmp_path)
    client.start()
    try:
        first = client.request("initialize", {}, timeout_s=5)
        second = client.request("textDocument/definition", {}, timeout_s=5)
    finally:
        assert client._proc is not None
        client._proc.kill()
        client._proc.wait()
    assert first["result"]["capabilities"]["pad"] == "x" * 2000
    # The stream stays in sync for the next message
    assert second["id"] == first["id"] + 1
