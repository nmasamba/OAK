# SPDX-License-Identifier: Apache-2.0
"""Complete JSON Schema Draft 2020-12 registry and validation."""

import json
from pathlib import Path
from typing import Any

from jsonschema import ValidationError
from jsonschema.validators import validator_for
from referencing import Registry, Resource

# jsonschema builds most of its messages by interpolating the *offending value*:
# `'sk-live-…' is too long`, `'…' is not of type 'integer'`. Only these validators
# describe the schema constraint or the offending key names instead, which is
# structural information the caller already sent. Everything else is synthesized from
# the constraint alone, so a rejected value can never travel back out in a diagnostic.
_INSTANCE_FREE_VALIDATORS = frozenset(
    {"required", "dependentRequired", "dependencies", "additionalProperties"}
)
_MAXIMUM_CONSTRAINT_CHARACTERS = 120


def payload_safe_reason(error: ValidationError) -> str:
    """Describe why validation failed without echoing the value that failed it."""

    validator = str(error.validator)
    if validator in _INSTANCE_FREE_VALIDATORS:
        return error.message
    constraint = repr(error.validator_value)
    if len(constraint) > _MAXIMUM_CONSTRAINT_CHARACTERS:
        constraint = constraint[: _MAXIMUM_CONSTRAINT_CHARACTERS - 3] + "..."
    return f"value does not satisfy {validator}: {constraint}"


class ContractValidationError(ValueError):
    """A stable, payload-safe canonical validation failure."""

    def __init__(self, schema_name: str, path: str, reason: str) -> None:
        self.schema_name = schema_name
        self.path = path
        self.reason = reason
        super().__init__(str(self))

    def __str__(self) -> str:
        location = self.path or "/"
        return f"{self.schema_name} validation failed at {location}: {self.reason}"


class SchemaRegistry:
    """Load every schema in a directory and resolve references by canonical ID."""

    def __init__(self, schemas: dict[str, dict[str, Any]]) -> None:
        if not schemas:
            raise ValueError("schema registry cannot be empty")
        self._schemas = dict(sorted(schemas.items()))
        resources: list[tuple[str, Resource[Any]]] = []
        for schema in self._schemas.values():
            schema_id = schema.get("$id")
            if not isinstance(schema_id, str) or not schema_id:
                raise ValueError("every canonical schema must have a non-empty $id")
            resources.append((schema_id, Resource.from_contents(schema)))
        self._registry = Registry().with_resources(resources)

    @classmethod
    def from_directory(cls, directory: Path) -> "SchemaRegistry":
        schemas: dict[str, dict[str, Any]] = {}
        for path in sorted(directory.glob("*.schema.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise ValueError(f"schema {path.name} must contain an object")
            schemas[path.name] = document
        return cls(schemas)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._schemas)

    def schema(self, name: str) -> dict[str, Any]:
        try:
            return self._schemas[name]
        except KeyError as error:
            raise KeyError(f"unknown canonical schema: {name}") from error

    def validate(self, name: str, instance: Any) -> None:
        schema = self.schema(name)
        validator_class = validator_for(schema)
        validator_class.check_schema(schema)
        validator = validator_class(schema, registry=self._registry)
        errors = sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path))
        if errors:
            raise self._error(name, errors[0])

    @staticmethod
    def _error(name: str, error: ValidationError) -> ContractValidationError:
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        return ContractValidationError(
            schema_name=name, path=path, reason=payload_safe_reason(error)
        )
