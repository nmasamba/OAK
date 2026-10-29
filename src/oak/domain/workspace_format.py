# SPDX-License-Identifier: Apache-2.0
"""The file workspace's manifest format, and how an older one is carried forward.

A workspace manifest names its format in ``schema_version``. One format is current, and
every build reads it; an older format is one a step in the chain below accepts and carries
to the next. A build that knows a format can read a workspace at it in two ways only:
``oak export`` copies it as it is, so a workspace can always be rescued, and
``oak workspace migrate`` runs the chain under the workspace lock and writes the result.
Nothing migrates on an ordinary read: a workspace at an older format is refused on every
other command, naming the command that would carry it forward, and a format no step
accepts is refused on every command, export included, naming the build that can read it.

Four rules bound what a step may do; ``migrate_manifest`` enforces the last three on every
step's result, and the first is the step author's, proven for the shipped chain by running
the migration in two interpreters with different hash seeds:

- a step is pure: the same manifest and the same objects give the same result, so two
  interpreters with different hash seeds write the same bytes;
- a step never rewrites, relabels, reorders or drops a stored object: every entry the
  input index holds is in the output index as it was and in its place, because the audit
  chain binds those bytes and the entry is the object's identity;
- a step may add objects, and only objects it returned, so an index entry never names
  bytes nothing produced; a document that must change shape is therefore a new object with
  a new digest, and the application records it as a successor of the current design case,
  with an audit event naming the migration as its origin;
- a step may change the manifest's own shape, but every format keeps the invariant keys
  where they are, so an export can read the index without knowing the format.

No published release has written a format other than the current one, so the production
chain holds no step; the mechanism is exercised by a synthetic step in the tests and by the
``0.9.0`` corpus, for which a migration is a no-op.
"""

import copy
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from oak.domain.artifacts import Artifact
from oak.domain.errors import OAKError

CURRENT_MANIFEST_FORMAT = "0.4.0"
#: Keys every manifest format keeps at the top level, and in every index entry, so that an
#: export can be taken from a workspace at any known format without migrating it.
INVARIANT_MANIFEST_KEYS = ("schema_version", "id", "tenant_id", "artifact_index")
INVARIANT_INDEX_KEYS = ("digest", "size_bytes")
#: Where the design-case successor and the audit event record a migration's origin.
MIGRATION_EXTENSION = "oak.community/migration"
MIGRATION_EVENT_TYPE = "workspace_migrated"
_FORMAT = re.compile(r"^[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}(?:-[A-Za-z0-9.-]{1,24})?$")

ReadObject = Callable[[str], bytes]


@dataclass(frozen=True, slots=True)
class StepResult:
    """What one step produced.

    ``manifest`` is the manifest at the step's target format. ``new_artifacts`` are the
    objects the step added, each a new id or version and each named by the output index.
    ``case_document`` is the current design case at the current schema, given only when
    the stored case no longer reads under it, or when the step changed what the case
    refers to (a reshaped intent, say); its ``id`` and ``version`` are the stored case's,
    and the application records the successor and the audit event.
    """

    manifest: dict[str, Any]
    new_artifacts: tuple[Artifact, ...] = ()
    case_document: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class FormatStep:
    """One pure, idempotent step from an older format to the next."""

    from_format: str
    to_format: str
    name: str
    apply: Callable[[dict[str, Any], ReadObject], StepResult]


