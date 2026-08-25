// SPDX-License-Identifier: Apache-2.0
// Build-stage helper for web.Dockerfile, never shipped in any image layer that runs.
//
// devEngines.runtime makes pnpm provision the pinned Node on developer hosts (RR-034),
// and the lockfile therefore carries a `node@runtime:<version>` entry with per-platform
// download URLs. Inside the image build the base already IS the pinned Node —
// tools/check_toolchains.py fails if the FROM line and .node-version diverge — and the
// musl download would add a mandatory network dependency on unofficial-builds.nodejs.org
// to every image build. This script removes the managed runtime from package.json and
// pnpm-lock.yaml so the build uses the base image's Node, and fails loudly if the
// lockfile shape stops matching what it expects: a partial strip must break the build,
// never silently change what gets installed.
"use strict";

const fs = require("node:fs");

const manifest = JSON.parse(fs.readFileSync("package.json", "utf8"));
if (!manifest.devEngines) {
  throw new Error("package.json no longer declares devEngines; update this script");
}
delete manifest.devEngines;
fs.writeFileSync("package.json", JSON.stringify(manifest, null, 2) + "\n");

const lines = fs.readFileSync("pnpm-lock.yaml", "utf8").split("\n");
const kept = [];
for (let index = 0; index < lines.length; index += 1) {
  const line = lines[index];
  if (
    line === "      node:" &&
    (lines[index + 1] ?? "").startsWith("        specifier: runtime:")
  ) {
    index += 2;
    continue;
  }
  if (/^ {2}node@runtime:/.test(line)) {
    while (
      index + 1 < lines.length &&
      !/^ {0,2}\S/.test(lines[index + 1] ?? "")
    ) {
      index += 1;
    }
    continue;
  }
  kept.push(line);
}
const stripped = kept.join("\n");
if (stripped.includes("runtime:")) {
  throw new Error("pnpm-lock.yaml still references a managed runtime after stripping");
}
fs.writeFileSync("pnpm-lock.yaml", stripped);
console.log("managed Node runtime stripped for the image build");
