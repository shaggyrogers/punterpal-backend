#!/usr/bin/env python3
"""
  betfair.py
  ==========

  Description:           TODO
  Author:                Michael De Pasquale
  Creation Date:         2024-12-09
  Modification Date:     2025-04-11

"""

from itertools import batched, chain
from collections.abc import Iterator

import gevent
from pydantic import BaseModel
import requests

from .base_scraper import BaseScraper


class BetfairScraperResult(BaseModel):
    sportName: str
    leagueName: str
    marketMeta: dict
    marketNode: dict

    def __repr__(self) -> str:
        return (
            f"BetfairScraperResult("
            + ", ".join(
                (
                    f"sport='{self.sportName}'",
                    f"league='{self.leagueName}'",
                    f"event='{self.marketMeta['eventName']}'",
                    f"market='{self.marketMeta['marketType']}'",
                )
            )
            + ")"
        )


class BetfairScraper(BaseScraper):

    def __init__(self) -> None:
        super().__init__(
            headers={
                "user-agent": "okhttp/4.9.2",
                "accept": "application/json",
                "x-application": "AYXCX3IlPt4vhUk3",
            }
        )

        self._hostNav = "https://production.ausnav.online"
        self._hostApi = "https://www.betfair.com.au"

    def _fetch(self, session: requests.Session) -> Iterator[BetfairScraperResult]:
        # Get list of sports
        page = session.get(
            f"{self._hostNav}/nav", params={"type": "list", "name": "all"}
        )

        # Get leagues for each sport
        return self._waitCollectResults(
            [
                gevent.spawn(self._fetchSport, session, sport)
                for sport in page.json()["Sports"]
            ]
        )

    def _fetchSport(
        self, session: requests.Session, sport: str
    ) -> Iterator[BetfairScraperResult]:
        self._log.debug(f"Fetching leagues for sport {sport}")

        page = session.get(
            f"{self._hostNav}/nav",
            params={
                "type": "sportslandingpage",
                "name": sport,
                "groupByDate": True,
                # This is the offset, in minutes, from UTC
                # Was set to 660 (AEDT, UTC+11:00), but change to 0 for UTC
                "timezone": 0,
            },
        )

        # NOTE: Soccer is split into regions. In this case, competitionList is
        # a dict of region name to a list of comps for that region.
        compList = page.json()

        if "competitionList" not in compList:
            self._log.error(f"Missing competitionList for sport {sport}")

            return

        compList = compList["competitionList"]

        # Get events/markets for each league
        return self._waitCollectResults(
            [
                gevent.spawn(self._fetchLeague, session, sport, leagueName)
                for leagueName in (
                    chain.from_iterable(compList.values())
                    if isinstance(compList, dict)
                    else compList
                )
            ]
        )

    def _fetchLeague(
        self, session: requests.Session, sport: str, league: str
    ) -> Iterator[BetfairScraperResult]:
        self._log.debug(f"Fetching competitions for league {league}")

        page = session.get(
            f"{self._hostNav}/nav",
            params={
                "type": "leaguelandingpage",
                "name": sport,
                "leagueName": league,
                "groupByDate": True,
                "timezone": 0,
            },
        )

        return self._handleLeaguePage(session, sport, league, page.json())

    def _handleLeaguePage(
        self,
        session: requests.Session,
        sportName: str,
        leagueName: str,
        leaguePage: dict,
    ) -> Iterator[BetfairScraperResult]:
        return self._waitCollectResults(
            [
                gevent.spawn(
                    self._fetchMarkets, session, sportName, leagueName, eventName, event
                )
                for eventName, event in chain.from_iterable(
                    events.items()
                    for events in leaguePage["featuredMarketData"].values()
                )
            ]
        )

    def _fetchMarkets(
        self,
        session: requests.Session,
        sportName: str,
        leagueName: str,
        eventName: str,
        event: list,
    ) -> Iterator[BetfairScraperResult]:
        self._log.debug(
            f"Retrieving odds: sport={sportName} league={leagueName}"
            f" event={eventName}"
        )

        # Need to divide markets into batches here to avoid getting a
        # 'TOO_MUCH_DATA' error from api.
        marketMetaMap = {market["marketId"]: market for market in event}
        results = []

        for marketIdBatch in batched((market["marketId"] for market in event), 5):
            page = session.get(
                f"{self._hostApi}/api/sports/exchange/readonly/v1/bymarket",
                params={
                    "currencyCode": "AUD",
                    "locale": "en",
                    "marketIds": ",".join(marketIdBatch),
                    "rollupLimit": 5,
                    "rollupModel": "STAKE",
                    "virtualise": True,
                    "types": ",".join(
                        [
                            "MARKET_STATE",
                            "MARKET_LICENCE",
                            "MARKET_RATES",
                            "MARKET_DESCRIPTION",
                            "EVENT",
                            "RUNNER_DESCRIPTION",
                            "RUNNER_STATE",
                            "RUNNER_METADATA",
                            "RUNNER_SP",
                            "RUNNER_EXCHANGE_PRICES_BEST",
                            "MARKET_LINE_RANGE_INFO",
                        ]
                    ),
                },
            )
            results.extend(
                self._handleMarkets(sportName, leagueName, marketMetaMap, page.json())
            )

        return results

    def _handleMarkets(
        self,
        sportName: str,
        leagueName: str,
        marketMetaMap: dict,
        market: dict,
    ):
        results = []

        # Handle API errors
        if "faultcode" in market:
            self._log.error(
                f"API {market['faultcode']} error {market['faultstring']}: {market['detail']}"
            )

            return results

        # Should only ever be 0 or 1 event type
        if len(market["eventTypes"]) == 0:
            return results

        assert len(market["eventTypes"]) == 1
        event = market["eventTypes"][0]

        # Can sometimes be > 1 event node...
        eventNode = event["eventNodes"][0]

        for eventNode in event["eventNodes"]:
            for marketNode in eventNode["marketNodes"]:
                results.append(
                    BetfairScraperResult(
                        sportName=sportName,
                        leagueName=leagueName,
                        marketMeta=marketMetaMap[marketNode["marketId"]],
                        marketNode=marketNode,
                    )
                )

        return results
