#!/usr/bin/env python3
"""
  unibet.py
  =========

  Description:           TODO
  Author:                Michael De Pasquale
  Creation Date:         2024-12-17
  Modification Date:     2025-03-12

"""

from typing import Union

from scrapers.unibet import UnibetScraperResult
from .base_parser import BaseParser
from .types import (
    AgencyData,
    AgencySport,
    AgencyCompetition,
    AgencyEvent,
    AgencyParticipant,
    AgencyMarket,
    AgencyMarketOutcome,
    MarketType,
)


class UnibetParser(BaseParser):

    @property
    def agencyName(self) -> str:
        """Return the name of the agency."""
        return "Unibet"

    def _getMarketType(self, result: UnibetScraperResult) -> MarketType:
        betOfferType = result.betOffer["betOfferType"]["englishName"]
        # TODO: handicap

        if betOfferType == "Match":
            # Check for draw
            if any(s["type"] == "OT_CROSS" for s in result.betOffer["outcomes"]):
                assert len(result.betOffer["outcomes"]) > 2

                return MarketType.WINNER_DRAW

            return MarketType.WINNER

        return MarketType.UNKNOWN

    def _getCompetitionName(self, result: UnibetScraperResult) -> Union[str, None]:
        """Find most appropriate name for league/competition.

        Returns
        -------
        Tuple of form (name, adjusted) where if adjusted is True, then a modified
        league name was returned and the agencyId for the league is no longer valid.
        If not supported, name will be None.
        """
        name = result.event["group"]
        path = result.event["path"]

        # HACK: Collapse path when appropriate
        # Doesnt seem to be a better way to do this.. will probably need to be updated
        if len(path) == 3 and (
            name
            in (
                "Cup",
                "Cup Series",
                "Cup (W)",
                "Championship",
                "Division 1",
                "Division 2",
                "Premiership",
                "Elections",
                "Federal Election",
                "Super League",
                "Ligue 1",
                "League One",
                "League Two",
                "Premier League",
            )
            or path[0]["termKey"] == "gaelic_sports"
        ):
            assert len(path) == 3
            return (path[1]["englishName"] + " " + name, True)

        # e.g. Cricket/International Test Cricket/Matches
        if name in ("Matches", "Classification"):
            assert len(path) == 3
            return (path[1]["englishName"], True)

        # Unsupported for now due to awkward grouping
        if name.lower().startswith("esports battle") or name == "Unconfirmed Fights":
            return (None, True)

        if name in ("Upcoming Fights", "Race"):
            if len(path) > 2:
                # Motorsports / Rally / Race
                return (path[0]["englishName"] + " " + path[1]["englishName"], True)

            assert len(path) == 2
            return (path[0]["englishName"], True)

        return (name, False)

    def _parseResult(self, result: UnibetScraperResult) -> None:
        # REVIEW: Maybe better to use termKey?
        sportName = result.sport["name"]
        leagueName, adjustedLeague = self._getCompetitionName(result)
        eventName = result.event["name"]

        if not all((sportName, leagueName, eventName)):
            self._log.debug("Skipping unsupported result node")

            return

        # NOTE: Can get region for some leagues by checking path.. assume we don't need
        # for now.
        sport = self._getSport(sportName, result.sport["termKey"])

        try:
            comp = self._getCompetition(
                sport,
                leagueName,
                result.event["groupId"] if not adjustedLeague else None,
            )

        except KeyError:
            self._log.exception(
                "Skipping result node: duplicate comp key"
                f" sportName={sportName} leagueName={leagueName} eventName={eventName}"
            )

            return

        try:
            event = self._getEvent(
                comp,
                eventName,
                self.parseISO8601(result.event["start"]),
                [result.event.get("homeName"), result.event.get("awayName")],
                result.event["id"],
            )

        except (KeyError, ValueError):
            self._log.exception(
                f"Skipping event sportName={sportName} leagueName={leagueName} eventName={eventName}"
            )

            return

        marketType = self._getMarketType(result)

        # FIXME: Probably should clean this up, move to method
        outcomes = {}

        if marketType == MarketType.UNKNOWN:
            self._log.debug(
                f"Skipping unsupported result node"
                f" sport='{sportName}' league='{leagueName}' event='{eventName}'"
                f" marketType='{marketType}'"
            )

            return

        for outcome in result.betOffer["outcomes"]:
            if outcome["status"] == "SUSPENDED":
                self._log.debug("Skipping market (suspended)")

                return

            isDraw = outcome["type"] == "OT_CROSS"
            name = (
                outcome["englishLabel"]
                if (isDraw or "participant" not in outcome)
                else outcome["participant"]
            )

            assert isDraw or outcome["type"] in ("OT_ONE", "OT_TWO")
            assert name not in outcomes

            outcomes[name] = AgencyMarketOutcome(
                name=name,
                price=self.americanOddsToDecimal(outcome["oddsAmerican"]),
                associatedParticipant=(
                    event.participants[name] if not isDraw else None
                ),
                isDraw=isDraw,
            )

        event.markets[result.betOffer["betOfferType"]["englishName"]] = AgencyMarket(
            name=result.betOffer["betOfferType"]["englishName"],
            outcomes=outcomes,
            marketType=marketType,
        )
