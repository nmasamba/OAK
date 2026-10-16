# SPDX-License-Identifier: Apache-2.0
"""Report renderer port: an architecture report document in, file bytes out.

A renderer draws the document it is given and nothing else: it reads no record, calls no
service and decides no wording. The same document and the same renderer version give the
same bytes. It names the formats it can write, so a format can join later without
changing the port.
"""

from typing import Any, Protocol


class ReportRendererPort(Protocol):
    def identity(self) -> dict[str, Any]:
        """`{name, version, libraries}`: what the report's record appendix names."""
        ...

    def formats(self) -> tuple[str, ...]:
        """The media types this renderer writes."""
        ...

    def render(self, document: dict[str, Any], media_type: str) -> bytes: ...
