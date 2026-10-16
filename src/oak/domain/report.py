# SPDX-License-Identifier: Apache-2.0
"""Names the architecture report shares across the application and both repositories.

A report is three or four immutable artifacts: the report document (JSON), its PPTX and
PDF renderings (bytes), and, only when the user chose a model mode, the notes a model
proposed. The case holds the latest set under one extension. None of it is authority.
"""

REPORT_MEDIA_TYPE = "application/vnd.oak.architecture-report+json"
NARRATIVE_MEDIA_TYPE = "application/vnd.oak.report-narrative+json"
PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
PDF_MEDIA_TYPE = "application/pdf"
REPORT_EXTENSION = "oak.community/report"
RENDERING_KIND = "report_rendering"
# The first bytes each rendering must start with: a ZIP local-file header for the PPTX
# package and the PDF header for the PDF. Anything else is not a rendering.
RENDERING_MAGIC = {
    PPTX_MEDIA_TYPE: b"PK\x03\x04",
    PDF_MEDIA_TYPE: b"%PDF-",
}
MAXIMUM_RENDERING_BYTES = 4_194_304
