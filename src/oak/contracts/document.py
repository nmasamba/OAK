# SPDX-License-Identifier: Apache-2.0
"""Lossless runtime wrapper for a parsed canonical document."""

from typing import Any

from pydantic import RootModel


class CanonicalDocument(RootModel[dict[str, Any]]):
    """A parsed JSON object that preserves canonical contract content."""
