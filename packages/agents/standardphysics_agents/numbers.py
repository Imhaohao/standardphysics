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


def _singular(word: str) -> str:
    if word.endswith("ves") and len(word) > 4:
        return word[:-3] + "f"
    if word.endswith(("ses", "hes", "xes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


VES_ENDINGS = ("lf", "af")
"""Shelf and half take -ves. Roof and chef do not, so only these two shapes
get the rule rather than every word ending in f."""


def plural(label: str) -> str:
    """`chairs`, `display cases`, `boxes`, `shelves`.

    Idempotent, so a word that arrives plural does not come back as `sofases`.
    """
    lowered = _singular(label.strip().casefold())
    if lowered.endswith(VES_ENDINGS):
        return f"{lowered[:-1]}ves"
    if lowered.endswith(("s", "x", "ch", "sh")):
        return f"{lowered}es"
    return f"{lowered}s"


COUNT_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
"""Counted in words up to six, because nobody writes "the 4 tables"."""


def things(labels: list[str]) -> str | None:
    """`the two display cases`, `the four tables`, `the case and the table`."""
    unique = list(dict.fromkeys(labels))
    if not labels:
        return None
    if len(unique) == 1:
        if len(labels) == 1:
            return f"the {unique[0].casefold()}"
        count = COUNT_WORDS.get(len(labels), str(len(labels)))
        return f"the {count} {plural(unique[0])}"
    return " and ".join(f"the {label.casefold()}" for label in unique[:2])


def size(value: float) -> str:
    """`60 inch`, for use in front of a noun: a 60 inch circle."""
    for fraction, name in NAMED_FRACTIONS:
        if abs(value - fraction) < FRACTION_TOLERANCE:
            return name.replace("an inch", "inch").replace("a quarter", "quarter")
    return f"{_whole_or_tenth(value)} inch"


INCHES_PER_FOOT = 12.0

FEET_ABOVE_INCHES = 36.0
"""Above three feet, people say feet.

"126 inches" is a number you have to convert in your head to picture. "10 feet
6 inches" is a distance across a room.
"""


def span(value: float) -> str:
    """`31 inches`, `10 feet 6 inches`, for a distance across a room."""
    if value < FEET_ABOVE_INCHES:
        return inches(value)
    feet = int(value // INCHES_PER_FOOT)
    rest = round(value - feet * INCHES_PER_FOOT)
    if rest >= INCHES_PER_FOOT:
        feet, rest = feet + 1, 0
    foot_word = "foot" if feet == 1 else "feet"
    if rest == 0:
        return f"{feet} {foot_word}"
    return f"{feet} {foot_word} {inches(rest)}"


def by(width: float, depth: float) -> str:
    """`48 by 30 inches`, for a rectangle."""
    return f"{_whole_or_tenth(width)} by {inches(depth)}"


def by_size(width: float, depth: float) -> str:
    """`48 by 30 inch`, for use in front of a noun: a 97 by 38 inch couch."""
    return f"{_whole_or_tenth(width)} by {size(depth)}"
