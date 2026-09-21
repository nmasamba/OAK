# SPDX-License-Identifier: Apache-2.0
"""The model families a user may configure, described without any provider code.

This table is the single source for family identifiers, display names, licence classes
(in the vocabulary of `OAK-FR-CAT-003`) and the documented environment variables that may
carry a key. Provider adapters reference it; interfaces render it; nothing here can reach
a network or a keychain.

Since Sprint 10 there are two rows: Hugging Face Inference Providers, the only hosted
family, and the local OpenAI-compatible server. The product relies on the open-source
ecosystem, so no other hosted vendor is described here.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

LICENCE_PROPRIETARY_HOSTED = "proprietary_hosted"
LICENCE_OPEN_WEIGHT_HOSTED = "open_weight_via_hosted_provider"
LICENCE_LOCAL_SELF_HOSTED = "local_self_hosted"


@dataclass(frozen=True, slots=True)
class FamilyDescriptor:
    family: str
    display_name: str
    licence_class: str
    credential_required: bool
    environment_variable: str | None
    key_hint: str
    data_use_note: str
    token_help_url: str | None


# Environment-variable names are literals so the configuration-reference contract test
# sees them; a reference to any other variable is refused by the credential store.
ENVIRONMENT_VARIABLES: MappingProxyType[str, str] = MappingProxyType(
    {
        "huggingface": "OAK_MODEL_KEY_HUGGINGFACE",
    }
)

FAMILIES: tuple[FamilyDescriptor, ...] = (
    FamilyDescriptor(
        family="huggingface",
        display_name="Hugging Face Inference Providers",
        licence_class=LICENCE_OPEN_WEIGHT_HOSTED,
        credential_required=True,
        environment_variable="OAK_MODEL_KEY_HUGGINGFACE",
        key_hint=(
            "a fine-grained Hugging Face token with the 'Make calls to Inference Providers' "
            "permission; free accounts receive a small monthly experimentation allowance"
        ),
        data_use_note=(
            "requests are routed by Hugging Face to a third-party inference provider under "
            "that provider's terms"
        ),
        token_help_url=(
            "https://huggingface.co/settings/tokens/new"
            "?ownUserPermissions=inference.serverless.write&tokenType=fineGrained"
        ),
    ),
    FamilyDescriptor(
        family="local",
        display_name="Local OpenAI-compatible server",
        licence_class=LICENCE_LOCAL_SELF_HOSTED,
        credential_required=False,
        environment_variable=None,
        key_hint=(
            "no key by default; set one only if your local server (Ollama, vLLM, llama.cpp) "
            "requires a bearer token"
        ),
        data_use_note="brief content stays on this machine; the endpoint must be loopback",
        token_help_url=None,
    ),
)

FAMILY_BY_ID: MappingProxyType[str, FamilyDescriptor] = MappingProxyType(
    {descriptor.family: descriptor for descriptor in FAMILIES}
)
FAMILY_IDS: tuple[str, ...] = tuple(descriptor.family for descriptor in FAMILIES)
DEFAULT_FAMILY = "huggingface"
