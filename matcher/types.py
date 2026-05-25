#!/usr/bin/env python3
"""
  types.py
  ========

  Description:           TODO
  Author:                Michael De Pasquale
  Creation Date:         2025-01-20
  Modification Date:     2025-08-29

"""
# Very similar to parsers.types...
# pylint: disable=too-few-public-methods

from collections import defaultdict
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

from parsers.types import MarketType


class MatchFailure(BaseModel):
    name: str
    bestMatch: str
    score: float
    subScores: dict


class LeagueMatchFailure(MatchFailure):
    sport: str


class EventMatchFailure(LeagueMatchFailure):
    league: str


class MatchStats(BaseModel):
    """Update/matching stats for an agency."""

    unknownSports: int = 0
    unknownComps: int = 0
    unknownEvents: int = 0
    updatedMarkets: int = 0
    matchFailures: list[Union[MatchFailure, LeagueMatchFailure, EventMatchFailure]] = (
        Field(default_factory=list)
    )
    lastUpdated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            + ", ".join(
                (
                    f"unknownSports={self.unknownSports}",
                    f"unknownComps={self.unknownComps}",
                    f"unknownEvents={self.unknownEvents}",
                    f"updatedMarkets={self.updatedMarkets}",
                )
            )
            + ")"
        )

    @field_serializer("lastUpdated")
    @classmethod
    def serialiseLastUpdated(cls, lastUpdated: datetime, _info) -> str:
        """Serialise last market update timestamp."""
        return lastUpdated.isoformat()

    @field_validator("lastUpdated", mode="before")
    @classmethod
    def deserialiseLastUpdated(cls, lastUpdated: Union[str, datetime]) -> datetime:
        """Parse last market update timestamp."""
        if isinstance(lastUpdated, str):
            return datetime.fromisoformat(lastUpdated)

        return lastUpdated


class NameScoringType(Enum):
    """Represents different name similarity scoring methods."""

    # Inherit whatever the parent/default scoring method is.
    INHERIT = "INHERIT"

    # Generic scoring
    GENERIC = "GENERIC"

    # Geared toward personal names
    PERSONAL_NAME = "PERSONAL_NAME"

    # Geared towards leagues
    LEAGUE_NAME = "LEAGUE_NAME"

    def update(self, candidate: "NameScoringType") -> "NameScoringType":
        """Return self if candidate is INHERIT, otherwise candidate."""
        if candidate == NameScoringType.INHERIT:
            return self

        return candidate


class NamedBaseModel(BaseModel):
    """Model with name, synonyms and antonyms."""

    name: str

    synonyms: set[str] = Field(default_factory=set)

    # Use this for names that are similar, but definitely belong to something different
    # e.g. "Football" and "Floorball", "Baseball" and "Basketball"
    antonyms: set[str] = Field(default_factory=set)

    @model_validator(mode="after")
    def addNameToSynonyms(self) -> "CanonSport":
        """Ensure name is not empty, and add to synonyms if necessary."""
        if not self.name:
            raise ValueError("Name is required")

        if self.name not in self.synonyms:
            self.synonyms.add(self.name)

        return self

    @field_serializer("synonyms")
    @classmethod
    def serialiseSynonyms(cls, synonyms: set, _info) -> list:
        """Convert synonyms to list for serialisation."""
        return list(synonyms)

    @field_validator("synonyms", mode="before")
    @classmethod
    def deserialiseSynonyms(cls, synonyms: Union[list, set]) -> set:
        """Convert synonyms back to set after deseralisation"""
        return set(synonyms)

    @field_serializer("antonyms")
    @classmethod
    def serialiseAntonyms(cls, antonyms: set, _info) -> list:
        """Convert antonyms to list for serialisation."""
        return list(antonyms)

    @field_validator("antonyms", mode="before")
    @classmethod
    def deserialiseAntonyms(cls, antonyms: Union[list, set]) -> set:
        """Convert antonyms back to set after deseralisation"""
        return set(antonyms)


