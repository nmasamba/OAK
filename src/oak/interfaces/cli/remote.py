# SPDX-License-Identifier: Apache-2.0
"""Remote CLI mode: map design-journey commands onto the `/v1` REST surface.

The client is a bounded stdlib HTTP adapter. It adds no authority: every request
carries the same actor/tenant/idempotency/expected-version context as local mode,
and problem responses are surfaced as the same stable ``OAKError`` codes. A
wrong-shape server response is refused with ``OAK-REMOTE-PROTOCOL`` rather than a
stack trace. Documents written locally are checked against the case references in
the same response, which catches a corrupted or version-skewed server; because
that reference is itself server-supplied, remote mode still trusts the control
plane it is pointed at and is not a defence against a fully malicious server.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from oak.domain import OAKError, canonical_json_bytes, content_digest

MAXIMUM_RESPONSE_BYTES = 94_371_840
MAXIMUM_EXPORT_OBJECT_BYTES = 8_388_608
MAXIMUM_EXPORT_TOTAL_BYTES = 67_108_864
REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_OPERATION_TIMEOUT_SECONDS = 120.0
OPERATION_POLL_SECONDS = 0.5
DIGEST_HEX = re.compile(r"^sha256:([a-f0-9]{64})$")
TERMINAL_OPERATION_STATES = frozenset({"succeeded", "failed", "cancelled"})


def operation_timeout_seconds() -> float:
    raw = os.getenv("OAK_REMOTE_TIMEOUT", "")
    try:
        parsed = float(raw)
    except ValueError:
        return DEFAULT_OPERATION_TIMEOUT_SECONDS
    if not 0 < parsed <= 3600:
        return DEFAULT_OPERATION_TIMEOUT_SECONDS
    return parsed


def _unknown_case(problem: OAKError, path: str) -> OAKError:
    """Name the case a server says it does not hold, as the local CLI does.

    The server answers `OAK-CASE-NOT-FOUND` with an opaque detail. A `0.9` server answered
    `OAK-WORKSPACE-NOT-FOUND`, whose remedy ("run oak init") is wrong for a server, so that
    is reported as the case code too. The client names the case it asked for; the server's
    opaque detail stays opaque.
    """

    if problem.code not in {"OAK-CASE-NOT-FOUND", "OAK-WORKSPACE-NOT-FOUND"}:
        return problem
    prefix = "/v1/design-cases/"
    named = path.startswith(prefix)
    case_id = urllib.parse.unquote(re.split(r"[/:?]", path[len(prefix) :], maxsplit=1)[0])
    if not named or not case_id:
        return OAKError("OAK-CASE-NOT-FOUND", "the server holds no such design case")
    return OAKError("OAK-CASE-NOT-FOUND", f"the server holds no design case {case_id}")


class RemoteClient:
    """Bounded JSON client for one OAK control plane."""

    def __init__(
        self,
        base_url: str,
        *,
        actor: str | None = None,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        model_token: str | None = None,
    ) -> None:
        normalized = base_url.strip().rstrip("/")
        # Every route the client calls starts with /v1, so a URL copied from a REST example
        # with /v1 on the end used to send /v1/v1/... and read as not found.
        if normalized.endswith("/v1"):
            normalized = normalized.removesuffix("/v1").rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise OAKError("OAK-REMOTE-SERVER", "--server must be an http or https URL")
        self._base_url = normalized
        self._actor = actor
        self._timeout = timeout
        self._model_token = model_token

    # -- transport -------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        expected_version: str | None = None,
        model_token: bool = False,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._actor:
            headers["X-OAK-Actor"] = self._actor
        if model_token and self._model_token:
            headers["X-OAK-Model-Token"] = self._model_token
        if idempotency_key is not None:
            if not 16 <= len(idempotency_key) <= 240:
                raise OAKError("OAK-IDEMPOTENCY-KEY", "idempotency key is required")
            headers["Idempotency-Key"] = idempotency_key
        if expected_version is not None:
            headers["If-Match"] = f'"{expected_version}"'
        payload: bytes | None = None
        if body is not None:
            try:
                payload = canonical_json_bytes(body)
            except (TypeError, ValueError) as error:
                raise OAKError(
                    "OAK-REMOTE-REQUEST", "request body is not canonical JSON"
                ) from error
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self._base_url + path,
            data=payload,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                content = response.read(MAXIMUM_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            raise _unknown_case(self._problem(error), path) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise OAKError(
                "OAK-REMOTE-UNAVAILABLE",
                "the remote control plane could not be reached",
                retriable=True,
            ) from error
        if len(content) > MAXIMUM_RESPONSE_BYTES:
            raise OAKError("OAK-REMOTE-SIZE", "remote response exceeds the size limit")
        return self._parse_json(content)

    @staticmethod
    def _parse_json(content: bytes) -> dict[str, Any]:
        try:
            document = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise OAKError("OAK-REMOTE-PROTOCOL", "remote response is not valid JSON") from error
        if not isinstance(document, dict):
            raise OAKError("OAK-REMOTE-PROTOCOL", "remote response is not a JSON object")
        return document

    @staticmethod
    def _problem(error: urllib.error.HTTPError) -> OAKError:
        try:
            content = error.read(1_048_576)
            problem = json.loads(content.decode("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            return OAKError(
                "OAK-REMOTE-PROTOCOL", f"remote request failed with status {error.code}"
            )
        if not isinstance(problem, dict) or not isinstance(problem.get("code"), str):
            return OAKError(
                "OAK-REMOTE-PROTOCOL", f"remote request failed with status {error.code}"
            )
        detail = problem.get("detail")
        return OAKError(
            str(problem["code"]),
            detail if isinstance(detail, str) and detail else "remote request failed",
            retriable=bool(problem.get("retriable", False)),
        )

    # -- resources -------------------------------------------------------------

    def get_case(self, case_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/design-cases/{case_id}")

    def current_case_version(self, case_id: str) -> str:
        return str(require_field(self.get_case(case_id), "case", "version"))

    def get_artifact(self, case_id: str, reference: dict[str, Any]) -> dict[str, Any]:
        """One canonical artifact of the case, refused unless it matches its digest."""

        identifier = urllib.parse.quote(str(reference.get("id", "")), safe="")
        query = urllib.parse.urlencode(
            {
                "version": str(reference.get("version", "")),
                "digest": str(reference.get("digest", "")),
            }
        )
        document = self._request(
            "GET",
            f"/v1/design-cases/{urllib.parse.quote(case_id, safe='')}/artifacts/{identifier}"
            f"?{query}",
        )
        verify_document_digest(document, reference, name=str(reference.get("id")))
        return document

    def get_artifact_bytes(self, case_id: str, reference: dict[str, Any]) -> bytes:
        """One artifact's raw bytes, refused unless they hash to the reference's digest."""

        identifier = urllib.parse.quote(str(reference.get("id", "")), safe="")
        query = urllib.parse.urlencode(
            {
                "version": str(reference.get("version", "")),
                "digest": str(reference.get("digest", "")),
            }
        )
        headers: dict[str, str] = {"Accept": "*/*"}
        if self._actor:
            headers["X-OAK-Actor"] = self._actor
        request = urllib.request.Request(
            self._base_url
            + f"/v1/design-cases/{urllib.parse.quote(case_id, safe='')}/artifacts/{identifier}"
            + f"?{query}",
            headers=headers,
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                content = bytes(response.read(MAXIMUM_RESPONSE_BYTES + 1))
        except urllib.error.HTTPError as error:
            raise _unknown_case(self._problem(error), f"/v1/design-cases/{case_id}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise OAKError(
                "OAK-REMOTE-UNAVAILABLE",
                "the remote control plane could not be reached",
                retriable=True,
            ) from error
        if len(content) > MAXIMUM_RESPONSE_BYTES:
            raise OAKError("OAK-REMOTE-SIZE", "remote response exceeds the size limit")
        if content_digest(content) != reference.get("digest"):
            raise OAKError(
                "OAK-REMOTE-DIGEST", f"remote {reference.get('id')} does not match its digest"
            )
        return content

    def record_report(
        self,
        case_id: str,
        *,
        expected_version: str,
        idempotency_key: str,
        narrative: str = "deterministic",
    ) -> dict[str, Any]:
        model_mode = narrative != "deterministic"
        query = "" if not model_mode else f"?narrative={narrative}"
        return self._request(
            "POST",
            f"/v1/design-cases/{case_id}:record-report{query}",
            idempotency_key=idempotency_key,
            expected_version=expected_version,
            # Offered only when a model would be called, as for interpretation.
            model_token=model_mode,
        )

    def research_plan(self, case_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/design-cases/{case_id}/research-plan")

    def research(
        self,
        case_id: str,
        *,
        consent: dict[str, Any],
        expected_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        # Research is egress, so the capability token is always offered.
        return self._request(
            "POST",
            f"/v1/design-cases/{case_id}:research",
            body={"consent": consent},
            idempotency_key=idempotency_key,
            expected_version=expected_version,
            model_token=True,
        )

    def review_research_item(
        self,
        case_id: str,
        *,
        item_id: str,
        decision: str,
        rationale: str,
        expected_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/design-cases/{case_id}:review-research-item",
            body={"item_id": item_id, "decision": decision, "rationale": rationale},
            idempotency_key=idempotency_key,
            expected_version=expected_version,
        )

    def create_design_case(
        self, *, original_name: str, content: str, idempotency_key: str
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/design-cases",
            body={"original_name": original_name, "content": content},
            idempotency_key=idempotency_key,
        )

    def interpret(
        self,
        case_id: str,
        *,
        expected_version: str,
        idempotency_key: str,
        interpreter: str = "deterministic",
    ) -> dict[str, Any]:
        model_mode = interpreter != "deterministic"
        query = "" if not model_mode else f"?interpreter={interpreter}"
        return self._request(
            "POST",
            f"/v1/design-cases/{case_id}:interpret{query}",
            idempotency_key=idempotency_key,
            expected_version=expected_version,
            # The token is offered only when a model would be called. Sending it on a
            # deterministic request cost nothing until a malformed OAK_MODEL_TOKEN in the
            # environment broke the one command the documentation says never needs it.
            model_token=model_mode,
        )

    def confirm(
        self,
        case_id: str,
        answers: dict[str, Any],
        *,
        expected_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/design-cases/{case_id}:confirm",
            body={"answers": answers},
            idempotency_key=idempotency_key,
            expected_version=expected_version,
        )

    def generate_candidates(
        self, case_id: str, *, expected_version: str, idempotency_key: str
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/design-cases/{case_id}:generate-candidates",
            idempotency_key=idempotency_key,
            expected_version=expected_version,
        )

    def evaluate_candidate(
        self,
        candidate_id: str,
        *,
        case_id: str,
        expected_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/candidates/{candidate_id}:evaluate",
            body={"case_id": case_id},
            idempotency_key=idempotency_key,
            expected_version=expected_version,
        )

    def select_candidate(
        self,
        case_id: str,
        *,
        candidate_id: str,
        rationale: str,
        expected_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/design-cases/{case_id}:select-candidate",
            body={"candidate_id": candidate_id, "rationale": rationale},
            idempotency_key=idempotency_key,
            expected_version=expected_version,
        )

    def create_assurance_plan(
        self,
        case_id: str,
        *,
        candidate_id: str,
        expected_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/design-cases/{case_id}:create-assurance-plan",
            body={"candidate_id": candidate_id},
            idempotency_key=idempotency_key,
            expected_version=expected_version,
        )

    def compile_bundle(
        self,
        case_id: str,
        *,
        candidate_id: str,
        target: dict[str, Any],
        expected_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/design-cases/{case_id}:compile",
            body={"candidate_id": candidate_id, "target": target},
            idempotency_key=idempotency_key,
            expected_version=expected_version,
        )

    def get_operation(self, operation_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/operations/{operation_id}")

    def export_case(self, case_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/design-cases/{case_id}/export")

    def import_case(
        self, export_document: dict[str, Any], *, idempotency_key: str
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/design-cases:import",
            body=export_document,
            idempotency_key=idempotency_key,
        )

    def wait_for_operation(self, operation_id: str) -> dict[str, Any]:
        """Poll a durable operation to a terminal state within a bounded window."""

        deadline = time.monotonic() + operation_timeout_seconds()
        while True:
            operation = self.get_operation(operation_id)
            state = str(operation.get("state", ""))
            if state == "succeeded":
                return operation
            if state in TERMINAL_OPERATION_STATES:
                problem = operation.get("problem")
                if state == "failed" and isinstance(problem, dict):
                    code = problem.get("code")
                    message = problem.get("message")
                    raise OAKError(
                        code if isinstance(code, str) and code else "OAK-OPERATION-FAILED",
                        message
                        if isinstance(message, str) and message
                        else "the remote operation failed",
                        retriable=bool(problem.get("retriable", False)),
                    )
                if state == "cancelled":
                    raise OAKError("OAK-OPERATION-CANCELLED", "the remote operation was cancelled")
                raise OAKError("OAK-OPERATION-FAILED", "the remote operation failed")
            if time.monotonic() >= deadline:
                raise OAKError(
                    "OAK-REMOTE-OPERATION-TIMEOUT",
                    f"operation {operation_id} did not complete in time; it keeps running "
                    "remotely and can be inspected by id",
                    retriable=True,
                )
            time.sleep(OPERATION_POLL_SECONDS)


# -- safe access to server-supplied documents --------------------------------


def require_field(document: Any, *path: str) -> Any:
    """Navigate a server response, refusing any missing or mistyped field.

    A hostile or version-skewed control plane can return a 200 body of the
    wrong shape; without this guard the caller's nested indexing would raise a
    LookupError/TypeError that no command's except tuple catches, producing a
    stack trace and exit 1 instead of a stable ``OAK-REMOTE-PROTOCOL`` code.
    """

    current = document
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise OAKError("OAK-REMOTE-PROTOCOL", "remote response is missing an expected field")
        current = current[key]
    return current


# -- derived idempotency keys ------------------------------------------------


def derived_key(operation: str, identity: str) -> str:
    return f"{operation}:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"


def content_identity(content: bytes) -> str:
    return content_digest(content)


def document_identity(document: dict[str, Any]) -> str:
    try:
        return content_digest(canonical_json_bytes(document))
    except (TypeError, ValueError) as error:
        raise OAKError("OAK-REMOTE-REQUEST", "input is not canonical JSON data") from error


# -- local artifact integrity -------------------------------------------------


def verify_document_digest(document: dict[str, Any], reference: Any, *, name: str) -> None:
    """Refuse to write a remote document whose canonical digest is unreferenced."""

    if not isinstance(reference, dict) or not isinstance(reference.get("digest"), str):
        raise OAKError("OAK-REMOTE-DIGEST", f"{name} has no canonical reference digest")
    actual = document_identity(document)
    if actual != reference["digest"]:
        raise OAKError("OAK-REMOTE-DIGEST", f"{name} does not match its canonical digest")


def write_export_directory(destination: Path, export_document: dict[str, Any]) -> None:
    """Materialize a canonical export as the portable workspace-export layout."""

    manifest = export_document.get("manifest")
    objects = export_document.get("objects")
    if not isinstance(manifest, dict) or not isinstance(objects, list):
        raise OAKError("OAK-REMOTE-PROTOCOL", "remote export document is invalid")
    decoded: dict[str, bytes] = {}
    total = 0
    for item in objects:
        if not isinstance(item, dict):
            raise OAKError("OAK-REMOTE-PROTOCOL", "remote export object is invalid")
        digest = item.get("digest")
        encoded = item.get("content_base64")
        if not isinstance(digest, str) or not isinstance(encoded, str):
            raise OAKError("OAK-REMOTE-PROTOCOL", "remote export object is invalid")
        if DIGEST_HEX.fullmatch(digest) is None:
            raise OAKError("OAK-REMOTE-DIGEST", "remote export digest is invalid")
        try:
            content = base64.b64decode(encoded, validate=True)
        except ValueError as error:
            raise OAKError("OAK-REMOTE-PROTOCOL", "remote export encoding is invalid") from error
        if len(content) > MAXIMUM_EXPORT_OBJECT_BYTES:
            raise OAKError("OAK-REMOTE-SIZE", "remote export object exceeds the size limit")
        total += len(content)
        if total > MAXIMUM_EXPORT_TOTAL_BYTES:
            raise OAKError("OAK-REMOTE-SIZE", "remote export exceeds the size limit")
        if content_digest(content) != digest:
            raise OAKError("OAK-REMOTE-DIGEST", "remote export object digest does not match")
        decoded[digest] = content
    index = manifest.get("artifact_index")
    if not isinstance(index, list):
        raise OAKError("OAK-REMOTE-PROTOCOL", "remote export manifest index is invalid")
    indexed: set[str] = set()
    for entry in index:
        if not isinstance(entry, dict) or not isinstance(entry.get("digest"), str):
            raise OAKError("OAK-REMOTE-PROTOCOL", "remote export manifest entry is invalid")
        indexed.add(str(entry["digest"]))
    if not indexed or not indexed.issubset(decoded):
        raise OAKError("OAK-REMOTE-PROTOCOL", "remote export objects are incomplete")
    absolute = destination.absolute()
    if absolute.exists() or absolute.is_symlink():
        raise OAKError("OAK-EXPORT-OUTPUT", "output directory already exists")
    absolute.parent.mkdir(parents=True, exist_ok=True)
    # Staged beside the destination, owner-only like a local export, and renamed into
    # place: an interrupted write leaves nothing that blocks the retry (F1-15).
    staging = Path(tempfile.mkdtemp(prefix=f".{absolute.name}.tmp-", dir=absolute.parent))
    try:
        os.chmod(staging, 0o700)
        object_directory = staging / "objects" / "sha256"
        object_directory.mkdir(parents=True, mode=0o700)
        os.chmod(staging / "objects", 0o700)
        for digest, content in decoded.items():
            match = DIGEST_HEX.fullmatch(digest)
            assert match is not None  # guarded above
            path = object_directory / match.group(1)
            path.write_bytes(content)
            path.chmod(0o600)
        manifest_path = staging / "manifest.json"
        manifest_path.write_bytes(canonical_json_bytes(manifest))
        manifest_path.chmod(0o600)
        if absolute.exists() or absolute.is_symlink():
            raise OAKError("OAK-EXPORT-OUTPUT", "output directory already exists")
        os.replace(staging, absolute)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def read_export_directory(source: Path) -> dict[str, Any]:
    """Read a portable workspace export into the canonical export document."""

    absolute = source.absolute()
    if absolute.is_symlink() or not absolute.is_dir():
        raise OAKError("OAK-IMPORT-UNSAFE-PATH", "import source must be a regular directory")
    manifest_path = absolute / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise OAKError("OAK-IMPORT-INVALID", "import manifest is missing")
    if manifest_path.stat().st_size > MAXIMUM_EXPORT_OBJECT_BYTES:
        raise OAKError("OAK-IMPORT-SIZE", "import manifest exceeds the size limit")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise OAKError("OAK-IMPORT-INVALID", "import manifest is invalid") from error
    if not isinstance(manifest, dict):
        raise OAKError("OAK-IMPORT-INVALID", "import manifest must be an object")
    index = manifest.get("artifact_index")
    if not isinstance(index, list):
        # A null or numeric index crashed with a TypeError traceback (F1-13).
        raise OAKError("OAK-IMPORT-INVALID", "import manifest index is invalid")
    objects: list[dict[str, str]] = []
    seen: set[str] = set()
    total = 0
    for entry in index:
        if not isinstance(entry, dict):
            raise OAKError("OAK-IMPORT-INVALID", "import manifest index is invalid")
        digest = str(entry.get("digest", ""))
        match = DIGEST_HEX.fullmatch(digest)
        if match is None:
            raise OAKError("OAK-IMPORT-DIGEST", "import object digest is invalid")
        if digest in seen:
            continue
        seen.add(digest)
        object_path = absolute / "objects" / "sha256" / match.group(1)
        if object_path.is_symlink() or not object_path.is_file():
            raise OAKError("OAK-IMPORT-INVALID", "an indexed import object is missing")
        if object_path.stat().st_size > MAXIMUM_EXPORT_OBJECT_BYTES:
            raise OAKError("OAK-IMPORT-SIZE", "an import object exceeds the size limit")
        content = object_path.read_bytes()
        total += len(content)
        if total > MAXIMUM_EXPORT_TOTAL_BYTES:
            raise OAKError("OAK-IMPORT-SIZE", "canonical import exceeds the size limit")
        if content_digest(content) != digest:
            raise OAKError("OAK-IMPORT-DIGEST", "import object digest does not match")
        objects.append(
            {"digest": digest, "content_base64": base64.b64encode(content).decode("ascii")}
        )
    if not objects:
        raise OAKError("OAK-IMPORT-INVALID", "import contains no canonical objects")
    objects.sort(key=lambda item: item["digest"])
    return {"export_version": "0.1.0", "manifest": manifest, "objects": objects}
