# SPDX-License-Identifier: Apache-2.0
"""The in-process research source for the browser suite and the manual capture.

Sprint 14 (ADR-0018). Selected only by ``OAK_RESEARCH_FIXTURES=<directory>``, it answers
the same requests the live readers build, from recorded JSON files in that directory, and
imports no transport. It is the first test double an environment variable can select in
the shipped image, so everything built from it says ``source_mode: fixture``, lists no
real address and reads "synthetic estimate" (``RR-052``).

Dates in a recorded file may be offsets (``@-1d`` for one day before the run), resolved
against the run's ``occurred_at`` so the freshness gate never expires the suite; an
absolute date is kept as it is.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import urllib.parse
from datetime import timedelta
from pathlib import Path
from typing import Any

from oak.adapters.models.transport import TransportRequest, TransportResponse
from oak.domain import OAKError
from oak.domain.catalogue_rules import catalogue_timestamp
from oak.domain.research_rules import SEGMENT

MAXIMUM_FIXTURE_BYTES = 1_048_576
OFFSET = re.compile(r"^@(-?\d{1,4})d$")
FILES = {
    ("huggingface.co", "/api/models"): "hub-models.json",
    ("router.huggingface.co", "/v1/models"): "router-models.json",
    ("api.github.com", "/search/repositories"): "github-search.json",
}


class FixtureResearchSource:
    """Answer research requests from a directory of recorded responses."""

    def __init__(self, directory: Path, *, occurred_at: str) -> None:
        self._directory = directory
        self._occurred_at = catalogue_timestamp(occurred_at)
        self.log: list[str] = []

    @property
    def hosts(self) -> frozenset[str]:
        return frozenset()

    def fetch(
        self, request: TransportRequest, *, deadline_seconds: float | None = None
    ) -> TransportResponse:
        del deadline_seconds
        parts = urllib.parse.urlsplit(request.url)
        host = (parts.hostname or "").lower()
        path = parts.path
        self.log.append(f"{host}{path}")
        name = FILES.get((host, path))
        if name == "github-search.json":
            # One recorded answer per topic where the directory has one, else the shared one.
            query = urllib.parse.parse_qs(parts.query).get("q", [""])[0]
            topic = query.split(" ", 1)[0].removeprefix("topic:")
            if (
                SEGMENT.match(topic)
                and (self._directory / f"github-search--{topic}.json").is_file()
            ):
                name = f"github-search--{topic}.json"
        if name is None and host == "api.github.com":
            match = re.match(r"^/repos/([^/]+)/([^/]+)(?:/(releases|commits/[^/]+))?$", path)
            if match is not None:
                owner, repository, tail = match.groups()
                kind = "repo" if tail is None else ("releases" if tail == "releases" else "commit")
                name = f"github-{kind}--{owner}--{repository}.json".lower()
        if name is None:
            return TransportResponse(404, {}, b"{}")
        body = self._read(name)
        if body is None:
            return TransportResponse(404, {}, b"{}")
        if name.startswith("github-commit--"):
            document = json.loads(body.decode("utf-8"))
            sha = str(document.get("sha", ""))
            return TransportResponse(
                200, {"content-type": "application/vnd.github.sha"}, sha.encode()
            )
        resolved = self._resolve_dates(json.loads(body.decode("utf-8")))
        return TransportResponse(
            200,
            {"content-type": "application/json"},
            json.dumps(resolved, sort_keys=True).encode("utf-8"),
        )

    def _read(self, name: str) -> bytes | None:
        path = self._directory / name
        if path.is_symlink() or not path.is_file():
            return None
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            details = os.fstat(stream.fileno())
            if not stat.S_ISREG(details.st_mode):
                raise OAKError("OAK-RESEARCH-FIXTURE", "a research fixture is not a regular file")
            body = stream.read(MAXIMUM_FIXTURE_BYTES + 1)
        if len(body) > MAXIMUM_FIXTURE_BYTES:
            raise OAKError("OAK-RESEARCH-FIXTURE", "a research fixture exceeds its size limit")
        return body

    def _resolve_dates(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._resolve_dates(child) for key, child in value.items()}
        if isinstance(value, list):
            return [self._resolve_dates(child) for child in value]
        if isinstance(value, str):
            match = OFFSET.match(value)
            if match is not None:
                moment = self._occurred_at + timedelta(days=int(match.group(1)))
                return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
        return value


def fixture_digest(directory: Path) -> str:
    """A digest over the directory's file names and bytes, for the run's evidence."""

    digest = hashlib.sha256()
    for path in sorted(directory.glob("*.json")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()
