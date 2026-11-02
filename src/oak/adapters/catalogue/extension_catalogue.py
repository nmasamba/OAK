# SPDX-License-Identifier: Apache-2.0
"""The catalogue the compiler reads: the curated documents, plus the activated extensions
the operator's trust anchors vouch for.

Until Tier 3's Batch A, activating a component-manifest or architecture-pattern extension
fed nothing (`RR-004`'s catalogue clause): the curated catalogue inside the wheel was the
whole catalogue, and a signature over it would have proven little, because whoever alters
the wheel alters the verifier and any pinned key with it (`RR-025`). The boundary where
authenticity matters is here, where a manifest enters from outside the wheel. An active
extension feeds the catalogue only when, at the moment the catalogue is read:

- its activation record exists, validates against its schema, and names this manifest by
  digest; the record is a claim the operator's own `oak extensions activate` wrote, not a
  proof, so nothing below rests on it alone;
- its manifest's steward signature verifies against a key pinned in the operator's trust
  directory now, never a key the extension carries (`RR-012`);
- its declared compatibility range still holds for this OAK, so a pack activated under an
  older OAK stops feeding once an upgrade passes its maximum;
- every payload file matches the digest the signed manifest declares, and the aggregate
  payload digest matches; what was verified is what is parsed;
- every payload document validates against its class's schema, and its id is held by no
  other catalogue document of either kind.

Anything else refuses the read, never silently omits the extension: an operator who
activated one must not get a design that quietly left it out. The provenance of every
document an extension contributed is returned beside it, and the compiler writes it into
the catalogue snapshot, which every compiled artifact is bound to.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any, NoReturn

from oak.contracts import ContractValidationError, SchemaRegistry, load_alias_free_yaml_document
from oak.contracts.signatures import verify_pinned_signature
from oak.domain import OAKError, canonical_json_bytes, content_digest
from oak.domain.extension_sdk import (
    ARCHITECTURE_PATTERN_CLASS,
    COMPONENT_MANIFEST_CLASS,
    STEWARD_ROLE,
    compatibility_problem,
)
from oak.ports.catalogue import CatalogueDocuments, CataloguePort
from oak.ports.extensions import ACTIVE, ExtensionEntry, ExtensionStorePort

FED_CLASSES = {
    COMPONENT_MANIFEST_CLASS: "component-manifest.schema.json",
    ARCHITECTURE_PATTERN_CLASS: "architecture-pattern.schema.json",
}
KIND_OF = {COMPONENT_MANIFEST_CLASS: "manifest", ARCHITECTURE_PATTERN_CLASS: "pattern"}
ACTIVATION_SCHEMA = "extension-activation.schema.json"


def provenance_key(kind: str, identifier: str) -> str:
    """Provenance is kept by kind and id: a manifest and a pattern may not share an id,
    and a lookup by id alone once let a contributed manifest label a curated pattern."""

    return f"{kind}:{identifier}"


SIGNATURE_REASONS = {
    "unsigned": "its manifest is unsigned",
    "wrong-role": "its signature does not use the steward role",
    "unpinned-key": "its signature key is not pinned in the trust directory",
    "key-mismatch": "its embedded public key does not match the pinned trust anchor",
    "key-id-mismatch": "its signature key identifier does not derive from its key",
    "unreadable-anchor": "the pinned trust anchor key is unreadable",
    "invalid-signature": "its signature does not verify against the pinned trust anchor",
}


class ExtensionFedCatalogue:
    """The curated catalogue plus the activated extensions the trust directory vouches for."""

    def __init__(
        self,
        curated: CataloguePort,
        store: ExtensionStorePort,
        anchors: Callable[[], dict[str, str]],
        registry: SchemaRegistry,
        *,
        oak_version: str,
    ) -> None:
        self._curated = curated
        self._store = store
        self._anchors = anchors
        self._registry = registry
        self._oak_version = oak_version

    def load(self) -> CatalogueDocuments:
        documents = self._curated.load()
        manifests = list(documents.manifests)
        patterns = list(documents.patterns)
        provenance = dict(documents.provenance)
        # Every id the catalogue already holds, of either kind: a contributed document may
        # add to the catalogue, never take an id another document has.
        held = {str(document["id"]) for document in (*manifests, *patterns)}
        # Only the active directory is read: a quarantined entry, well-formed or not, is
        # the `oak extensions` commands' business and never feeds a compile.
        for entry in self._store.list_entries(ACTIVE):
            extension_class = str(entry.manifest.get("extension_class"))
            schema = FED_CLASSES.get(extension_class)
            if schema is None:
                continue
            origin, verified = self._vouched(entry)
            for content in verified.values():
                document = self._document(entry, content, schema)
                identifier = str(document["id"])
                if identifier in held:
                    raise OAKError(
                        "OAK-CATALOGUE-DUPLICATE",
                        f"activated extension {entry.extension_id}@{entry.version} contributes "
                        f"{identifier}, an id another catalogue document already holds",
                    )
                held.add(identifier)
                if extension_class == COMPONENT_MANIFEST_CLASS:
                    manifests.append(document)
                else:
                    patterns.append(document)
                provenance[provenance_key(KIND_OF[extension_class], identifier)] = dict(origin)
        return CatalogueDocuments(
            manifests=tuple(manifests), patterns=tuple(patterns), provenance=provenance
        )

    def _vouched(self, entry: ExtensionEntry) -> tuple[dict[str, Any], dict[str, bytes]]:
        """Every check an activated extension must pass now, or the read is refused.

        Returns the provenance to record and the payload bytes as verified, so that what
        the catalogue parses is what the digests covered.
        """

        manifest = entry.manifest
        activation = self._store.activation_record(entry)
        if activation is None:
            self._refuse(entry, "it has no activation record")
        try:
            self._registry.validate(ACTIVATION_SCHEMA, activation)
        except ContractValidationError:
            self._refuse(entry, "its activation record does not validate")
        manifest_digest = content_digest(canonical_json_bytes(manifest))
        if (
            activation.get("extension_id") != entry.extension_id
            or activation.get("extension_version") != entry.version
            or activation.get("manifest_digest") != manifest_digest
        ):
            self._refuse(entry, "its activation record does not name this manifest")
        activated_at = activation.get("activated_at")
        try:
            stamped = datetime.fromisoformat(str(activated_at).replace("Z", "+00:00"))
        except ValueError:
            stamped = None
        if stamped is None or stamped.tzinfo is None:
            self._refuse(entry, "its activation record carries no readable activation time")
        reason = verify_pinned_signature(manifest, self._anchors(), role=STEWARD_ROLE)
        if reason is not None:
            self._refuse(entry, SIGNATURE_REASONS.get(reason, "its signature was refused"))
        problem = compatibility_problem(manifest, self._oak_version)
        if problem is not None:
            self._refuse(entry, f"it is not compatible with this OAK ({problem.rstrip('.')})")
        declared = manifest["payload"]["files"]
        digests = {str(item["path"]): str(item["digest"]) for item in declared}
        names = self._store.payload_names(entry)
        if sorted(digests) != list(names):
            self._refuse(entry, "its payload files do not match the signed manifest")
        verified: dict[str, bytes] = {}
        for name in names:
            content = self._store.payload_bytes(entry, name)
            if content_digest(content) != digests[name]:
                self._refuse(entry, "a payload file does not match its signed digest")
            verified[name] = content
        expected = content_digest(
            canonical_json_bytes({"files": sorted(declared, key=lambda item: str(item["path"]))})
        )
        if expected != str(manifest["payload"]["payload_digest"]):
            self._refuse(entry, "its aggregate payload digest does not match the signed manifest")
        return {
            "origin": "extension",
            "extension_id": entry.extension_id,
            "extension_version": entry.version,
            "manifest_digest": manifest_digest,
            "signer_key_id": str(manifest["signature"]["key_id"]),
            "activated_at": str(activated_at),
        }, verified

    def _document(self, entry: ExtensionEntry, content: bytes, schema: str) -> dict[str, Any]:
        try:
            document = load_alias_free_yaml_document(content.decode("utf-8"))
            self._registry.validate(schema, document)
        except (UnicodeDecodeError, ValueError, ContractValidationError):
            self._refuse(entry, f"a payload document does not validate against {schema}")
        if not isinstance(document.get("id"), str):
            self._refuse(entry, "a payload document names no id")
        return document

    @staticmethod
    def _refuse(entry: ExtensionEntry, reason: str) -> NoReturn:
        raise OAKError(
            "OAK-CATALOGUE-EXTENSION",
            f"activated extension {entry.extension_id}@{entry.version} cannot feed the "
            f"catalogue: {reason}; deactivate it, or restore what it needs, before compiling",
        )


__all__ = ["ExtensionFedCatalogue", "provenance_key"]