class FormatChain:
    """The formats a build reads, and the steps that carry each older one forward."""

    def __init__(
        self, steps: tuple[FormatStep, ...] = (), *, current: str = CURRENT_MANIFEST_FORMAT
    ) -> None:
        by_from: dict[str, FormatStep] = {}
        for step in steps:
            if (
                step.from_format == current
                or step.from_format == step.to_format
                or step.from_format in by_from
            ):
                raise ValueError(f"migration chain is malformed at step {step.name}")
            by_from[step.from_format] = step
        self._current = current
        self._by_from = by_from
        for start in by_from:
            self._path(start)

    @property
    def current(self) -> str:
        return self._current

    @property
    def known_formats(self) -> tuple[str, ...]:
        return (self._current, *self._by_from)

    @property
    def older_formats(self) -> tuple[str, ...]:
        return tuple(self._by_from)

    def is_known(self, format_name: str) -> bool:
        return format_name in self.known_formats

    def path(self, from_format: str) -> tuple[FormatStep, ...]:
        """The steps that carry ``from_format`` to the current format; none when current."""

        if not self.is_known(from_format):
            raise OAKError("OAK-WORKSPACE-FORMAT", self.describe_unknown(from_format))
        return self._path(from_format)

    def describe_unknown(self, format_name: str, *, noun: str = "workspace") -> str:
        reads = f"it reads {self._current}"
        if self._by_from:
            reads += f" and migrates from {', '.join(self._by_from)}"
        return (
            f"{noun} format {format_name} is not one this build reads ({reads}); use the "
            "build that wrote it, and export from there"
        )

    def _path(self, from_format: str) -> tuple[FormatStep, ...]:
        steps: list[FormatStep] = []
        seen: set[str] = set()
        format_name = from_format
        while format_name != self._current:
            step = self._by_from.get(format_name)
            if step is None or format_name in seen:
                raise ValueError(
                    f"migration chain does not reach {self._current} from {from_format}"
                )
            seen.add(format_name)
            steps.append(step)
            format_name = step.to_format
        return tuple(steps)


PRODUCTION_CHAIN = FormatChain()


def manifest_format(document: Any) -> str:
    """The format a raw manifest claims, before anything else is believed about it."""

    if not isinstance(document, dict):
        raise OAKError("OAK-WORKSPACE-CORRUPT", "workspace manifest must be an object")
    format_name = document.get("schema_version")
    if not isinstance(format_name, str) or _FORMAT.fullmatch(format_name) is None:
        raise OAKError("OAK-WORKSPACE-CORRUPT", "workspace manifest names no readable format")
    return format_name


def index_digests(manifest: dict[str, Any], *, code: str) -> dict[str, int]:
    """The objects a manifest at any known format names, by the invariant index keys."""

    index = manifest.get("artifact_index")
    if not isinstance(index, list):
        raise OAKError(code, "workspace manifest index is not a list")
    digests: dict[str, int] = {}
    for entry in index:
        if not isinstance(entry, dict):
            raise OAKError(code, "workspace manifest index entry is not an object")
        digest = entry.get("digest")
        size = entry.get("size_bytes")
        if not isinstance(digest, str) or not isinstance(size, int) or isinstance(size, bool):
            raise OAKError(code, "workspace manifest index entry names no object")
        if digests.get(digest, size) != size:
            raise OAKError(code, "workspace manifest index names one object with two sizes")
        digests[digest] = size
    return digests


@dataclass(frozen=True, slots=True)
class WorkspaceFormatReport:
    """What `oak workspace status` reports, for a workspace at any format."""

    workspace_id: str
    format: str
    current_format: str
    known_formats: tuple[str, ...]
    steps: tuple[str, ...]
    #: The current case's id, read from the manifest as stored, when it names one.
    case_id: str | None = None

    @property
    def current(self) -> bool:
        return self.format == self.current_format

    @property
    def known(self) -> bool:
        return self.format in self.known_formats

    def to_document(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "format": self.format,
            "current_format": self.current_format,
            "current": self.current,
            "known": self.known,
            "known_formats": list(self.known_formats),
            "migration_steps": list(self.steps),
            "case_id": self.case_id,
        }


@dataclass(frozen=True, slots=True)
class MigrationOutcome:
    """The chain applied in memory: nothing on disk has changed."""

    from_format: str
    to_format: str
    steps: tuple[str, ...]
    source_digest: str
    manifest: dict[str, Any]
    new_artifacts: tuple[Artifact, ...]
    case_document: dict[str, Any] | None

    @property
    def changed(self) -> bool:
        return bool(self.steps)

    @property
    def reshapes_case(self) -> bool:
        return bool(self.new_artifacts) or self.case_document is not None