class CanonTree(BaseModel):
    """Root node of the canonical tree."""

    # Agency whose data was used to create this tree
    baseAgency: str

    sports: dict[str, "CanonSport"] = Field(default_factory=dict)

    # Scoring functions
    sportScorer: NameScoringType = NameScoringType.GENERIC
    defaultCompScorer: NameScoringType = NameScoringType.LEAGUE_NAME
    defaultPartScorer: NameScoringType = NameScoringType.GENERIC

    # Update timestamps/stats
    lastSchemaUpdate: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    stats: dict[str, MatchStats] = Field(default_factory=defaultdict(MatchStats))

    @property
    def agencies(self) -> set[str]:
        """Get set of agencies."""
        return set(self.stats.keys())

    # Serialisation/deserialisation methods
    def save(self, path: str) -> None:
        """Write to file."""
        with open(path, "w", encoding="utf8") as f:
            json.dump(
                self.model_dump(mode="json"), f, indent=4, separators=(", ", ": ")
            )

    @classmethod
    def load(cls, path: str) -> "CanonTree":
        """Load from file."""
        return cls.parse_file(path)

    def toJSON(self) -> str:
        """Convert to a JSON-encoded string"""
        return json.dumps(self.model_dump(mode="json"))

    @classmethod
    def fromJSON(cls, data: str) -> "CanonTree":
        """Deserialise CanonTree from JSON-format string."""
        return cls.model_validate_json(data)

    def setSchemaLastUpdated(self) -> None:
        """Set last schema update timestamp to current time."""
        self.lastSchemaUpdate = datetime.now(timezone.utc)

    def onUpdateStarted(self, agency: str) -> None:
        """Reset match/update statistics for agency. Must call once before updating"""
        if agency in self.stats:
            del self.stats[agency]

        # This creates new MatchStats with updated timestamp
        # pylint: disable=pointless-statement
        self.stats[agency]

    def recordMatchFail(
        self,
        agency: str,
        name: str,
        bestMatch: str,
        score: float,
        sport: str = None,
        league: str = None,
        **subScores,
    ) -> None:
        """Record match failure and update stats.
        Type is inferred from sport and league arguments."""
        assert not league or sport
        failCls = MatchFailure

        if not sport and not league:
            self.stats[agency].unknownSports += 1

        elif sport and not league:
            failCls = LeagueMatchFailure
            self.stats[agency].unknownComps += 1

        elif league:
            failCls = EventMatchFailure
            self.stats[agency].unknownEvents += 1

        self.stats[agency].matchFailures.append(
            failCls(
                name=name,
                bestMatch=bestMatch,
                score=score,
                subScores=subScores,
                sport=sport,
                league=league,
            )
        )

    @field_serializer("lastSchemaUpdate")
    @classmethod
    def serialiseLastSchemaUpdate(cls, ts: datetime, _info) -> str:
        """Serialise last schema update timestamp."""
        return ts.isoformat()

    @field_validator("lastSchemaUpdate", mode="before")
    @classmethod
    def deserialiseLastSchemaUpdate(cls, ts: Union[str, datetime]) -> datetime:
        """Parse last schema update timestamp."""
        if isinstance(ts, str):
            return datetime.fromisoformat(ts)

        return ts

    @field_validator("stats", mode="after")
    @classmethod
    def deserialiseStats(cls, stats: dict[str, MatchStats]) -> dict:
        # Promote to defaultdict
        if not isinstance(stats, defaultdict):
            tmp = defaultdict(MatchStats)
            tmp.update(stats)
            stats = tmp

        return stats

    @field_validator("sports")
    @classmethod
    def validateSportKeys(
        cls, sports: dict[str, "CanonSport"]
    ) -> dict[str, "CanonSport"]:
        """Ensure keys match names."""
        for key, sport in sports.items():
            if key != sport.name:
                raise ValueError(f"Sport key mismatch ({key} / {sport.name})")

        return sports


class CanonSport(NamedBaseModel):
    """Represents a sport."""

    competitions: dict[str, "CanonCompetition"] = Field(default_factory=dict)

    # Default scoring functions to use for competitions and participants in this sport.
    # partScorer can be replaced by CanonCompetition
    compScorer: NameScoringType = NameScoringType.INHERIT
    partScorer: NameScoringType = NameScoringType.INHERIT

    @field_validator("competitions")
    @classmethod
    def validateCompKeys(
        cls, competitions: dict[str, "CanonCompetition"]
    ) -> dict[str, "CanonCompetition"]:
        """Ensure keys match names."""
        for key, comp in competitions.items():
            if key != comp.name:
                raise ValueError(f"Competition key mismatch ({key} / {comp.name})")

        return competitions


class CanonCompetition(NamedBaseModel):
    """Represents a league/competition."""

    events: dict[str, "CanonEvent"] = Field(default_factory=dict)

    # All participants (teams) we know exist for this competition.
    participants: dict[str, "CanonParticipant"] = Field(default_factory=dict)

    # Default scoring function to use for participants
    partScorer: NameScoringType = NameScoringType.INHERIT

    @field_validator("events")
    @classmethod
    def validateEventKeys(
        cls, events: dict[str, "CanonEvent"]
    ) -> dict[str, "CanonEvent"]:
        """Ensure keys match names."""
        for key, event in events.items():
            if key != event.name:
                raise ValueError(f"Event key mismatch ({key} / {event.name})")

        return events


