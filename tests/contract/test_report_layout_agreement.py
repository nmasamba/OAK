# SPDX-License-Identifier: Apache-2.0
"""OAK-S13-003: the report draws the topology exactly where the workspace draws it.

The web lays a candidate out in `web/src/topology.ts` and formats numbers with
`formatQuantity` in `web/src/ui/RangeBar.tsx`; the report uses Python ports of both. This
test loads the TypeScript through Vite in Node, runs both on the reference candidates and
on awkward shapes, and requires identical coordinates, sizes, sentences and numbers.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from oak.adapters.persistence import FileWorkspaceRepository
from oak.application.report.formatting import format_number
from oak.application.report.records import gather_records
from oak.application.report.topology import layout_topology
from oak.contracts import SchemaRegistry
from tests.report_support import build_reference_case

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
PROBE = """
import { createServer } from "vite";
const input = JSON.parse(await new Promise((resolve) => {
  let data = "";
  process.stdin.on("data", (chunk) => (data += chunk));
  process.stdin.on("end", () => resolve(data));
}));
const server = await createServer({
  root: process.cwd(), logLevel: "silent", appType: "custom",
  server: { middlewareMode: true, hmr: false, ws: false },
  optimizeDeps: { noDiscovery: true, include: [] },
});
try {
  const { layoutTopology } = await server.ssrLoadModule("/src/topology.ts");
  const { formatQuantity } = await server.ssrLoadModule("/src/ui/RangeBar.tsx");
  process.stdout.write(JSON.stringify({
    layouts: input.topologies.map((topology) => layoutTopology(topology)),
    numbers: input.numbers.map((number) => formatQuantity(number)),
  }));
} finally {
  await server.close();
}
"""
AWKWARD = [
    {},
    {"nodes": [{"id": "only", "role": "Only node"}]},
    {
        "nodes": [{"id": "a", "role": "A"}, {"id": "b", "role": "B"}, {"id": "c", "role": "C"}],
        "edges": [
            {"from": "a", "to": "b", "interface": "x"},
            {"from": "b", "to": "a", "interface": "back"},
            {"from": "a", "to": "missing", "interface": "dangling"},
            {"from": "a", "to": "c"},
        ],
    },
    {
        "nodes": [{"id": f"n{index}", "role": f"Role {index}"} for index in range(5)],
        "edges": [{"from": "n0", "to": f"n{index}", "interface": "fan"} for index in range(1, 5)],
    },
]
NUMBERS = [
    36.0,
    32.4,
    39.6,
    1200.0,
    900.0,
    0.511,
    0.949,
    487.5,
    812.5,
    1.316,
    2.444,
    0,
    12345,
    0.0001234,
    -5.55,
    100,
    0.995,
    9.995,
    99950,
    None,
]


def _node() -> str | None:
    node = shutil.which("node")
    if node is None or not (WEB / "node_modules" / "vite").exists():
        if os.environ.get("CI"):
            pytest.fail("CI must run the layout agreement: node and web/node_modules are missing")
        return None
    return node


@pytest.fixture(scope="module")
def topologies(tmp_path_factory: pytest.TempPathFactory) -> list[dict[str, Any]]:
    workspace = build_reference_case(tmp_path_factory.mktemp("layout"), "candidate_selected")
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    records = gather_records(FileWorkspaceRepository(workspace, registry))
    return [candidate["topology"] for candidate in records.candidates] + AWKWARD


def test_python_lays_out_and_formats_exactly_as_the_workspace(
    topologies: list[dict[str, Any]],
) -> None:
    node = _node()
    if node is None:
        pytest.skip("node and web/node_modules are needed to run the workspace layout")
    run = subprocess.run(
        [node, "--input-type=module", "-e", PROBE],
        input=json.dumps({"topologies": topologies, "numbers": NUMBERS}),
        capture_output=True,
        text=True,
        cwd=WEB,
        timeout=120,
        check=True,
    )
    web = json.loads(run.stdout)
    assert len(web["layouts"]) == len(topologies)
    for topology, expected in zip(topologies, web["layouts"], strict=True):
        assert layout_topology(topology) == expected
    assert [format_number(number) for number in NUMBERS] == web["numbers"]
