# SPDX-License-Identifier: Apache-2.0
"""probe"""

from __future__ import annotations

import litellm


def go(p: str) -> str:
    return str(litellm.completion(model="x", messages=[{"role": "user", "content": p}]))