class CanonEvent(BaseModel):
    """Represents a match."""

    start: datetime
    markets: dict[MarketType, "CanonMarket"] = Field(default_factory=dict)

    # Names are keys for CanonCompetition.participants
    participantNames: set[str] = Field(default_factory=set)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            + ", ".join(
                (
                    f"start={self.start.isoformat()}",
                    f"participantNames={self.participantNames}",
                    f"markets.keys={list(self.markets.keys())}",
                )
            )
            + ")"
        )

    @property
    def name(self) -> str:
        """Return a key identifying this instance. Unique to parent node."""
        return f"{' v '.join(sorted(list(self.participantNames)))} @ {self.start.isoformat()}"

    @model_validator(mode="after")
    def ensureValid(self) -> "AgencyEvent":
        """Perform model-level validation"""
        # Check timezone is UTC
        if self.start.tzinfo != timezone.utc:
            raise ValueError(f"Bad timezone (expected UTC, got {self.start.tzinfo})")

        # Check market keys match their value's marketType
        assert all(map(lambda tup: tup[1].marketType == tup[0], self.markets.items()))

        return self

    @field_serializer("start")
    @classmethod
    def serialiseStart(cls, start: datetime, _info) -> str:
        """Serialise start time."""
        return start.isoformat()

    @field_validator("start", mode="before")
    @classmethod
    def deserialiseStart(cls, start: Union[str, datetime]) -> datetime:
        """Parse start time."""
        if isinstance(start, str):
            return datetime.fromisoformat(start)

        return start

    @field_serializer("participantNames")
    @classmethod
    def serialiseParticipantNames(cls, participantNames: datetime, _info) -> list:
        """Convert participantNames to list for serialisation."""
        return list(participantNames)

    @field_validator("participantNames", mode="before")
    @classmethod
    def deserialiseParticipantNames(cls, participantNames: Union[list, set]) -> set:
        """Convert participantNames back to set after deseralisation"""
        return set(participantNames)


class CanonParticipant(NamedBaseModel):
    """Represents a team in a match."""


class CanonMarket(BaseModel):
    """Represents a betting market for a match."""

    marketType: MarketType

    # Unlike AgencyMarket, None is used as a key for a draw.
    outcomes: dict[Union[str, None], "CanonMarketOutcome"] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ensureValid(self) -> "CanonMarket":
        """Perform model-level validation"""
        # Market type must not be unknown
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

        # Check that we have the same set of agencies for each outcome
        agencies = [set(o.prices.keys()) for o in self.outcomes.values()]

        if agencies and not all(a == agencies[0] for a in agencies):
            raise ValueError(f"Missing price(s) for one or more agencies: {agencies}")

        return self

    # NOTE: The key None will normally be converted to "None", so we need to swap key
    # here. Otherwise we will lose data on serialisation as an existing "None" value
    # will be overwritten.
    @field_serializer("outcomes")
    def serialiseOutcomes(self, outcomes: dict, _info) -> dict:
        """Serialise outcomes."""
        assert "_DRAW_KEY" not in outcomes

        if None in outcomes:
            # Must be a draw
            assert outcomes[None].isDraw

        return {("_DRAW_KEY" if k is None else k): v for k, v in outcomes.items()}

    @field_validator("outcomes", mode="before")
    @classmethod
    def deserialiseOutcomes(cls, outcomes: dict) -> set:
        """Deserialise outcomes."""
        if "_DRAW_KEY" in outcomes:
            assert outcomes["_DRAW_KEY"]["isDraw"]

        return {(None if k == "_DRAW_KEY" else k): v for k, v in outcomes.items()}


class CanonMarketOutcome(BaseModel):
    """Represents a possible outcome in a betting market."""

    # Participant associated with outcome (e.g. winner) or None if draw
    # Must be canonical name matching key in CanonCompetition.participants
    associatedParticipantName: Union[str, None]

    isDraw: bool = False

    # Decimal prices for each agency
    prices: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ensureValid(self) -> "CanonMarketOutcome":
        """Perform model-level validation after instantiation."""
        # Must either be a draw, or have an associated participant, and not both
        if (self.isDraw is False) == (self.associatedParticipantName is None):
            raise ValueError(f"Invalid outcome, isDraw with participant: {self}")

        # Prices must be positive
        if not all(map(lambda p: p > 0, self.prices.values())):
            raise ValueError(f"One or more prices are not positive! {self}")

        return self
