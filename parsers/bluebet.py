#!/usr/bin/env python3
"""
  bluebet.py
  ==========

  Description:           Parse scraped results from bluebet
  Author:                Michael De Pasquale
  Creation Date:         2025-04-04
  Modification Date:     2025-10-05

"""

from collections import defaultdict

from scrapers.bluebet import BluebetScraperResult
from .base_parser import BaseParser, AmbiguousEventException
from .types import (
    AgencyMarket,
    AgencyMarketOutcome,
    MarketType,
)


class BluebetParser(BaseParser):
    @property
    def agencyName(self) -> str:
        """Return the name of the agency."""
        # Rebranded as 'betr'
        return "Bluebet"

    def _getMarketType(self, market: list) -> MarketType:
        # MarketTypeCode should be the same
        assert market
        assert all(
            map(
                lambda o: o["MarketTypeCode"] == market[0]["MarketTypeCode"], market[1:]
            )
        )

        # Only support WINNER/WINNER_DRAW
        if market[0]["MarketTypeCode"] != "WIN":
            self._log.debug(
                f"Ignoring unsupported market type: {market[0]['MarketTypeCode']}"
            )

            return MarketType.UNKNOWN

        # Check for draw
        hasDraw = any(map(self._isDrawName, [o["OutcomeName"] for o in market]))

        if hasDraw:
            if len(market) != 3:
                # FIXME: Should look into what is happening here...
                self._log.error(
                    f"Unexpected draw for market with {len(market)} outcomes!"
                )

                return MarketType.UNKNOWN

            return MarketType.WINNER_DRAW

        return MarketType.WINNER

    def _parseResult(self, result: BluebetScraperResult) -> None:
        if "Markets" not in result.event or not result.event["Markets"]:
            self._log.debug(f"Skipping result with no/missing markets: {repr(result)}")

            return

        if result.category.endswith("Futures"):
            self._log.debug(f"Skipping futures market(s): {repr(result)}")

            return

        # Group outcomes by MarketTypeCode
        markets = defaultdict(list)

        for outcome in result.event["Markets"]:
            markets[outcome["MarketTypeCode"]].append(outcome)

        for market in markets.values():
            self._parseMarket(result, market)

    def _parseMarket(self, result: BluebetScraperResult, market: list) -> None:
        marketType = self._getMarketType(market)

        if marketType == MarketType.UNKNOWN:
            return

        participants = [
            o["OutcomeName"] for o in market if not self._isDrawName(o["OutcomeName"])
        ]

        if len(participants) <= 1:
            self._log.debug(f"Skipping result (too few participants) {repr(result)}")

            return

        # NOTE: Ignoring masterCategory here.
        sport = self._getSport(
            result.eventType,
            result.eventTypeId,
        )
        comp = self._getCompetition(
            sport,
            result.category,
            # Duplicates exist with different IDs
            None,  # result.categoryId
        )

        try:
            event = self._getEvent(
                comp,
                result.event["MasterEventName"],
                self.parseISO8601(result.event["MinAdvertisedStartTime"]),
                [
                    o["OutcomeName"]
                    for o in market
                    if not self._isDrawName(o["OutcomeName"])
                ],
            )

        except AmbiguousEventException:
            self._log.exception(f"Ignoring ambiguous event! result: {repr(result)}")

            return

        outcomes = {}

        for outcome in market:
            # NOTE: IsOpenForBetting is always False
            isDraw = self._isDrawName(outcome["OutcomeName"])
            outcomes[outcome["OutcomeName"]] = AgencyMarketOutcome(
                name=outcome["OutcomeName"],
                price=outcome["Price"],
                associatedParticipant=(
                    None if isDraw else event.participants[outcome["OutcomeName"]]
                ),
                isDraw=isDraw,
            )

        event.markets[market[0]["MarketDesc"]] = AgencyMarket(
            name=market[0]["MarketDesc"], outcomes=outcomes, marketType=marketType
        )
