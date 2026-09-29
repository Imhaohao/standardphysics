"""What an owner wants kept when the rearranger changes their shop, and how a proposal explains itself.

An owner states a wish when they turn a proposal down: keep this piece where
it is, keep it within some inches of another, or keep it out of the spot a
suggestion put it in. Stated wishes are saved on
the scan and bind every later proposal, the same way the room's ADA layout
directives do. A proposal also says, in plain words, what moved, what it
fixed, and which of the owner's choices it kept or had to bend, with a
ready-made wish for each bent one so the owner can say "keep that" in a tap.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .geometry import Vec3
from .loop import NodeMove

MAX_NEAR_INCHES = 240.0
NEEDS = {"stays_near": ("anchor_id", "inches"), "not_there": ("at", "inches")}
"""The fields each kind of wish cannot do without."""


class OwnerWish(BaseModel):
    """One thing the owner wants kept."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["stays_put", "stays_near", "not_there"]
    node_id: UUID
    anchor_id: UUID | None = None
    """For `stays_near`, the piece to stay near."""
    inches: float | None = Field(default=None, gt=0, le=MAX_NEAR_INCHES)
    """For `stays_near`, how near; for `not_there`, how far from `at` the piece must stay if it moves."""
    at: Vec3 | None = None
    """For `not_there`, the spot the owner turned down for this piece, in the scan's coordinates."""
    text: str = Field(default="", max_length=200)
    """The wish in the owner's words, for showing back to them."""

    @model_validator(mode="after")
    def _has_what_its_kind_needs(self) -> OwnerWish:
        missing = [name for name in NEEDS.get(self.kind, ()) if getattr(self, name) is None]
        if missing:
            raise ValueError(f"{self.kind} needs {' and '.join(missing)}")
        return self


class OwnerWishesRequest(BaseModel):
    """Every wish the owner wants kept for this shop, replacing the ones saved before."""

    model_config = ConfigDict(extra="forbid")
    wishes: list[OwnerWish] = Field(default_factory=list, max_length=50)


class TurnDownRequest(BaseModel):
    """Pieces the owner doesn't want where a suggestion put them.

    Each becomes a `not_there` wish every later proposal and loop is held to,
    and the whole suggestion is kept as a training record of what was turned down.
    """

    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=0)
    turned_down: list[NodeMove] = Field(min_length=1, max_length=64)
    """Each turned-down piece, with the move from `base_revision` that put it where the owner doesn't want it."""
    suggestion: list[NodeMove] = Field(default_factory=list, max_length=128)
    """Every move the suggestion made, turned down or not, for the record."""
    source: Literal["fix_room", "proposal"] = "fix_room"
    model: str = Field(default="", max_length=120)
    """The model that made the suggestion, as the owner's button names it."""


class BentWish(BaseModel):
    """A choice the owner's layout showed that a proposal breaks, and the wish that would keep it."""

    text: str
    keep: OwnerWish | None = None
    """What to save if the owner wants this kept; None when no single piece can hold it."""


class ProposalExplanation(BaseModel):
    """A proposal in the owner's words, built only from what was measured."""

    moves: list[str] = []
    fixed: list[str] = []
    kept: list[str] = []
    bent: list[BentWish] = []
