#!/usr/bin/env python3
"""
  dabble.py
  =========

  Description:           TODO
  Author:                Michael De Pasquale
  Creation Date:         2024-12-17
  Modification Date:     2025-03-18

"""

from typing import Union

from scrapers.dabble import DabbleScraperResult
from .base_parser import BaseParser
from .types import (
    AgencyEvent,
    AgencyMarket,
    AgencyMarketOutcome,
    MarketType,
)


class DabbleParser(BaseParser):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # Not ideal, many diff resultingType values..
        self._winnerMarkets = {
            "fight_winner",
            "match_result_(inc_overtime)",
            "match_result_no_overtime",
            "match_result_with_overtime",
            "match_winner",
            "MatchWinner",
            "match_winner_no_draw",
            "draw_no_bet",
            "Win_Draw_No_Bet",
            "Winner",
            "winner-2-way",
            "winner-3-way",
            "winner-2-way-draw-no-bet",
        }

    @property
    def agencyName(self) -> str:
        """Return the name of the agency."""
        return "Dabble"

    def _getMarketType(self, market: dict[str, object]) -> MarketType:
        """Return MarketType for the given market dict.
        Market dict has form {"market": {}, "selections": [...]}
        """
        # Only 1 winner. Should always be 1?
        if market["market"]["expectedWinners"] != 1:
            self._log.debug(f"Skipping market; expectedWinners not 1: {market}")

            return MarketType.UNKNOWN

        # Don't support any of these yet.
        if any(
            [
                market["market"]["isFuture"],
                market["market"]["isHandicap"],
                market["market"]["isAllIn"],
                market["market"]["isTotal"],
            ]
        ):
            self._log.debug("Skipping market (future/handicap/allIn/total)")

            return MarketType.UNKNOWN

        # Only support WINNER, WINNER_DRAW
        if market["market"]["resultingType"] not in self._winnerMarkets:
            self._log.debug(
                f"Skipping unsupported market '{market['market']['resultingType']}'"
            )

            return MarketType.UNKNOWN

        # Only support 2/3 outcomes
        numSel = len(market["selections"])

        if not 2 <= numSel <= 3:
            self._log.debug(f"Skipping unsupported market ({numSel} outcomes)")

            return MarketType.UNKNOWN

        # Use selection name/number to determine if WINNER or WINNER_DRAW
        if any(self._isDrawName(s["name"]) for s in market["selections"]):
            assert len(market["selections"]) == 3

            return MarketType.WINNER_DRAW

        return MarketType.WINNER

    def _getParticipants(self, markets: dict[str, dict]) -> Union[list[str], None]:
        """Try to find a list of participant names, returning None if unsuccessful."""
        # Find winner or winner-draw and use selection names
        for marketDict in markets.values():
            marketType = self._getMarketType(marketDict)

            if marketType == MarketType.WINNER:
                assert len(marketDict["selections"]) == 2

                return [s["name"] for s in marketDict["selections"]]

            if marketType == MarketType.WINNER_DRAW:
                assert len(marketDict["selections"]) == 3

                return list(
                    filter(
                        lambda n: not self._isDrawName(n),
                        map(lambda s: s["name"], marketDict["selections"]),
                    )
                )

        return None

    def _parseResult(self, result: DabbleScraperResult) -> None:
        if result.sport["isRacing"] or result.sport["isHidden"]:
            # Shouldn't happen, we only get sports
            self._log.debug("Skipping result node (racing or hidden)")

            return

        if result.event["status"].lower() != "open":
            self._log.debug("Skipping result node (not open)")

            return

        sport = self._getSport(result.sport["name"], result.sport["id"])
        comp = self._getCompetition(sport, result.league["name"], result.league["id"])

        if not all([sport, comp]):
            self._log.debug(
                "Skipping unsupported result (failed to get sport or comp.)"
            )

            return

        # Group markets/selections/prices
        # Make {market ID : {"market": {..}, "selections": [selection1+price1, ...]}}
        selectionLookup = {s["id"]: s for s in result.event["selections"]}
        marketSelections = {
            m["id"]: {
                "market": m,
                "selections": [],
            }
            for m in result.event["markets"]
            if m["status"].lower() == "open" and m["isDisplayed"]
        }

        for price in result.event["prices"]:
            selection = selectionLookup[price["selectionId"]]

            # Ignore if we already removed market
            if price["marketId"] not in marketSelections:
                continue

            # Remove market if any selection is bad
            if not selection["isDisplayed"] or selection["isScratched"]:
                self._log.debug(
                    "Skipping market (selection not displayed or scratched)"
                    f" {marketSelections[price['marketId']]['market']['name']} /"
                    f" {selection['name']}"
                )
                del marketSelections[price["marketId"]]

                continue

            # FIXME: This fails.. why?
            # Maybe continue if price is in selection, but prices are the same?
            # assert "price" not in selection
            if "price" in selection:
                self._log.warning(
                    f"Skipping market: Selection with multiple prices!"
                    f" {marketSelections[price['marketId']]['market']['name']} /"
                    f" {selection['name']}"
                )
                del marketSelections[price["marketId"]]

                continue

            selection["price"] = price["price"]
            marketSelections[price["marketId"]]["selections"].append(selection)

        # Now we can get event, since we need to group market selections first
        participants = self._getParticipants(marketSelections)

        if not participants:
            self._log.debug(f"Skipping event (failed to get participants)")

            return

        # Has duplicate events with different start times!
        # Not sure why?
        try:
            event = self._getEvent(
                comp,
                result.event["name"],
                self.parseISO8601(result.event["advertisedStart"]),
                participants,
                result.event["id"],
            )

        except ValueError:
            self._log.exception(f"Ignoring event (bad/duplicate details)")

            return

        if event is None:
            return

        # Handle each market
        for marketDict in marketSelections.values():
            self._parseMarket(event, marketDict)

    def _parseMarket(self, event: AgencyEvent, market: dict[str, object]) -> None:
        # NOTE: We are doubling up on _getMarketType() calls..
        marketType = self._getMarketType(market)

        if marketType == MarketType.UNKNOWN:
            return

        outcomes = {}

        for selection in market["selections"]:
            name = selection["name"]
            isDraw = self._isDrawName(selection["name"])

            # FIXME: Possible for selection name to be different to participant names
            # e.g. Bayern Munich vs "B Munich win"
            # Just skip if this is the case for now.
            if not isDraw and name not in event.participants:
                self._log.warning(f"Skipping market, unknown participant '{name}'")

                return

            outcomes[name] = AgencyMarketOutcome(
                name=name,
                price=selection["price"],
                associatedParticipant=(
                    event.participants[name] if not isDraw else None
                ),
                isDraw=isDraw,
            )

        event.markets[market["market"]["name"]] = AgencyMarket(
            name=market["market"]["name"], outcomes=outcomes, marketType=marketType
        )
