# SPDX-License-Identifier: Apache-2.0
FROM ghcr.io/astral-sh/uv:0.10.8@sha256:88234bc9e09c2b2f6d176a3daf411419eb0370d450a08129257410de9cfafd2a AS uv

# Build stage. `uv` and the source tree live here and go no further: a 0.7.0 image scan
# found the `uv` and `uvx` binaries shipping in the runtime layer with three HIGH
# advisories each in their vendored Rust dependencies (quinn-proto, rustls-webpki), none
# of which OAK executes at run time. They are build tooling, so they now stay in the build.
FROM python:3.13.12-slim@sha256:f1927c75e81efd1e091dbd64b6c0ecaa5630b38635a3d1c04034ac636e1f94c8 AS build

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

# Runtime stage.
FROM python:3.13.12-slim@sha256:f1927c75e81efd1e091dbd64b6c0ecaa5630b38635a3d1c04034ac636e1f94c8

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Apply distro security updates. The base is pinned by digest, and that digest is the
# current one for its tag — the upstream image itself lags Debian's patch stream, so
# re-pinning fixes nothing and this is the only way to pick up a fixed OpenSSL. It costs
# build-time determinism: image contents now depend on when the build ran. OAK does not
# claim byte-reproducible images (see docs/security/residual-risk.md, RR-006), and
# shipping a known-fixed CRITICAL is the worse trade.
RUN apt-get update \
    && apt-get upgrade --yes --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 oak \
    && mkdir -p /var/lib/oak/artifacts \
    && chown -R oak:oak /var/lib/oak

# `--no-editable` above installed the package and its force-included data into the venv,
# so the source tree is not needed here. The venv keeps its build-stage path because its
# console scripts carry an absolute interpreter path.
COPY --from=build --chown=oak:oak /app/.venv /app/.venv

USER oak

EXPOSE 8080
CMD ["oak-api"]
