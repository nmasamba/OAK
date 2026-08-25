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
# filesystem. It listens on 8080, which needs no privilege (RR-037).
FROM nginxinc/nginx-unprivileged:1.29.1-alpine@sha256:27985295bdb22a1ef8f712863210bd5877c0f3006494a593e86b3fe0fa55467e

# Apply distro security updates. The digest pin is current for its tag; the upstream
# image lags Alpine's patch stream, so this is the only way to pick up fixed OpenSSL,
# libexpat, libxml2, libpng, pcre2 and zlib. It trades build-time determinism, which OAK
# does not claim for images (docs/security/residual-risk.md, RR-006). apk needs root;
# the runtime user is restored immediately after.
USER root
RUN apk upgrade --no-cache
USER nginx

COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/web/dist /usr/share/nginx/html
EXPOSE 8080
