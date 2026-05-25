#!/usr/bin/env python3
"""
  ladbrokes.py
  ============

  Description:           Ladbrokes parser
  Author:                Michael De Pasquale
  Creation Date:         2025-03-17
  Modification Date:     2025-08-23

"""

from typing import Union

from scrapers.ladbrokes import LadbrokesScraperResult
from .base_parser import BaseParser, AmbiguousEventException
from .types import (
    AgencyEvent,
    AgencyMarket,
    AgencyMarketOutcome,
    MarketType,
)


class LadbrokesParser(BaseParser):
    @property
    def agencyName(self) -> str:
        """Return the name of the agency."""
        return "Ladbrokes"

    def _getMarketType(self, result: LadbrokesScraperResult) -> MarketType:
        # Some markets just have one placeholder 'All Players' team, or null
        # Skip these, but could probably use market names for teams in these cases
        if result.event["teams"] is None:
            self._log.debug(f"Skipping result - missing teams: {repr(result)}")

            return MarketType.UNKNOWN

        entrantCount = result.market["entrantCount"]
        teamCount = len(result.event["teams"])

        if teamCount <= 1:
            self._log.debug(f"Skipping result - {teamCount} teams: {repr(result)}")

            return MarketType.UNKNOWN

        # Skip anything with >3 outcomes
        if entrantCount > 3:
            self._log.debug(
                f"Skipping result - {entrantCount} entrants: {repr(result)}"
            )

            return MarketType.UNKNOWN

        if result.market["name"].lower() in (
            "fight betting",
            "head to head",
            "match betting",
            "match result",
            "money line",
            "to qualify",
            "to win",
            "winner 2-way",
        ):
            # Check for draw
            hasDraw = any(
                map(
                    self._isDrawName,
                    (e["name"] for e in result.market["entrants"]["nodes"]),
                )
            )

            # Expect 2 or 3 outcomes, fail otherwise
            if teamCount + (1 if hasDraw else 0) != entrantCount:
                self._log.warning(
                    f"Unexpected outcome count! teamCount={teamCount}"
                    f" entrantCount={entrantCount} hasDraw={hasDraw}"
                )

                return MarketType.UNKNOWN

            return MarketType.WINNER_DRAW if hasDraw else MarketType.WINNER

        return MarketType.UNKNOWN

    def _parseResult(self, result: LadbrokesScraperResult) -> None:
        if result.market["isSuspended"] or result.market["handicap"] not in (None, 0):
            self._log.debug(
                f"Skipping unsupported result (suspended or handicap) {repr(result)}"
            )

            return

        if not result.market["entrants"]["nodes"]:
            self._log.debug(f"Skipping result (no markets) {repr(result)}")

            return

        marketType = self._getMarketType(result)

        if marketType == MarketType.UNKNOWN:
            self._log.debug(f"Skipping unsupported market for result {repr(result)}")

            return

        try:
            sport = self._getSport(result.category["name"], result.category["id"])
            comp = self._getCompetition(
                sport, result.competition["name"], result.competition["id"]
            )
            event = self._getEvent(
                comp,
                result.event["name"],
                self.parseISO8601(result.event["advertisedStart"]),
                # Need to use outcome names since team names don't always match
                [
                    e["name"]
                    for e in result.market["entrants"]["nodes"]
                    if not self._isDrawName(e["name"])
                ],
            )

        except KeyError as e:
            self._log.exception(
                f"Failed to retrieve sport, competition or event! result: {repr(result)}"
            )

            return

        except AmbiguousEventException as e:
            self._log.exception(f"Ignoring ambiguous event! result: {repr(result)}")

            return

        outcomes = {}

        for node in result.market["entrants"]["nodes"]:
            name = node["name"]
            isDraw = self._isDrawName(node["name"])

            assert isDraw or name in event.participants
            assert not isDraw or node["role"] is None

            if not (
                node["price"]["odds"]["numerator"]
                and node["price"]["odds"]["denominator"]
            ):
                # This happens sometimes
                self._log.debug(
                    f"Skipping invalid market (missing price for {name}) {repr(result)}"
                )

                return

            outcomes[name] = AgencyMarketOutcome(
                name=name,
                price=self.fractionalOddsToDecimal(
                    node["price"]["odds"]["numerator"],
                    node["price"]["odds"]["denominator"],
                ),
                associatedParticipant=None if isDraw else event.participants[name],
                isDraw=isDraw,
            )

        # self._log.debug(f"Processed result {repr(result)}")
        event.markets[result.market["name"]] = AgencyMarket(
            name=result.market["name"], outcomes=outcomes, marketType=marketType
        )
