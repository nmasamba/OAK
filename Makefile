# SPDX-License-Identifier: Apache-2.0

UV_CACHE_DIR ?= .uv-cache
UV := UV_CACHE_DIR=$(UV_CACHE_DIR) uv
PNPM := pnpm

.PHONY: bootstrap lock toolchain-check validate format format-check lint typecheck test test-integration test-e2e openapi-compatibility web-build web-e2e build check audit sbom clean

bootstrap:
	$(UV) sync --frozen
	$(PNPM) install --frozen-lockfile

lock:
	$(UV) lock
	$(PNPM) install --lockfile-only

toolchain-check:
	$(UV) run python tools/check_toolchains.py

validate: toolchain-check
	$(UV) run python scripts/validate_repository.py

format:
	$(UV) run ruff format src tests tools scripts
	$(UV) run ruff check --fix src tests tools scripts
	$(PNPM) format

format-check:
	$(UV) run ruff format --check src tests tools scripts
	$(PNPM) format:check

lint:
	$(UV) run ruff check src tests tools scripts
	$(UV) run python tools/check_boundaries.py
	$(UV) run python tools/check_repository.py
	$(PNPM) lint

typecheck:
	$(UV) run mypy
	$(PNPM) typecheck

test:
	$(UV) run pytest tests/unit tests/contract

test-integration:
	$(UV) run pytest tests/integration

test-e2e:
	$(UV) run pytest tests/e2e

openapi-compatibility:
	$(UV) run python scripts/generate_openapi.py --check
	$(UV) run python scripts/check_openapi_compatibility.py

web-build:
	$(PNPM) build

web-e2e:
	OAK_E2E_DOCKER=1 $(PNPM) --dir web e2e

build:
	$(UV) build --no-build-isolation
	$(PNPM) build

check: validate format-check lint typecheck test test-integration test-e2e openapi-compatibility web-build

audit:
	$(UV) run pip-audit
	$(PNPM) audit --audit-level=high

sbom:
	mkdir -p sbom
	$(UV) run cyclonedx-py environment --output-reproducible --output-format JSON --output-file sbom/python.cdx.json .venv

clean:
	$(UV) cache clean
