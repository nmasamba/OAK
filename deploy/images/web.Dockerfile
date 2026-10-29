# SPDX-License-Identifier: Apache-2.0
FROM node:24.18.0-alpine@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd AS build

WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY web/package.json ./web/package.json
# The base image IS the pinned Node, so the pnpm-managed runtime is stripped for the
# image build only — see the script's header for why. The runtime stage ships none of
# these files, so nothing in the shipped image records the edit.
COPY deploy/images/strip-managed-node.cjs ./strip-managed-node.cjs
RUN node strip-managed-node.cjs && rm strip-managed-node.cjs
RUN pnpm install --frozen-lockfile
COPY web ./web
RUN pnpm build

# Unprivileged runtime: the master process runs as uid 101 (`nginx`), not root, and the
# pid file and caches live under /tmp, so the image tolerates a read-only root
# filesystem. It listens on 8080, which needs no privilege (RR-037). The Debian (trixie)
# variant of the image rather than the Alpine one: Alpine keeps no dated package archive,
# so an Alpine image could either upgrade at build time and never reproduce, or stay at
# its base's packages and fail the scan gate; Debian's dated snapshot gives both.
FROM nginxinc/nginx-unprivileged:1.30.6-trixie@sha256:ec0f7ecb1fbd84959ac114e65fb36074ffc97d4d51db0f18ee925162d889dcef

# Apply Debian's security updates as of the same fixed date as the API image, from the
# dated snapshot.debian.org archive, so the result depends on the date and not on when the
# build ran (RR-006); the date moves at each release (RR-036). apt needs root; the runtime
# user is restored immediately after. What apt, dpkg and ldconfig log carries the build's
# own clock, so it goes.
ARG DEBIAN_SNAPSHOT=20261029T000000Z
USER root
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
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/*.bin /var/log/apt /var/log/dpkg.log \
        /var/log/alternatives.log /var/cache/ldconfig/aux-cache
USER nginx

COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/web/dist /usr/share/nginx/html
EXPOSE 8080
