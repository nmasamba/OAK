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
# The source commit's time, passed by scripts/reproduce_images.py and the workflows: with
# it set, Python compiles hash-based bytecode (no source mtime inside the .pyc), so the
# venv below is the same bytes on every build of the commit (RR-006). A build that passes
# none still works; it just makes no reproducibility claim.
ARG SOURCE_DATE_EPOCH

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md LICENSE VERSION ./
COPY src ./src
COPY schemas ./schemas
COPY catalogue ./catalogue
COPY policy-packs ./policy-packs
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
# `uv_cache.json` beside the project's own dist-info is uv's record of the build it made
# from this tree, stamped with the build's clock; uv is not in the runtime image and
# nothing reads it there, so it goes, with its RECORD line, or two builds differ by it.
RUN uv sync --frozen --no-dev --no-editable \
    && rm -f /app/.venv/lib/python*/site-packages/oak_community-*.dist-info/uv_cache.json \
    && sed -i '/\/uv_cache\.json,/d' /app/.venv/lib/python*/site-packages/oak_community-*.dist-info/RECORD

# Runtime stage.
FROM python:3.13.12-slim@sha256:f1927c75e81efd1e091dbd64b6c0ecaa5630b38635a3d1c04034ac636e1f94c8

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Apply Debian's security updates as of a fixed date. The base is pinned by digest, and
# that digest is the current one for its tag; the upstream image lags Debian's patch
# stream, so re-pinning fixes nothing and this is the only way to pick up a fixed
# OpenSSL. The packages come from the dated snapshot.debian.org archive, so the result
# depends on the date below, not on when the build ran: the images reproduce (RR-006),
# and the date moves at each release to take the updates published since (RR-036; the
# release checklist in docs/release-process.md). The base's own sources name the
# snapshot they were built from in a comment, which this rewrite follows.
ARG DEBIAN_SNAPSHOT=20261029T000000Z
RUN sed -i \
        -e "s|http://deb.debian.org/debian-security|http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}|" \
        -e "s|http://deb.debian.org/debian|http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}|" \
        /etc/apt/sources.list.d/debian.sources \
    # The rewrite must have matched, and no live mirror may remain, or the build would
    # quietly take today's packages and reproduce nothing.
    && grep -q "snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}" /etc/apt/sources.list.d/debian.sources \
    && grep -q "snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}" /etc/apt/sources.list.d/debian.sources \
    && ! grep -rqs "deb.debian.org\|nginx.org" /etc/apt/sources.list.d /etc/apt/sources.list \
    && apt-get -o Acquire::Check-Valid-Until=false -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Check-Valid-Until=false -o Acquire::Retries=5 \
        upgrade --yes --no-install-recommends \
    && apt-get clean \
    # What apt and dpkg log, and what ldconfig caches, carry the build's own clock.
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/*.bin /var/log/apt /var/log/dpkg.log \
        /var/log/alternatives.log /var/cache/ldconfig/aux-cache

# The model-state directory must exist in the image, owned by `oak` and `0700`, before a
# named volume is mounted over it: Docker copies ownership and mode from the image path, and
# a volume mounted at a path the image does not have is created `root:root 0755`, which the
# unprivileged process cannot then make owner-only. Getting this wrong ends with an operator
# running the container as root, which is the class of workaround RR-037 closed.
# The shadow entry's last-change day is the build day unless it is set, and the account
# files' backups (`/etc/shadow-` and kin) keep the state before each edit: both would
# make two builds differ, so the day is fixed and the backups go (RR-006).
RUN groupadd --gid 10001 oak \
    && useradd --create-home --no-log-init --uid 10001 --gid 10001 oak \
    && chage --lastday 2026-01-01 oak \
    && rm -f /etc/passwd- /etc/shadow- /etc/group- /etc/gshadow- \
    && mkdir -p /var/lib/oak/artifacts \
    && chown -R oak:oak /var/lib/oak \
    && install -d -m 0700 -o oak -g oak /var/lib/oak/model-state

# `--no-editable` above installed the package and its force-included data into the venv,
# so the source tree is not needed here. The venv keeps its build-stage path because its
# console scripts carry an absolute interpreter path.
COPY --from=build --chown=oak:oak /app/.venv /app/.venv

USER oak

# The source revision `/version` reports. A build that passes none reports "unknown"; the
# browser-suite run passes the commit it built, so `/version` proves which build answers.
# Last, so that changing it rebuilds nothing above.
ARG OAK_COMMIT=unknown
ENV OAK_COMMIT=${OAK_COMMIT}

EXPOSE 8080
CMD ["oak-api"]
