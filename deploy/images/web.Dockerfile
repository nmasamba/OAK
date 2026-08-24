# SPDX-License-Identifier: Apache-2.0
FROM node:24.18.0-alpine@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd AS build

WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY web/package.json ./web/package.json
RUN pnpm install --frozen-lockfile
COPY web ./web
RUN pnpm build

FROM nginx:1.29.1-alpine@sha256:42a516af16b852e33b7682d5ef8acbd5d13fe08fecadc7ed98605ba5e3b26ab8

# Apply distro security updates. The digest pin is current for its tag; the upstream
# image lags Alpine's patch stream, so this is the only way to pick up fixed OpenSSL,
# libexpat, libxml2, libpng, pcre2 and zlib. It trades build-time determinism, which OAK
# does not claim for images (docs/security/residual-risk.md, RR-006).
RUN apk upgrade --no-cache

COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/web/dist /usr/share/nginx/html
EXPOSE 8080
