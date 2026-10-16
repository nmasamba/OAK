# SPDX-License-Identifier: Apache-2.0
"""The print palette (kickoff decision K5): paper, ink and one brass accent.

Decks get printed and projected, so every slide but the cover sits on a light paper
ground with ink text; the cover alone carries the workspace's dark Instrument ground.
Brass is the one accent: rules, the recommendation and the selected option. A status is
always a drawn shape and a word, never a colour alone, so the palette needs no status
colours that a reader must tell apart.

`TEXT_PAIRS` lists every text colour the renderers draw on every ground they draw it on;
guard R4 in `scripts/check_report.py` holds each pair to 4.5:1 or better.
"""

PAPER = "#FBF8F1"
PAPER_SHADE = "#F1ECDF"
INK = "#1D1F1A"
INK_MUTED = "#55594E"
RULE = "#CFC7B4"
BRASS = "#8A6416"
BRASS_LIGHT = "#E0AE4E"
COVER = "#101310"
COVER_TEXT = "#EDEBE3"
COVER_MUTED = "#B4B8AA"
NOTE_GROUND = "#F4EEDD"

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_ITALIC = "Helvetica-Oblique"
FONT_MONO = "Courier"

# (where it is used, text colour, background colour)
TEXT_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("body text on paper", INK, PAPER),
    ("secondary text on paper", INK_MUTED, PAPER),
    ("accent text on paper", BRASS, PAPER),
    ("table header text on shade", INK, PAPER_SHADE),
    ("secondary text on shade", INK_MUTED, PAPER_SHADE),
    ("accent text on shade", BRASS, PAPER_SHADE),
    ("model note text", INK, NOTE_GROUND),
    ("model note label", BRASS, NOTE_GROUND),
    ("cover text", COVER_TEXT, COVER),
    ("cover secondary text", COVER_MUTED, COVER),
    ("cover accent text", BRASS_LIGHT, COVER),
)
