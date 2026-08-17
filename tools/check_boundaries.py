# SPDX-License-Identifier: Apache-2.0
"""Enforce modular-monolith dependency and execution boundaries."""

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

INTERNAL_ALLOWED: dict[str, frozenset[str]] = {
    "domain": frozenset(),
    "compiler": frozenset({"contracts", "domain"}),
    "ports": frozenset({"contracts", "domain"}),
    "application": frozenset({"compiler", "contracts", "domain", "ports"}),
    "adapters": frozenset({"contracts", "domain", "ports"}),
    "interfaces": frozenset({"application", "bootstrap", "contracts", "domain"}),
    "runner": frozenset({"contracts", "domain", "runner"}),
    "contracts": frozenset(),
}

THIRD_PARTY_FORBIDDEN: dict[str, frozenset[str]] = {
    "domain": frozenset({"fastapi", "pydantic", "sqlalchemy", "typer", "uvicorn"}),
    "compiler": frozenset({"fastapi", "sqlalchemy", "typer", "uvicorn"}),
    "ports": frozenset({"fastapi", "sqlalchemy", "typer", "uvicorn"}),
    "application": frozenset({"fastapi", "sqlalchemy", "typer", "uvicorn"}),
    "runner": frozenset({"fastapi", "sqlalchemy", "typer", "uvicorn"}),
}


@dataclass(frozen=True, slots=True)
class Violation:
    path: Path
    line: int
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def _package_for(path: Path, source_root: Path) -> str | None:
    try:
        parts = path.relative_to(source_root).parts
    except ValueError:
        return None
    if len(parts) < 3 or parts[0] != "oak":
        return None
    return parts[1]


def _import_names(node: ast.Import | ast.ImportFrom) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if node.module is None:
        return ()
    return (node.module,)


def _check_import(
    path: Path,
    package: str,
    node: ast.Import | ast.ImportFrom,
) -> list[Violation]:
    violations: list[Violation] = []
    for imported in _import_names(node):
        parts = imported.split(".")
        root = parts[0]
        if root == "oak" and len(parts) > 1:
            target = parts[1]
            if target != package and target not in INTERNAL_ALLOWED.get(package, frozenset()):
                violations.append(
                    Violation(
                        path,
                        node.lineno,
                        f"oak.{package} must not import oak.{target}",
                    )
                )
        elif root in THIRD_PARTY_FORBIDDEN.get(package, frozenset()):
            violations.append(Violation(path, node.lineno, f"oak.{package} must not import {root}"))
        if root == "subprocess" and package not in {"adapters", "runner"}:
            violations.append(
                Violation(
                    path,
                    node.lineno,
                    "subprocess is restricted to deployment adapters and the runner",
                )
            )
    return violations


def _check_shell_true(path: Path, tree: ast.AST) -> list[Violation]:
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if (
                keyword.arg == "shell"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
            ):
                violations.append(
                    Violation(path, node.lineno, "shell=True is forbidden in all OAK source")
                )
    return violations


def check(source_root: Path) -> list[Violation]:
    violations: list[Violation] = []
    for path in sorted(source_root.rglob("*.py")):
        package = _package_for(path, source_root)
        if package is None:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as error:
            violations.append(Violation(path, error.lineno or 1, "invalid Python syntax"))
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                violations.extend(_check_import(path, package, node))
        violations.extend(_check_shell_true(path, tree))
    return violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=Path("src"))
    arguments = parser.parse_args()
    violations = check(arguments.source_root)
    for violation in violations:
        print(violation.render(), file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
