"""What one check hands back."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .observation import Observation, Unevaluated


@dataclass(frozen=True)
class CheckResult:
    observations: list[Observation] = field(default_factory=list)
    unevaluated: list[Unevaluated] = field(default_factory=list)


def as_result(value: CheckResult | Iterable[Observation]) -> CheckResult:
    """Most checks just return their observations; a few report a gap as well."""
    if isinstance(value, CheckResult):
        return value
    return CheckResult(observations=list(value))
