# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-024 (RR-015): no secret and no user content reaches a log line.

A whole journey runs through the API and the worker with a sentinel in every input that
carries a secret or the user's words: the brief (and the case id named from it), the
confirmed answers, a model key, a wrong capability token, a bearer token, a correlation ID,
an idempotency key, a query string, an exception message and a failing worker cycle. Both
processes' logging is captured at `DEBUG`, the most verbose level, and must hold lines but
no sentinel. Signing keys and webhook secrets are absent: neither the API nor the worker
receives one.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from oak.application import CommunityWorker, OperationWorker
from oak.bootstrap import create_model_configuration_service
from oak.contracts import load_yaml_document
from oak.interfaces.api.app import create_app
from oak.interfaces.logs import ALLOWED_FIELDS, configure_logging
from oak.interfaces.worker import run_worker
from tests.asgi_support import ASGIClient
from tests.mcp_support import build_file_control_plane

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "oaksentinel"
TOKEN = "log-leakage-capability-token-0123456789"
BASE_FIELDS = {"time", "level", "component", "logger", "event"}


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[io.StringIO]:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    monkeypatch.setenv("OAK_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("OAK_CREDENTIALS_DIRECTORY", str(tmp_path / "credentials"))
    monkeypatch.setenv("OAK_MODELS_DIRECTORY", str(tmp_path / "models"))
    stream = io.StringIO()
    configure_logging("oak-api", stream=stream)
    yield stream
    root.handlers[:], level = saved
    root.setLevel(level)
    logging.captureWarnings(False)


class _NoOutbox:
    def claim(self, **_: Any) -> list[Any]:
        return []


def lines_for(lines: list[dict[str, Any]], status: int) -> Any:
    (line,) = [line for line in lines if line.get("status") == status]
    return line.items()


def _headers(key: str, version: str | None = None) -> dict[str, str]:
    headers = {
        "Idempotency-Key": f"{SENTINEL}-idempotency-{key}",
        "X-Correlation-ID": f"{SENTINEL}-correlation-{key}",
        "Authorization": f"Bearer {SENTINEL}-bearer",
    }
    if version is not None:
        headers["If-Match"] = f'"{version}"'
    return headers


def test_a_whole_journey_logs_no_secret_and_no_user_content(
    tmp_path: Path, captured: io.StringIO, monkeypatch: pytest.MonkeyPatch
) -> None:
    control_plane, store = build_file_control_plane(tmp_path)
    application = create_app(
        control_plane=control_plane,
        model_token=TOKEN,
        model_configuration=create_model_configuration_service,
    )
    brief = (
        (ROOT / "examples/briefs/public-manual-qa.yaml")
        .read_text(encoding="utf-8")
        .replace("brief.public-manual-qa", f"brief.{SENTINEL}-case")
        .replace("Cited answers over public technical manuals", f"{SENTINEL} brief title")
    )
    case_id = f"design-case.{SENTINEL}-case"
    answers = load_yaml_document(
        (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
    )
    answers["design_case_id"] = case_id
    for answer in answers["answers"]:
        answer["rationale"] = f"{SENTINEL} rationale {answer['rationale']}"
    worker = CommunityWorker(
        OperationWorker(
            store,
            {
                "generate_candidates": control_plane.execute_operation,
                "evaluate_candidate": control_plane.execute_operation,
            },
        ),
        _NoOutbox(),  # type: ignore[arg-type]
        worker_id="log-leakage-worker",
    )

    with ASGIClient(application, base_url="http://127.0.0.1") as client:
        created = client.post(
            "/v1/design-cases",
            headers=_headers("create"),
            json={"original_name": f"{SENTINEL}.yaml", "content": brief},
        )
        assert created.status_code == 201, created.text
        version = created.json()["case"]["version"]
        interpreted = client.post(
            f"/v1/design-cases/{case_id}:interpret", headers=_headers("interpret", version)
        )
        assert interpreted.status_code == 200, interpreted.text
        version = interpreted.json()["case"]["version"]
        confirmed = client.post(
            f"/v1/design-cases/{case_id}:confirm",
            headers=_headers("confirm", version),
            json={"answers": answers},
        )
        assert confirmed.status_code == 200, confirmed.text
        version = confirmed.json()["case"]["version"]
        generated = client.post(
            f"/v1/design-cases/{case_id}:generate-candidates",
            headers=_headers("generate", version),
        )
        assert generated.status_code == 202, generated.text

        run_worker(worker, once=True)
        assert (
            client.get(f"/v1/operations/{generated.json()['operation_id']}").json()["state"]
            == "succeeded"
        )

        assert client.get(f"/v1/design-cases?cursor={SENTINEL}&q={SENTINEL}").status_code in {
            200,
            422,
        }
        for read in ("audit", "candidates", "research-plan", "export"):
            assert client.get(f"/v1/design-cases/{case_id}/{read}").status_code == 200, read
        stale = client.post(
            f"/v1/design-cases/{case_id}:confirm",
            headers=_headers("stale", "0.0.1"),
            json={"answers": answers},
        )
        assert stale.status_code in {409, 422}
        stored = client.put(
            "/v1/models/credentials/huggingface",
            json={"api_key": f"hf_{SENTINEL}0123456789abcdef"},
            headers={"X-OAK-Model-Token": TOKEN},
        )
        assert stored.status_code == 204, stored.text
        wrong_token = client.put(
            "/v1/models/credentials/huggingface",
            json={"api_key": f"hf_{SENTINEL}0123456789abcdef"},
            headers={"X-OAK-Model-Token": f"{SENTINEL}-wrong-token-0123456789"},
        )
        assert wrong_token.status_code in {401, 403}

        def broken(*_: Any, **__: Any) -> Any:
            raise RuntimeError(f"failed while reading {SENTINEL} brief text")

        monkeypatch.setattr(control_plane, "get_design_case", broken)
        # The test client raises what the app did not handle, after the server's error
        # middleware has answered 500 and the access line has been written.
        with pytest.raises(RuntimeError):
            client.get(f"/v1/design-cases/{case_id}")

    class _Failing:
        def run_once(self, **_: Any) -> Any:
            raise ValueError(f"cycle failed on {SENTINEL} answer")

    pauses: list[float] = []

    def stop_after_one(seconds: float) -> None:
        pauses.append(seconds)
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_worker(_Failing(), once=False, sleep=stop_after_one)  # type: ignore[arg-type]

    text = captured.getvalue()
    lines = [json.loads(line) for line in text.splitlines()]
    events = [line["event"] for line in lines]
    assert events.count("request") >= 10, events
    assert "operation_cycle" in events and "cycle_failed" in events
    assert all(set(line) <= BASE_FIELDS | ALLOWED_FIELDS for line in lines)
    assert {"status": 500, "error_type": "RuntimeError"}.items() <= lines_for(lines, 500)
    assert SENTINEL not in text.lower()
    assert "hf_" not in text and TOKEN not in text
