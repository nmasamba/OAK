# SPDX-License-Identifier: Apache-2.0
"""Honest placeholders for entrypoints scheduled after Sprint 0."""

import sys
from typing import NoReturn


def _unavailable(process: str) -> NoReturn:
    print(f"{process} is not available in the Sprint 0 harness", file=sys.stderr)
    raise SystemExit(69)


def worker_main() -> NoReturn:
    _unavailable("oak-worker")


def runner_main() -> NoReturn:
    _unavailable("oak-runner")


def mcp_main() -> NoReturn:
    _unavailable("oak-mcp")
