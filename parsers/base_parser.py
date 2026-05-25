#!/usr/bin/env python3
"""
  base_parser.py
  ==============

  Description:           Parent class for parsers
  Author:                Michael De Pasquale
  Creation Date:         2024-12-13
  Modification Date:     2025-08-23

"""

from collections.abc import Iterable
from datetime import datetime, timezone, tzinfo
import logging
import math
from typing import Union

from .types import (
    AgencyData,
    AgencySport,
    AgencyCompetition,
    AgencyEvent,
    AgencyParticipant,
)

# Arbitrary threshold for determining whether two otherwise identical events with
# different start times should be considered the same.
SAME_EVENT_HOURS = 120  # 5 days


# FIXME: Remove the need for this... see _getEvent
class AmbiguousEventException(ValueError):
    """To be raised when two apparently identical events have sufficiently different
    start times.
    """


class BaseParser:
    """Functionality shared by parser classes."""

    def __init__(self) -> None:
        self._data = None
        self._log = logging.getLogger(
            self.__class__.__module__ + "." + self.__class__.__qualname__
        )
        self._log.setLevel("DEBUG")

    def parse(self, results: Iterable[object]) -> AgencyData:
        """Parse results and convert to agency-agnostic tree.
        Raises a pydantic ValidationError if unsuccessful.
        """
        self._data = AgencyData(agencyName=self.agencyName)

        for result in results:
            self._parseResult(result)

        # Remove any useless nodes
        self._cullResults()

        # TODO: unicode normalise everything here?

        # So we don't store reference, allowing gc to clear if possible
        result = self._data
        self._data = None

        return result

    # Implement these
    @property
    def agencyName(self) -> str:
        """Return the name of the agency."""
        raise NotImplementedError("Must implement agencyName()!")

    def _parseResult(self, result: object) -> None:
        """Attempt to parse a result node, updating self._data."""
        raise NotImplementedError("Must implement _parseResult()!")

    # These should cover most cases, override if needed
    def _getSport(self, name: str, agencyId: Union[str, int, None]) -> AgencySport:
        """Get AgencySport with given name, creating if necessary."""
        if name not in self._data.sports:
            self._data.sports[name] = AgencySport(name=name, agencyId=agencyId)

        sport = self._data.sports[name]
        assert sport.agencyId == agencyId

        return sport

    def _getCompetition(
        self, sport: AgencySport, name: str, agencyId: Union[str, int, None]
    ) -> AgencyCompetition:
        """Get/create AgencyCompetition for result."""
        if name not in sport.competitions:
            sport.competitions[name] = AgencyCompetition(
                name=name,
                agencyId=agencyId,
            )

        comp = sport.competitions[name]

        if comp.agencyId != agencyId:
            raise KeyError(f"Duplicate competition name detected: {name}")

        return comp

    def _getEvent(
        self,
        comp: AgencyCompetition,
        name: str,
        start: datetime,
        participants: list[str],
        agencyId: Union[str, int, None] = None,
    ) -> AgencyEvent:
        """Get/create AgencyEvent with the given details."""
        if name not in comp.events:
            # In case we get a generator, which we would prematurely exhaust
            if not isinstance(participants, list):
                participants = list(participants)

            if not participants or not all(participants):
                self._log.warning(
                    f"Skipping event: missing participant(s)! got {participants}"
                )

                return None

            # Should have at least 2 participants
            assert len(participants) > 1

            comp.events[name] = AgencyEvent(
                start=start,
                name=name,
                participants={p: AgencyParticipant(name=p) for p in participants},
                agencyId=agencyId,
            )

        event = comp.events[name]

        if event.start != start:
            self._log.warning(
                f"Duplicate event '{name}' (comp {comp.name}) with differing start"
            )

            # FIXME: This happens rarely. Either:
            # 1. Multiple events with same participants
            # 2. Time changed / is slightly different between results
            # Here just consider events the same if they are reasonably close together.
            # otherwise fail.
            # Probably best to address this by keying using day, X-day blocks or weeks.
            hoursDelta = abs((start - event.start).total_seconds()) / 3600

            if hoursDelta >= SAME_EVENT_HOURS:
                raise AmbiguousEventException(
                    f"Duplicate event '{name}' (comp {comp.name}) start delta exceeds"
                    f" threshold! hoursDelta={hoursDelta} threshold={SAME_EVENT_HOURS}"
                )

        if event.agencyId != agencyId:
            raise ValueError(
                f"Event '{name}' (comp {comp.name}) already exists with different ID!"
            )

        if not all(k in event.participants for k in participants):
            raise ValueError(f"Participant mismatch for existing event '{name}'")

        return event

    # Shouldn't need to override this.
    def _cullResults(self) -> None:
        """Remove any nodes with markets we couldn't parse."""
        for sportKey in list(self._data.sports.keys()):
            sport = self._data.sports[sportKey]
            sportMarketCount = 0

            for compKey in list(sport.competitions.keys()):
                comp = sport.competitions[compKey]
                compMarketCount = 0

                for eventKey in list(comp.events.keys()):
                    event = comp.events[eventKey]
                    compMarketCount += len(event.markets)
                    sportMarketCount += len(event.markets)

                    # No markets: cull event
                    if not event.markets:
                        self._log.debug(
                            f"Culling event (no markets): sport={sport.name}"
                            f" comp={comp.name} event={event.name}"
                        )
                        del comp.events[eventKey]

                # No markets: cull competition
                if not compMarketCount:
                    self._log.debug(
                        f"Culling competition (no markets): sport={sport.name}"
                        f" comp={comp.name}"
                    )
                    del sport.competitions[compKey]

            # No markets: cull sport
            if not sportMarketCount:
                self._log.debug(f"Culling sport (no markets): sport={sport.name}")
                del self._data.sports[sportKey]

    def _isDrawName(self, name: str) -> bool:
        """Return True if outcome name looks like it represents a draw, False
        otherwise.
        """
        return name.lower() in (
            "draw",
            "draw or technical draw",
            "the draw",
            "tie",
        )

    @staticmethod
    def parseTimestamp(
        timestamp: Union[int, float, str], tz: Union[str, tzinfo] = timezone.utc
    ) -> datetime:
        """Converts a POSIX timestamp (or POSIX-like timestamp, as returned by
        toTimestamp) to a timezone-aware datetime object.

        Parameters
        ----------
        timestamp : int or float or str
        A POSIX-like timestamp.

        tz : tzinfo, optional
        A tzinfo for a timezone to convert to. Default is timezone.UTC.

        Returns
        -------
        A timezone-aware datetime object. Raises an exception if unsuccessful.

        """
        if isinstance(timestamp, str):
            timestamp = float(timestamp)

        if timestamp < 0:
            raise ValueError("Timestamps cannot be negative")

        return datetime.fromtimestamp(timestamp, tz=tz)

    @staticmethod
    def parseISO8601(
        timestamp: str,
    ) -> datetime:
        """Converts an ISO8601 timestamp to a timezone-aware datetime object.

        Parameters
        ----------
        timestamp : str
        A datime representation in ISO 8601 format.

        Returns
        -------
        A timezone-aware datetime object. Raises a ValueError if unsuccessful.

        """
        # FIXME: datetime.fromisoformat() supports "Z" suffix in python3.11+
        if timestamp.endswith("Z"):
            dt = datetime.fromisoformat(timestamp[:-1]).replace(tzinfo=timezone.utc)

        else:
            dt = datetime.fromisoformat(timestamp)

        # Must have timezone
        if dt.tzinfo is None:
            raise ValueError(f"ISO timestamp missing timezone: '{timestamp}'")

        return dt

    @staticmethod
    def americanOddsToDecimal(american: Union[float, str]) -> float:
        """Converts american odds to decimal odds.

        Parameters
        ----------
        american : float or str
          American odds to convert to decimal.

        Returns
        -------
        The equivalent in decimal, as a float.
        """
        if isinstance(american, str):
            american = float(american)

        if not math.isfinite(american):
            raise ValueError(f"Value must be finite (got {american})")

        assert math.fabs(american) >= 100

        # Positive: amount won on a $100 bet
        if american >= 0:
            return (100 + american) / 100

        # Negative: amount required to win $100
        return (100 - american) / -american

    @staticmethod
    def fractionalOddsToDecimal(numerator: float, denominator: float) -> float:
        """Converts fractional odds to decimal."""
        assert numerator > 0 and denominator > 0

        return 1 + numerator / denominator


#  vim: set ts=4 sw=4 tw=88 fdm=expr ff=unix fenc=utf-8 et :