def migrate_manifest(
    document: dict[str, Any],
    chain: FormatChain,
    read_object: ReadObject,
    *,
    source_digest: str,
) -> MigrationOutcome:
    """Run the chain over a raw manifest, in memory, checking each step against the rules."""

    from_format = manifest_format(document)
    steps = chain.path(from_format)
    manifest = copy.deepcopy(document)
    new_artifacts: list[Artifact] = []
    case_document: dict[str, Any] | None = None
    overlay: dict[str, bytes] = {}

    def read(digest: str) -> bytes:
        content = overlay.get(digest)
        return content if content is not None else read_object(digest)

    for step in steps:
        before = manifest
        if manifest_format(before) != step.from_format:
            raise OAKError(
                "OAK-WORKSPACE-MIGRATION",
                f"step {step.name} was given a manifest at another format",
            )
        result = step.apply(copy.deepcopy(before), read)
        _check_step(before, result, step, chain)
        for artifact in result.new_artifacts:
            overlay[artifact.digest] = artifact.content
        new_artifacts.extend(result.new_artifacts)
        if result.case_document is not None:
            case_document = result.case_document
        manifest = result.manifest
    return MigrationOutcome(
        from_format=from_format,
        to_format=chain.current,
        steps=tuple(step.name for step in steps),
        source_digest=source_digest,
        manifest=manifest,
        new_artifacts=tuple(new_artifacts),
        case_document=case_document,
    )


def _check_step(
    before: dict[str, Any], result: StepResult, step: FormatStep, chain: FormatChain
) -> None:
    after = result.manifest
    code = "OAK-WORKSPACE-MIGRATION"
    if not isinstance(after, dict):
        raise OAKError(code, f"step {step.name} returned no manifest")
    if manifest_format(after) != step.to_format:
        raise OAKError(code, f"step {step.name} did not reach {step.to_format}")
    for key in INVARIANT_MANIFEST_KEYS:
        if key not in after:
            raise OAKError(code, f"step {step.name} dropped the invariant key {key}")
    if after["id"] != before.get("id") or after["tenant_id"] != before.get("tenant_id"):
        raise OAKError(code, f"step {step.name} changed the workspace identity")
    kept = index_digests(before, code="OAK-WORKSPACE-CORRUPT")
    produced = {artifact.digest: len(artifact.content) for artifact in result.new_artifacts}
    named = index_digests(after, code=code)
    # Every entry the workspace indexed stays as it was, in its place: a step may add
    # entries after them and nothing else. Comparing digests alone would let a step rename,
    # re-kind or re-type an object, or drop one of two entries sharing bytes.
    kept_entries = list(before["artifact_index"])
    if after["artifact_index"][: len(kept_entries)] != kept_entries:
        raise OAKError(code, f"step {step.name} dropped, rewrote or reordered a stored object")
    for digest, size in named.items():
        if digest not in kept and produced.get(digest) != size:
            raise OAKError(code, f"step {step.name} named an object it did not produce")
    for digest in produced:
        if digest in kept:
            raise OAKError(code, f"step {step.name} returned an object the workspace holds")
        if digest not in named:
            raise OAKError(code, f"step {step.name} produced an object its index does not name")
    for key in ("audit_events", "idempotency_records"):
        # The history is the workspace's, entry for entry and in order; a migration records
        # itself through the ordinary commit, never by editing what is already there.
        if key in before and after.get(key) != before[key]:
            raise OAKError(code, f"step {step.name} edited the workspace history")
    if before.get("current_case_ref") != after.get("current_case_ref"):
        raise OAKError(code, f"step {step.name} moved the current design case")
    if result.case_document is not None:
        reference = after.get("current_case_ref")
        if not isinstance(reference, dict):
            raise OAKError(code, f"step {step.name} reshaped a case the workspace does not hold")
        if result.case_document.get("id") != reference.get("id") or str(
            result.case_document.get("version")
        ) != str(reference.get("version")):
            raise OAKError(code, f"step {step.name} reshaped a case other than the current one")
    del chain  # the chain's own invariants were checked when it was built


__all__ = [
    "CURRENT_MANIFEST_FORMAT",
    "INVARIANT_INDEX_KEYS",
    "INVARIANT_MANIFEST_KEYS",
    "MIGRATION_EVENT_TYPE",
    "MIGRATION_EXTENSION",
    "PRODUCTION_CHAIN",
    "FormatChain",
    "FormatStep",
    "MigrationOutcome",
    "ReadObject",
    "StepResult",
    "WorkspaceFormatReport",
    "index_digests",
    "manifest_format",
    "migrate_manifest",
]
