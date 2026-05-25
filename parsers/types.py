#!/usr/bin/env python3
"""
  types.py
  ========

  Description:           Intermediate data types returned by parsers.
  Author:                Michael De Pasquale
  Creation Date:         2024-11-20
  Modification Date:     2025-03-27

"""

# NOTE: Dictionary keys shouldn't be considered meaningful and must not be used outside
# of parsers.

# pylint: disable=too-few-public-methods, import-error

from datetime import datetime, timezone
from enum import Enum
import json
from typing import Union

from pydantic import (
    BaseModel,
    Field,
    model_validator,
    field_serializer,
    field_validator,
)


class MarketType(Enum):
    """Type of betting market."""

    # Betting on a given participant winning. Draw is not an outcome.
    # AKA "Money Line", "Head to Head"
    WINNER = "WINNER"

    # Betting on either participant winning or a draw
    WINNER_DRAW = "WINNER_DRAW"

    # AKA handicap.
    # Betting on a given participant winning, but result is adjusted based on a score
    # threshold
    LINE = "LINE"

    # If not known
    UNKNOWN = "UNKNOWN"


class AgencyData(BaseModel):
    """Root node for parsed results for an agency."""

    agencyName: str
    sports: dict[str, "AgencySport"] = Field(default_factory=dict)

    def save(self, path: str) -> None:
        """Write to file."""
        with open(path, "w", encoding="utf8") as f:
            json.dump(
                self.model_dump(mode="json"), f, indent=4, separators=(", ", ": ")
            )

    @classmethod
    def load(cls, path: str) -> None:
        """Load from file."""
        return cls.parse_file(path)


class AgencySport(BaseModel):
    """Represents a given sport."""

    name: str

    agencyId: Union[str, int, None] = None

    # Leagues/comps for sport. Keys are whatever is convenient for the parser and
    # shouldn't be used.
    competitions: dict[str, "AgencyCompetition"] = Field(default_factory=dict)


class AgencyCompetition(BaseModel):
    """Represents a league/competition."""

    name: str
    agencyId: Union[str, int, None] = None
    events: dict[str, "AgencyEvent"] = Field(default_factory=dict)


class AgencyEvent(BaseModel):
    """Represents a sports match"""

    # Start time for event, must be UTC
    start: datetime
    name: Union[str, None] = None
    agencyId: Union[str, int, None] = None
    participants: dict[str, "AgencyParticipant"] = Field(default_factory=dict)
    markets: dict[str, "AgencyMarket"] = Field(default_factory=dict)

    @model_validator(mode="after")
    def checkTZ(self) -> "AgencyEvent":
        """Check timezone is UTC."""
        if self.start.tzinfo != timezone.utc:
            raise ValueError(f"Bad timezone (expected UTC, got {self.start.tzinfo})")

        return self

    @field_serializer("start")
    def serialiseStart(self, start: datetime, _info) -> str:
        """Serialise start time."""
        return start.isoformat()

    @field_validator("start", mode="before")
    @classmethod
    def deserialiseStart(cls, start: Union[str, datetime]) -> set:
        """Deserialise start time."""
        if isinstance(start, str):
            return datetime.fromisoformat(start)

        return start


# TODO: Maybe better to just use set of participants?
# Not sure anything else needs to be in this except name.
class AgencyParticipant(BaseModel):
    """Represents a participant/team."""

    name: str


class AgencyMarket(BaseModel):
    """Represents a betting market."""

    name: str
    # FIXME: disallow None?
    marketType: Union[MarketType, None] = Field(
        default_factory=lambda: MarketType.UNKNOWN
    )
    outcomes: dict[str, "AgencyMarketOutcome"] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ensureValid(self) -> "AgencyMarket":
        """Model-level validation"""
        if self.marketType == MarketType.UNKNOWN:
            raise ValueError("Invalid market (unknown type)")

        # WINNER_DRAW: Must have one draw
        if self.marketType == MarketType.WINNER_DRAW:
            if len(list(filter(lambda o: o.isDraw, self.outcomes.values()))) != 1:
                raise ValueError(f"Invalid market (1 draw expected): {self}")

            # Must have 3 outcomes
            if len(self.outcomes) != 3:
                raise ValueError(f"Invalid market (expected 3 outcomes): {self}")

        # WINNER: No draw, at least 2 outcomes
        if self.marketType == MarketType.WINNER:
            if any(map(lambda o: o.isDraw, self.outcomes.values())):
                raise ValueError(f"Invalid market (WINNER with draw!): {self}")

            if len(self.outcomes) < 2:
                raise ValueError(f"Invalid market (too few outcomes): {self}")

        return self


class AgencyMarketOutcome(BaseModel):
    name: str

    # Price, must be decimal.
    price: float

    # The participant the outcome is associated with (e.g. winner, first scorer etc)
    associatedParticipant: Union["AgencyParticipant", None] = Field(default=None)

    isDraw: bool = False

    @model_validator(mode="after")
    def ensureValid(self) -> "AgencyMarketOutcome":
        """Perform model-level validation after instantiation."""
        # Must either be a draw, or have an associated participant, and not both
        if (self.isDraw is False) == (self.associatedParticipant is None):
            raise ValueError(f"Invalid outcome, isDraw with participant: {self}")

        # Price must be positive
        if self.price <= 0:
            raise ValueError(f"Invalid price: {self.price}")

        return self
