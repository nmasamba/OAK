# SPDX-License-Identifier: Apache-2.0
"""Numbers as the web shows them: three significant digits, grouped thousands.

`format_number` matches `Intl.NumberFormat("en", { maximumSignificantDigits: 3 })`, the
formatter `web/src/ui/RangeBar.tsx` uses, so a figure reads the same on the screen and
in the files. The contract test that checks the topology port checks this against Node.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal


def format_number(value: float | int | None) -> str:
    if value is None or isinstance(value, bool) or not math.isfinite(value):
        return "unknown"
    number = Decimal(repr(value)) if isinstance(value, float) else Decimal(value)
    if number.is_zero():
        return "0"
    rounded = number.quantize(Decimal(1).scaleb(number.adjusted() - 2), rounding=ROUND_HALF_UP)
    sign = "-" if rounded < 0 else ""
    digits = format(abs(rounded), "f")
    whole, _, fraction = digits.partition(".")
    fraction = fraction.rstrip("0")
    grouped = f"{int(whole):,}"
    return f"{sign}{grouped}.{fraction}" if fraction else f"{sign}{grouped}"


def format_unit(unit: str) -> str:
    """A recorded unit made readable: `normalized_fixture_score` → "normalized fixture score"."""

    return unit.replace("_", " ")
