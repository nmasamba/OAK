# SPDX-License-Identifier: Apache-2.0
"""OAK's native stand-in: a loopback HTTP server that answers its health probe (ADR-0019).

The shipped native profile installs this file, so the native path runs offline on every
platform CI covers: the runner verifies its digest as it would a download and runs it
with its own interpreter. It binds 127.0.0.1 only, opens no outbound connection, answers
``GET /health`` with ``200``, and exits on SIGTERM. It implements no component.
"""

from __future__ import annotations

import argparse
import http.server
import json
import signal
import sys
from types import FrameType


class _Health(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_error(404)
            return
        body = json.dumps({"status": "ok"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 (the base names it)
        return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OAK's native stand-in server")
    parser.add_argument("--port", type=int, required=True)
    port = parser.parse_args(argv).port
    server = http.server.HTTPServer(("127.0.0.1", port), _Health)

    def stop(signum: int, frame: FrameType | None) -> None:
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
