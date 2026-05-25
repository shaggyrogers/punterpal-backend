#!/usr/bin/env python3
"""
  pointsbet.py
  ============

  Description:           Pointsbet parser
  Author:                Michael De Pasquale
  Creation Date:         2025-03-20
  Modification Date:     2025-10-05

"""

from scrapers.pointsbet import PointsbetScraperResult
from .base_parser import BaseParser, AmbiguousEventException
from .types import (
    AgencyMarket,
    AgencyMarketOutcome,
    MarketType,
)


# NOTE: Have access to results (event.score)


class PointsbetParser(BaseParser):
    @property
    def agencyName(self) -> str:
        """Return the name of the agency."""
        return "Pointsbet"

    def _getMarketType(self, result: PointsbetScraperResult) -> MarketType:
        if result.market["eventName"] in (
            "Head to Head",
            "Match Result",
            "Moneyline",
            "Money Line",
        ):
            # market.includesDraw can't be trusted
            # Don't seem to be any markets with a draw? but check anyway
            # Could also check teamId or side?
            hasDraw = any(
                map(self._isDrawName, (o["name"] for o in result.market["outcomes"]))
            )

            if len(result.market["outcomes"]) != 2 + (1 if hasDraw else 0):
                self._log.error(
                    f"Unexpected result count! count={len(result.market["outcomes"])}"
                    f" expected={2 + (1 if hasDraw else 0)}"
                )

                return MarketType.UNKNOWN

            return MarketType.WINNER_DRAW if hasDraw else MarketType.WINNER

        return MarketType.UNKNOWN

    def _parseResult(self, result: PointsbetScraperResult) -> None:
        if result.market["isEventStarted"] or not result.market["isOpenForBetting"]:
            self._log.debug(
                f"Skipping result (started, abandoned or not open) {repr(result)}"
            )

            return

        assert result.market["outcomes"]

        marketType = self._getMarketType(result)

        if marketType == MarketType.UNKNOWN:
            self._log.debug(f"Skipping unsupported market {repr(result)}")

            return

        sport = self._getSport(result.event["sportName"], result.event["sportKey"])
        comp = self._getCompetition(
            sport,
            result.event["competitionName"],
            result.event["competitionKey"],
        )

        try:
            event = self._getEvent(
                comp,
                result.event["name"],
                # Also exists market.advertisedStartTime, market.bettingCloseTime
                self.parseISO8601(result.event["startsAt"]),
                # Need to use outcome names here, team names differ
                [
                    o["name"]
                    for o in result.market["outcomes"]
                    if not self._isDrawName(o["name"])
                ],
            )

        except AmbiguousEventException:
            self._log.exception(f"Ignoring ambiguous event! result: {repr(result)}")

            return

        outcomes = {}

        for outcome in result.market["outcomes"]:
            if not outcome["isOpenForBetting"] or outcome["isHidden"]:
                self._log.debug(
                    f"Ignoring market: outcome closed or hidden {repr(result)}"
                )

                return

            name = outcome["name"]
            isDraw = self._isDrawName(name)

            assert isDraw or name in event.participants

            outcomes[name] = AgencyMarketOutcome(
                name=name,
                price=outcome["price"],
                associatedParticipant=None if isDraw else event.participants[name],
                isDraw=isDraw,
            )

        event.markets[result.market["name"]] = AgencyMarket(
            name=result.market["name"],
            outcomes=outcomes,
            marketType=marketType,
        )
