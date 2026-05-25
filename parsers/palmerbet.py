#!/usr/bin/env python3
"""
  palmerbet.py
  ============

  Description:           Palmerbet parser
  Author:                Michael De Pasquale
  Creation Date:         2025-03-23
  Modification Date:     2025-03-27

"""

from scrapers.palmerbet import PalmerbetScraperResult
from .base_parser import BaseParser
from .types import (
    AgencyMarket,
    AgencyMarketOutcome,
    MarketType,
)


class PalmerbetParser(BaseParser):
    @property
    def agencyName(self) -> str:
        """Return the name of the agency."""
        return "Palmerbet"

    def _parseResult(self, result: PalmerbetScraperResult) -> None:
        # NOTE: More (unsupported) markets are available in match.additionalMarkets
        for key, expected in (("status", "NotStarted"), ("state", "Other")):
            if result.match[key] == expected:
                continue

            self._log.debug(
                f"Skipping match with unexpected {key} {result.match[key]}: {result}"
            )

            return

        if "win" not in result.match["homeTeam"]:
            self._log.debug(f"Skipping match without win/win-draw markets: {result}")

            return

        elif "price" not in result.match["homeTeam"]["win"]:
            self._log.debug(f"Skipping match with missing win price: {result}")

            return

        sport = self._getSport(result.sport["title"], result.sport["id"])
        comp = self._getCompetition(sport, result.league["title"], result.league["id"])
        event = self._getEvent(
            comp,
            # No convenient name available. Construct one for consistency, though
            # unnecessary since name isn't used for anything important
            " vs ".join(
                (
                    result.match["homeTeam"]["title"],
                    result.match["awayTeam"]["title"],
                )
            ),
            self.parseISO8601(result.match["startTime"]),
            [
                result.match["homeTeam"]["title"],
                result.match["awayTeam"]["title"],
            ],
        )
        outcomes = {
            result.match[key]["title"]: AgencyMarketOutcome(
                name=result.match[key]["title"],
                price=result.match[key]["win"]["price"],
                associatedParticipant=event.participants[result.match[key]["title"]],
            )
            for key in ("homeTeam", "awayTeam")
        }

        marketTypeName = result.match["homeTeam"]["win"]["type"]
        assert marketTypeName in ("Win", "WinDraw")
        marketType = (
            MarketType.WINNER if marketTypeName == "Win" else MarketType.WINNER_DRAW
        )

        if marketType == MarketType.WINNER_DRAW:
            outcomes["draw"] = AgencyMarketOutcome(
                name="draw", price=result.match["draw"]["price"], isDraw=True
            )

        event.markets[marketTypeName] = AgencyMarket(
            name=marketTypeName, outcomes=outcomes, marketType=marketType
        )
