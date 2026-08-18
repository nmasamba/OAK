# SPDX-License-Identifier: Apache-2.0
"""Fail locally when the committed REST contract removes or tightens a baseline shape."""

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "openapi" / "oak.openapi.json"
BASELINE_PATH = ROOT / "openapi" / "oak.compatibility-baseline.json"
HTTP_METHODS = frozenset({"delete", "get", "head", "options", "patch", "post", "put"})


def _type_signature(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return str(schema["$ref"])
    if "type" in schema:
        value = schema["type"]
        return json.dumps(value, sort_keys=True)
    if "anyOf" in schema:
        return "anyOf:" + ",".join(
            sorted(_type_signature(item) for item in schema["anyOf"] if isinstance(item, dict))
        )
    if "enum" in schema:
        return "enum:" + json.dumps(schema["enum"], sort_keys=True)
    if "const" in schema:
        return "const:" + json.dumps(schema["const"], sort_keys=True)
    return "unspecified"


def contract_signature(openapi: dict[str, Any]) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for path, path_item in sorted(openapi.get("paths", {}).items()):
        if not isinstance(path_item, dict):
            continue
        methods: dict[str, Any] = {}
        for method, operation in sorted(path_item.items()):
            if method not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            parameters = [
                {
                    "in": parameter.get("in"),
                    "name": parameter.get("name"),
                }
                for parameter in operation.get("parameters", [])
                if isinstance(parameter, dict) and parameter.get("required") is True
            ]
            parameters.sort(key=lambda item: (str(item["in"]), str(item["name"])))
            request_body = operation.get("requestBody", {})
            methods[method] = {
                "required_parameters": parameters,
                "request_body_required": bool(
                    isinstance(request_body, dict) and request_body.get("required") is True
                ),
                "responses": sorted(str(code) for code in operation.get("responses", {})),
            }
        paths[path] = methods

    schemas: dict[str, Any] = {}
    raw_schemas = openapi.get("components", {}).get("schemas", {})
    for name, schema in sorted(raw_schemas.items()):
        if not isinstance(schema, dict):
            continue
        properties = schema.get("properties", {})
        schemas[name] = {
            "required": sorted(str(field) for field in schema.get("required", [])),
            "properties": {
                str(field): _type_signature(value)
                for field, value in sorted(properties.items())
                if isinstance(value, dict)
            },
        }
    return {"signature_version": 1, "paths": paths, "schemas": schemas}


def compatibility_errors(
    baseline: dict[str, Any], current_openapi: dict[str, Any]
) -> tuple[str, ...]:
    current = contract_signature(current_openapi)
    errors: list[str] = []
    for path, methods in baseline.get("paths", {}).items():
        current_methods = current["paths"].get(path)
        if current_methods is None:
            errors.append(f"removed path {path}")
            continue
        for method, operation in methods.items():
            current_operation = current_methods.get(method)
            label = f"{method.upper()} {path}"
            if current_operation is None:
                errors.append(f"removed operation {label}")
                continue
            baseline_responses = set(operation["responses"])
            current_responses = set(current_operation["responses"])
            for response in sorted(baseline_responses - current_responses):
                errors.append(f"removed response {response} from {label}")
            baseline_parameters = operation["required_parameters"]
            current_parameters = current_operation["required_parameters"]
            if current_parameters != baseline_parameters:
                errors.append(f"changed required parameters for {label}")
            if (
                not operation["request_body_required"]
                and current_operation["request_body_required"]
            ):
                errors.append(f"made request body required for {label}")

    for name, schema in baseline.get("schemas", {}).items():
        current_schema = current["schemas"].get(name)
        if current_schema is None:
            errors.append(f"removed schema {name}")
            continue
        if current_schema["required"] != schema["required"]:
            errors.append(f"changed required fields for schema {name}")
        for field, signature in schema["properties"].items():
            current_signature = current_schema["properties"].get(field)
            if current_signature is None:
                errors.append(f"removed property {name}.{field}")
            elif current_signature != signature:
                errors.append(f"changed type of {name}.{field}")
    return tuple(errors)


def _read_json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-baseline", action="store_true")
    arguments = parser.parse_args()
    current = _read_json(OPENAPI_PATH)
    if arguments.write_baseline:
        BASELINE_PATH.write_text(
            json.dumps(contract_signature(current), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    errors = compatibility_errors(_read_json(BASELINE_PATH), current)
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
