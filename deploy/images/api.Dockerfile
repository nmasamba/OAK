# SPDX-License-Identifier: Apache-2.0
FROM ghcr.io/astral-sh/uv:0.10.8@sha256:88234bc9e09c2b2f6d176a3daf411419eb0370d450a08129257410de9cfafd2a AS uv
FROM python:3.13.12-slim@sha256:f1927c75e81efd1e091dbd64b6c0ecaa5630b38635a3d1c04034ac636e1f94c8

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md LICENSE VERSION ./
COPY src ./src
COPY schemas ./schemas
COPY catalogue ./catalogue
COPY policy-packs ./policy-packs
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
RUN uv sync --frozen --no-dev --no-editable

RUN useradd --create-home --uid 10001 oak \
    && mkdir -p /var/lib/oak/artifacts \
    && chown -R oak:oak /var/lib/oak
USER oak

EXPOSE 8080
CMD ["oak-api"]
