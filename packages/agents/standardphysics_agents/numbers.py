"""The display boundary. Inches become words here and nowhere else.

Everything behind this file works in the units the standard is written in. A
rounded label never reaches a threshold comparison, and a rounded label never
claims a measurement met a number it missed.
"""

from __future__ import annotations

NAMED_FRACTIONS = ((0.5, "half an inch"), (0.25, "a quarter inch"))

FRACTION_TOLERANCE = 0.01

WHOLE_TOLERANCE = 0.05


def _whole_or_tenth(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < WHOLE_TOLERANCE:
        return str(rounded)
    return f"{value:.1f}"


def inches(value: float) -> str:
    """`36 inches`, `43 inches`, `half an inch`."""
    for size, name in NAMED_FRACTIONS:
        if abs(value - size) < FRACTION_TOLERANCE:
            return name
    number = _whole_or_tenth(value)
    return f"{number} inch" if number == "1" else f"{number} inches"


def measured(value: float, required: float | None = None) -> str:
    """A measurement, with enough precision to show it missed the threshold.

    35.98 inches against a 36 inch minimum reads as "36 inches" once rounded,
    which would put a passing number under a failing headline. When that would
    happen, show the digits that separate them.
    """
    if required is None or _reads_differently(value, required):
        return inches(value)
    return f"{_separating_text(value, required)} inches"


def _reads_differently(value: float, required: float) -> bool:
    return inches(value) != inches(required) or abs(value - required) < 1e-6


def _separating_text(value: float, required: float) -> str:
    for places in (1, 2, 3):
        text = f"{value:.{places}f}"
        if text != f"{required:.{places}f}":
            return text
    return f"{value:.3f}"


def plural(label: str) -> str:
    lowered = label.strip().casefold()
    if lowered.endswith(("s", "x", "ch", "sh")):
        return f"{lowered}es"
    return f"{lowered}s"


def things(labels: list[str]) -> str | None:
    """`the two display cases`, `the display case and the table`."""
    unique = list(dict.fromkeys(labels))
    if not labels:
        return None
    if len(unique) == 1:
        if len(labels) == 1:
            return f"the {unique[0].casefold()}"
        return f"the two {plural(unique[0])}"
    return " and ".join(f"the {label.casefold()}" for label in unique[:2])


def size(value: float) -> str:
    """`60 inch`, for use in front of a noun: a 60 inch circle."""
    for fraction, name in NAMED_FRACTIONS:
        if abs(value - fraction) < FRACTION_TOLERANCE:
            return name.replace("an inch", "inch").replace("a quarter", "quarter")
    return f"{_whole_or_tenth(value)} inch"


def by(width: float, depth: float) -> str:
    """`48 by 30 inches`, for a rectangle."""
    return f"{_whole_or_tenth(width)} by {inches(depth)}"
