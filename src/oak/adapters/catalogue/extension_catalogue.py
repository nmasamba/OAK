# SPDX-License-Identifier: Apache-2.0
"""The catalogue the compiler reads: the curated documents, plus the activated extensions
the operator's trust anchors vouch for.

Until Tier 3's Batch A, activating a component-manifest or architecture-pattern extension
fed nothing (`RR-004`'s catalogue clause): the curated catalogue inside the wheel was the
whole catalogue, and a signature over it would have proven little, because whoever alters
the wheel alters the verifier and any pinned key with it (`RR-025`). The boundary where
authenticity matters is here, where a manifest enters from outside the wheel. An active
extension feeds the catalogue only when, at the moment the catalogue is read:

- its activation record exists and names this manifest by digest;
- its manifest's steward signature verifies against a key pinned in the operator's trust
  directory now, never a key the extension carries (`RR-012`);
- every payload file matches the digest the signed manifest declares, and the aggregate
  payload digest matches;
- every payload document validates against its class's schema.

Anything else refuses the read, never silently omits the extension: an operator who
activated one must not get a design that quietly left it out. The provenance of every
document an extension contributed is returned beside it, and the compiler writes it into
the catalogue snapshot, which every compiled artifact is bound to.
"""

from collections.abc import Callable
from typing import Any, NoReturn

from oak.contracts import ContractValidationError, SchemaRegistry, load_alias_free_yaml_document
from oak.contracts.signatures import verify_pinned_signature
from oak.domain import OAKError, canonical_json_bytes, content_digest
from oak.domain.extension_sdk import (
    ARCHITECTURE_PATTERN_CLASS,
    COMPONENT_MANIFEST_CLASS,
    STEWARD_ROLE,
)
from oak.ports.catalogue import CatalogueDocuments, CataloguePort
from oak.ports.extensions import ACTIVE, ExtensionEntry, ExtensionStorePort

FED_CLASSES = {
    COMPONENT_MANIFEST_CLASS: "component-manifest.schema.json",
    ARCHITECTURE_PATTERN_CLASS: "architecture-pattern.schema.json",
}
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
    ) -> None:
        self._curated = curated
        self._store = store
        self._anchors = anchors
        self._registry = registry

    def load(self) -> CatalogueDocuments:
        documents = self._curated.load()
        manifests = list(documents.manifests)
        patterns = list(documents.patterns)
        provenance = dict(documents.provenance)
        for entry in self._store.list_entries():
            if entry.state != ACTIVE:
                continue
            schema = FED_CLASSES.get(str(entry.manifest.get("extension_class")))
            if schema is None:
                continue
            origin = self._vouched(entry)
            for name in self._store.payload_names(entry):
                document = self._document(entry, self._store.payload_bytes(entry, name), schema)
                identifier = str(document["id"])
                if schema == FED_CLASSES[COMPONENT_MANIFEST_CLASS]:
                    manifests.append(document)
                else:
                    patterns.append(document)
                provenance[identifier] = dict(origin)
        return CatalogueDocuments(
            manifests=tuple(manifests), patterns=tuple(patterns), provenance=provenance
        )

    def _vouched(self, entry: ExtensionEntry) -> dict[str, Any]:
        """Every check an activated extension must pass now, or the read is refused."""

        manifest = entry.manifest
        activation = self._store.activation_record(entry)
        if activation is None:
            self._refuse(entry, "it has no activation record")
        manifest_digest = content_digest(canonical_json_bytes(manifest))
        if (
            activation.get("extension_id") != entry.extension_id
            or activation.get("extension_version") != entry.version
            or activation.get("manifest_digest") != manifest_digest
        ):
            self._refuse(entry, "its activation record does not name this manifest")
        reason = verify_pinned_signature(manifest, self._anchors(), role=STEWARD_ROLE)
        if reason is not None:
            self._refuse(entry, SIGNATURE_REASONS.get(reason, "its signature was refused"))
        declared = manifest["payload"]["files"]
        digests = {str(item["path"]): str(item["digest"]) for item in declared}
        names = self._store.payload_names(entry)
        if sorted(digests) != list(names):
            self._refuse(entry, "its payload files do not match the signed manifest")
        for name in names:
            if content_digest(self._store.payload_bytes(entry, name)) != digests[name]:
                self._refuse(entry, "a payload file does not match its signed digest")
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
            "activated_at": str(activation["activated_at"]),
        }

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


__all__ = ["ExtensionFedCatalogue"]
