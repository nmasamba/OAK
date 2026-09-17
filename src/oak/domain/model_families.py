# SPDX-License-Identifier: Apache-2.0
"""The model families a user may configure, described without any provider code.

This table is the single source for family identifiers, display names, licence classes
(in the vocabulary of `OAK-FR-CAT-003`) and the documented environment variables that may
carry a key. Provider adapters reference it; interfaces render it; nothing here can reach
a network or a keychain.
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
        "openai": "OAK_MODEL_KEY_OPENAI",
        "anthropic": "OAK_MODEL_KEY_ANTHROPIC",
        "gemini": "OAK_MODEL_KEY_GEMINI",
        "meta": "OAK_MODEL_KEY_META",
        "xai": "OAK_MODEL_KEY_XAI",
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
        family="openai",
        display_name="OpenAI",
        licence_class=LICENCE_PROPRIETARY_HOSTED,
        credential_required=True,
        environment_variable="OAK_MODEL_KEY_OPENAI",
        key_hint="an OpenAI API key (they begin with sk-)",
        data_use_note="brief content is sent to OpenAI under your account's data-use terms",
        token_help_url="https://platform.openai.com/api-keys",
    ),
    FamilyDescriptor(
        family="anthropic",
        display_name="Anthropic",
        licence_class=LICENCE_PROPRIETARY_HOSTED,
        credential_required=True,
        environment_variable="OAK_MODEL_KEY_ANTHROPIC",
        key_hint="an Anthropic API key (they begin with sk-ant-)",
        data_use_note="brief content is sent to Anthropic under your account's data-use terms",
        token_help_url="https://console.anthropic.com/settings/keys",
    ),
    FamilyDescriptor(
        family="gemini",
        display_name="Google Gemini",
        licence_class=LICENCE_PROPRIETARY_HOSTED,
        credential_required=True,
        environment_variable="OAK_MODEL_KEY_GEMINI",
        key_hint="a Gemini API key from Google AI Studio (they begin with AIza)",
        data_use_note="brief content is sent to Google under your account's data-use terms",
        token_help_url="https://aistudio.google.com/apikey",
    ),
    FamilyDescriptor(
        family="meta",
        display_name="Meta Model API",
        licence_class=LICENCE_PROPRIETARY_HOSTED,
        credential_required=True,
        environment_variable="OAK_MODEL_KEY_META",
        key_hint="a Meta Model API key",
        data_use_note=(
            "brief content is sent to Meta; the cheaper 'contributor' models permit training "
            "on your prompts and require an explicit acknowledgement here"
        ),
        token_help_url="https://ai.developer.meta.com/",
    ),
    FamilyDescriptor(
        family="xai",
        display_name="xAI Grok",
        licence_class=LICENCE_PROPRIETARY_HOSTED,
        credential_required=True,
        environment_variable="OAK_MODEL_KEY_XAI",
        key_hint="an xAI API key (they begin with xai-)",
        data_use_note="brief content is sent to xAI under your account's data-use terms",
        token_help_url="https://console.x.ai/",
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
