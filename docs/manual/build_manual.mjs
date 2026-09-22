// SPDX-License-Identifier: Apache-2.0
// Renders docs/manual/manual.html to OAK-Community-Manual.pdf using the same pinned
// Chromium the web e2e suite uses (no new dependency). Run from the repository root:
//   pnpm --dir web exec node ../docs/manual/build_manual.mjs
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.resolve(HERE, "..", "..", "web", "package.json"));
const { chromium } = require("@playwright/test");

const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(`file://${path.join(HERE, "manual.html")}`, { waitUntil: "networkidle" });
await page.pdf({
  path: path.join(HERE, "OAK-Community-Manual.pdf"),
  format: "A4",
  printBackground: true,
  displayHeaderFooter: true,
  headerTemplate: "<span></span>",
  footerTemplate:
    '<div style="width:100%;font-size:8px;color:#5a6b63;text-align:center;font-family:Helvetica,Arial,sans-serif;">' +
    'OAK Community 0.8.0 — user manual · page <span class="pageNumber"></span> of <span class="totalPages"></span></div>',
  margin: { top: "14mm", bottom: "16mm", left: "0", right: "0" },
});
await browser.close();
console.log("wrote docs/manual/OAK-Community-Manual.pdf");
