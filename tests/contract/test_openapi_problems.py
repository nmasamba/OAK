# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-005 (F2-7): the committed contract describes the errors the server sends.

Every error, 4xx and 5xx, is an `application/problem+json` problem document; the contract
used to declare only FastAPI's validation shape, which the server never returns, so a
generated client could parse no error at all.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads((ROOT / "openapi" / "oak.openapi.json").read_text(encoding="utf-8"))
PROBLEM = {"application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}}


def test_every_operation_names_the_problem_document_for_its_errors() -> None:
    for path, path_item in CONTRACT["paths"].items():
        for method, operation in path_item.items():
            responses = operation["responses"]
            assert responses["default"]["content"] == PROBLEM, (method, path)
            if "422" in responses:
                assert responses["422"]["content"] == PROBLEM, (method, path)
            # Since Tier 3's Batch A every operation can be answered 429 by the request
            # limiter, with Retry-After (RR-024).
            assert responses["429"]["content"] == PROBLEM, (method, path)
            assert responses["429"]["headers"]["Retry-After"]["schema"]["type"] == "integer"


def test_the_problem_schema_is_the_shape_the_server_sends() -> None:
    from oak.interfaces.api.models import Problem

    problem = CONTRACT["components"]["schemas"]["Problem"]
    assert set(problem["properties"]) == set(Problem.model_fields)
    assert {"title", "status", "code", "detail"} <= set(problem["required"])
