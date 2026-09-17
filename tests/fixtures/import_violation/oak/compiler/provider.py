# SPDX-License-Identifier: Apache-2.0
"""Deliberate boundary violation: the compiler must never hold a network client."""

import httpx

__all__ = ["httpx"]
