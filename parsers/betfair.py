#!/usr/bin/env python3
"""
  betfair.py
  ==========

  Description:           Betfair parser
  Author:                Michael De Pasquale
  Creation Date:         2025-02-21
  Modification Date:     2025-04-13

"""

from typing import Union

from scrapers.betfair import BetfairScraperResult
from .base_parser import BaseParser
from .types import (
    AgencyEvent,
    AgencyMarket,
    AgencyMarketOutcome,
    MarketType,
)

# FIXME: Currently no way to get participants for results that aren't win/win-draw
# markets. This is fine for now since nothing else is supported. Ideally the scraper
# would group all markets for an event to allow identifying participants for that event

# Minimum exchange back size to consider
SIZE_THRESHOLD = 100


class BetfairParser(BaseParser):
    @property
    def agencyName(self) -> str:
        """Return the name of the agency."""
        return "Betfair"

    def _getMarketType(self, result: BetfairScraperResult) -> MarketType:
        typeName = result.marketMeta["marketType"]

        if typeName in (
            # This should always have draw, but check anyway to be safe.
            "MATCH_ODDS_LO_TIE",
            "HEAD_TO_HEAD",
            "MATCH_ODDS",
            "MATCH_ODDS_LO_TIE",
            "OUTRIGHT_WINNER",
            "WINNER",
        ):
            if len(result.marketNode["runners"]) > 2:
                if any(
                    self._isDrawName(r["description"]["runnerName"])
                    for r in result.marketNode["runners"]
                ):
                    return MarketType.WINNER_DRAW

                # Skip these even though they should work. See note in SportsbetParser.
                self._log.warning(
                    f"Ignoring unsupported winner/match_odds market: >2 options with no draw"
                )

                return MarketType.UNKNOWN

            return MarketType.WINNER

        return MarketType.UNKNOWN

    def _getParticipants(
        self, marketType: MarketType, result: BetfairScraperResult
    ) -> Union[list[str], None]:
        """Return a list of participant names, or None if unsuccessful."""
        runnerNames = [
            r["description"]["runnerName"] for r in result.marketNode["runners"]
        ]

        if marketType == MarketType.WINNER:
            assert len(runnerNames) == 2
            assert not any(map(self._isDrawName, runnerNames))

            return runnerNames

        if marketType == MarketType.WINNER_DRAW:
            runnerNames = list(filter(lambda r: not self._isDrawName(r), runnerNames))
            assert len(runnerNames) == 2

            return runnerNames

        return None

    def _getRepresentativeBackPrice(self, back: list) -> Union[float, None]:
        # TODO: Discard 'outliers' i.e. size is below some threshold, or is too
        # different?
        # REVIEW: Not sure if this is appropriate, maybe just use best price?

        assert back
        sizeSum = sum(b["size"] for b in back)

        if sizeSum < SIZE_THRESHOLD:
            return None

        return sum(b["price"] * b["size"] / sizeSum for b in back)

    def _parseResult(self, result: BetfairScraperResult) -> None:
        # Ignore if no odds exist
        if not all(
            r["exchange"].get("availableToBack", None)
            for r in result.marketNode["runners"]
        ):
            self._log.debug(f"No market data available! {repr(result)}")

            return

        marketType = self._getMarketType(result)

        if marketType == MarketType.UNKNOWN:
            self._log.debug(f"Unsupported market type! {repr(result)}")

            return

        participants = self._getParticipants(marketType, result)

        if not participants:
            self._log.warning(f"Failed to get participants! {repr(result)}")

            return

        sport = self._getSport(
            result.sportName.replace("_", " ").title(),
            result.sportName,
        )
        comp = self._getCompetition(sport, result.leagueName, None)

        event = None

        # Need to handle duplicate events
        try:
            event = self._getEvent(
                comp,
                result.marketMeta["eventName"],
                # NOTE: marketNode.description.marketTime/suspendTime also exist, all
                # 3 seem to be the same.
                # Not match start time, checked some examples and one was 2 hours later,
                # another ~2 days before..
                self.parseISO8601(result.marketMeta["marketStartTime"]),
                participants,
            )

        except ValueError:
            self._log.exception(f"Failed to retrieve event for {repr(result)}")

            return

        outcomes = {}

        for runner in result.marketNode["runners"]:
            assert not runner["handicap"]

            name = runner["description"]["runnerName"]
            isDraw = self._isDrawName(name)
            price = self._getRepresentativeBackPrice(
                runner["exchange"]["availableToBack"]
            )

            if price is None:
                self._log.debug(f"Unable to get price! {repr(result)}")

                return

            outcomes[name] = AgencyMarketOutcome(
                name=name,
                price=price,
                associatedParticipant=(
                    event.participants[name] if not isDraw else None
                ),
                isDraw=isDraw,
            )

        self._log.debug(f"Processed result {repr(result)}")
        event.markets[result.marketMeta["name"]] = AgencyMarket(
            name=result.marketMeta["name"], outcomes=outcomes, marketType=marketType
        )
