#!/usr/bin/env python3
"""
  sportsbet.py
  ============

  Description:           Parser for sportsbet
  Author:                Michael De Pasquale
  Creation Date:         2024-12-13
  Modification Date:     2026-05-25

"""

from scrapers.sportsbet import SportsbetScraperResult
from .base_parser import BaseParser, AmbiguousEventException
from .types import (
    AgencyMarket,
    AgencyMarketOutcome,
    MarketType,
)


class SportsbetParser(BaseParser):
    """Parses Sportsbet scraper output."""

    @property
    def agencyName(self) -> str:
        """Return the name of the agency."""
        return "Sportsbet"

    def _getMarketType(self, result: SportsbetScraperResult) -> None:
        typeName = result.market["name"]

        # Draw No Bet: Bet on winner, draw means wager is refunded
        if typeName == "Draw No Bet":
            return MarketType.WINNER

        # Match Betting: Bet on winner. May or may not have draw.
        if typeName in (
            "Match Betting",
            "Head to Head",
            "Boxing Match Betting",
            "Money Line",
        ):
            # Fail if handicap exists
            if any(
                "unformattedHandicap" in sel or "displayHandicap" in sel
                for sel in result.market["selections"]
            ):
                self._log.warning(
                    f"Unexpected handicap in winner market typeName={typeName}"
                    f" result={repr(result)}"
                )
                return MarketType.UNKNOWN

            if len(result.market["selections"]) > 2:
                # Check for a 'Draw' option, default to 'Unknown' if not found
                if any(
                    s["name"].lower().startswith("draw")
                    for s in result.market["selections"]
                ):
                    return MarketType.WINNER_DRAW

                # FIXME: These would probably work fine, but there will usually be
                # ~10+ options, which means 1. we need at least that many agencies, and
                # 2. we will need to consider a large number of agency-outcome
                # permutations (e.g. for 10 there are ~3.5 million!)
                self._log.warning(
                    "Ignoring unsupported 'Match Betting' market: >2 options with no draw!"
                    f" selections: {result.market['selections']} result: {repr(result)}"
                )
                return MarketType.UNKNOWN

            return MarketType.WINNER

        # 'Win-Draw-Win' - Always has draw.
        if typeName == "Win-Draw-Win":
            return MarketType.WINNER_DRAW

        self._log.debug(f"Ignoring unsupported market type: '{typeName}'")

        return MarketType.UNKNOWN

    def _getParticipants(
        self, result: SportsbetScraperResult, marketType: MarketType
    ) -> list:
        """Find event participants."""
        if all(result.event[k] for k in ("participant1", "participant2")):
            return [result.event["participant1"], result.event["participant2"]]

        # participant1/2 are not set for some events e.g. MMA.
        if marketType in (MarketType.WINNER, MarketType.WINNER_DRAW):
            return [
                sel["name"]
                for sel in result.market["selections"]
                if not self._isDrawName(sel["name"])
            ]

        return None

    def _parseResult(self, result: SportsbetScraperResult) -> None:
        """Parse one single result, updating _data."""
        # FIXME: Supply agency IDs where they exist!
        sportName = result.page["name"]
        leagueName = result.event["competitionName"]
        eventName = result.event["name"]
        assert all((sportName, leagueName, eventName))

        # Find or make sport, league, event, get market type
        sport = self._getSport(sportName, result.page["classId"])
        comp = self._getCompetition(sport, leagueName, result.event["competitionId"])
        marketType = self._getMarketType(result)
        participants = self._getParticipants(result, marketType)

        if not participants or not all(participants):
            self._log.debug(f"Failed to get participants for {repr(result)}")

            return

        # FIXME: Need to compare with other agencies to see if we need to
        # adjust based on timezone.
        try:
            event = self._getEvent(
                comp,
                eventName,
                self.parseTimestamp(result.event["startTime"]),
                participants,
            )

        except AmbiguousEventException:
            self._log.exception(f"Ignoring ambiguous event! result: {repr(result)}")

            return

        if not all([sport, comp, event]) or marketType == MarketType.UNKNOWN:
            self._log.debug(f"Skipping unsupported result node: {repr(result)}")

            return

        # Handle markets
        outcomes = {}

        for selection in result.market["selections"]:
            isDraw = self._isDrawName(selection["name"])

            if not isDraw and selection["name"] not in event.participants:
                self._log.debug(
                    f"Skipping result node (unknown participant '{selection['name']}')"
                    f" {repr(result)}"
                )

                return

            # Shouldn't have a participant named 'Draw' / "Tie"
            assert not (isDraw and selection["name"] in event.participants)

            # Shouldn't have duplicates here.
            assert selection["name"] not in outcomes

            outcomes[selection["name"]] = AgencyMarketOutcome(
                name=selection["name"],
                price=selection["price"]["winPrice"],
                associatedParticipant=(
                    event.participants[selection["name"]] if not isDraw else None
                ),
                isDraw=isDraw,
            )

        # FIXME: Not sure if this is because only 1 outcome is offered, or if there's
        # a deeper issue with scraping/parsing...
        if len(outcomes) == 1:
            self._log.warning(f"Skipping market (only 1 outcome!) {repr(result)}")

            return

        # Add market to event
        event.markets[result.market["name"]] = AgencyMarket(
            name=result.market["name"], marketType=marketType, outcomes=outcomes
        )
