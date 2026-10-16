# SPDX-License-Identifier: Apache-2.0
"""Names the architecture report shares across the application and both repositories.

A report is two or three immutable artifacts: the report document (JSON), its PDF
rendering (bytes), and, only when the user chose a model mode, the notes a model proposed.
The case holds the latest set under one extension. None of it is authority. A PPTX
rendering was planned and deferred by the owner after its library failed review; adding it
later is one more media type here and one more reference in the extension.
"""

REPORT_MEDIA_TYPE = "application/vnd.oak.architecture-report+json"
NARRATIVE_MEDIA_TYPE = "application/vnd.oak.report-narrative+json"
PDF_MEDIA_TYPE = "application/pdf"
REPORT_EXTENSION = "oak.community/report"
RENDERING_KIND = "report_rendering"
# The first bytes each rendering must start with. Anything else is not a rendering.
RENDERING_MAGIC = {
    PDF_MEDIA_TYPE: b"%PDF-",
}
MAXIMUM_RENDERING_BYTES = 4_194_304
