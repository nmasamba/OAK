# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-002: verify that a restored OAK deployment is actually intact.

OAK keeps its state in two places that are backed up by different tools:

* the **metadata** — workspaces, design-case versions, the artifact index, audit
  and operation state — in a file workspace manifest or in PostgreSQL; and
* the **artifact bytes** — content-addressed objects under the artifact root or the
  workspace object store.

A PostgreSQL restore alone therefore produces a database that indexes artifacts which
may not be on disk, and every read of one fails at use time rather than at restore time.
This walks the index and re-reads every object, so a restore is *measured* rather than
declared.

It is read-only. It opens no transaction, writes nothing, and changes no state.

    python scripts/verify_deployment.py --workspace <dir>
    python scripts/verify_deployment.py --database-url <url> --artifact-root <dir>

Exit codes: 0 intact, 2 integrity failure, 3 the deployment could not be read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_CORRUPT = 2
EXIT_UNREADABLE = 3


@dataclass(frozen=True, slots=True)
class Finding:
    """One integrity problem, phrased so an operator knows what to restore."""

    artifact: str
    problem: str


def _object_path(objects: Path, digest: str) -> Path:
    return objects / digest.removeprefix("sha256:")


def _check_object(objects: Path, digest: str, size_bytes: int, artifact: str) -> Finding | None:
    path = _object_path(objects, digest)
    if not path.is_file():
        return Finding(artifact, f"object missing from the store: {path}")
    payload = path.read_bytes()
    if len(payload) != size_bytes:
        return Finding(artifact, f"object size is {len(payload)} bytes, index says {size_bytes}")
    actual = "sha256:" + hashlib.sha256(payload).hexdigest()
    if actual != digest:
        return Finding(artifact, f"object digest is {actual}, index says {digest}")
    return None


def verify_workspace(workspace: Path) -> tuple[int, list[Finding]]:
    """Verify a file-mode workspace against its own manifest index."""

    manifest_path = workspace / ".oak" / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"no OAK workspace manifest at {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    objects = workspace / ".oak" / "objects" / "sha256"

    findings: list[Finding] = []
    index = manifest.get("artifact_index", [])
    for entry in index:
        finding = _check_object(
            objects,
            str(entry["digest"]),
            int(entry["size_bytes"]),
            f"{entry['kind']}/{entry['id']}@{entry['version']}",
        )
        if finding is not None:
            findings.append(finding)

    # The current case pointer must resolve, or the workspace has a head with no body.
    current = manifest.get("current_case_ref")
    if isinstance(current, dict):
        digest = str(current.get("digest", ""))
        if digest and not _object_path(objects, digest).is_file():
            findings.append(Finding("current_case_ref", f"head object missing: {digest}"))

    return len(index), findings


def verify_database(database_url: str, artifact_root: Path) -> tuple[int, list[Finding]]:
    """Verify a PostgreSQL deployment against its artifact root.

    Artifact bytes are read only from the artifact root; the JSONB copy in
    `artifact_versions.canonical_document` is never read back at runtime, so a
    database restored without its artifact root is not a working deployment.
    """

    from sqlalchemy import create_engine, select

    from oak.adapters.persistence.models import artifact_versions

    objects = artifact_root / "sha256"
    engine = create_engine(database_url)
    with engine.connect() as connection:
        rows = (
            connection.execute(
                select(
                    artifact_versions.c.tenant_id,
                    artifact_versions.c.workspace_id,
                    artifact_versions.c.artifact_id,
                    artifact_versions.c.artifact_version,
                    artifact_versions.c.kind,
                    artifact_versions.c.digest,
                    artifact_versions.c.size_bytes,
                )
            )
            .mappings()
            .all()
        )

    findings: list[Finding] = []
    for row in rows:
        finding = _check_object(
            objects,
            str(row["digest"]),
            int(row["size_bytes"]),
            f"{row['tenant_id']}/{row['workspace_id']}/{row['kind']}/"
            f"{row['artifact_id']}@{row['artifact_version']}",
        )
        if finding is not None:
            findings.append(finding)
    return len(rows), findings


def _report(checked: int, findings: list[Finding], subject: str) -> int:
    for finding in findings:
        print(f"CORRUPT  {finding.artifact}: {finding.problem}", file=sys.stderr)
    if findings:
        print(
            f"\n{len(findings)} of {checked} indexed artifact(s) in {subject} could not be "
            "verified. The metadata and the artifact bytes are not from the same backup, "
            "or one of them is damaged. Restore both from the same point in time.",
            file=sys.stderr,
        )
        return EXIT_CORRUPT
    if checked == 0:
        print(f"{subject} holds no indexed artifacts; nothing to verify.")
        return EXIT_OK
    print(
        f"verified {checked} indexed artifact(s) in {subject}: every object present, "
        "correctly sized, and digest-matching."
    )
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a restored OAK deployment.")
    parser.add_argument("--workspace", type=Path, help="path to a file-mode workspace root")
    parser.add_argument("--database-url", help="SQLAlchemy URL of the control-plane database")
    parser.add_argument("--artifact-root", type=Path, help="artifact root ($OAK_ARTIFACT_ROOT)")
    arguments = parser.parse_args()

    if arguments.workspace and (arguments.database_url or arguments.artifact_root):
        parser.error("choose either --workspace or --database-url with --artifact-root")
    if arguments.database_url and not arguments.artifact_root:
        parser.error(
            "--database-url requires --artifact-root: a database alone is not a deployment"
        )
    if not arguments.workspace and not arguments.database_url:
        parser.error("nothing to verify: pass --workspace or --database-url with --artifact-root")

    try:
        if arguments.workspace:
            checked, findings = verify_workspace(arguments.workspace.resolve())
            subject = str(arguments.workspace)
        else:
            checked, findings = verify_database(
                arguments.database_url, arguments.artifact_root.resolve()
            )
            subject = "the control-plane database"
    # Broad by intent: this is an operator tool, and a traceback is a worse answer
    # than a stable message when a restore is half-finished.
    except Exception as error:
        print(f"could not read the deployment: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_UNREADABLE

    return _report(checked, findings, subject)


if __name__ == "__main__":
    sys.exit(main())
