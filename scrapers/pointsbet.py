#!/usr/bin/env python3
"""
  pointsbet.py
  ============

  Description:           TODO
  Author:                Michael De Pasquale
  Creation Date:         2025-03-19
  Modification Date:     2025-04-04

"""

from itertools import chain
from typing import Iterable

import gevent
from pydantic import BaseModel
import requests

from .base_scraper import BaseScraper


class PointsbetScraperResult(BaseModel):
    event: dict
    market: dict

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            + ", ".join(
                (
                    f"sport='{self.event['sportName']}'",
                    f"league='{self.event['competitionName']}'",
                    f"event='{self.event['name']}'",
                    f"market='{self.market['name']}'",
                )
            )
            + ")"
        )


class PointsbetScraper(BaseScraper):
    def __init__(self) -> None:
        self._host = "https://api.au.pointsbet.com"
        super().__init__(
            # stealth mode
            headers={
                "sec-ch-ua-platform": '"Android"',
                "sec-ch-ua": '"Android WebView";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                "sec-ch-ua-mobile": "?1",
                # First part of request ID is constant, second part changes. Same with traceparent
                # Not required
                # "request-id": "|47fe714ab1ec4be680098bf632f048e0.3c019a1b0cc14bac",
                # "traceparent": "00-47fe714ab1ec4be680098bf632f048e0-3c019a1b0cc14bac-01",
                "request-context": "appId=cid-v1:357718fd-f996-4d61-b298-abc0c05bc6c4",
                # pylint: disable=line-too-long
                "user-agent": "Mozilla/5.0 (Linux; Android 12; sdk_gphone64_x86_64 Build/SE1B.240122.005; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/131.0.6778.41 Mobile Safari/537.36 PointsBetApp/android/3.46.0/544571",
                "accept": "application/json, text/plain, */*",
                "x-requested-with": "com.pointsbet.app",
                "sec-fetch-site": "cross-site",
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
                "accept-encoding": "gzip, deflate, br, zstd",
                "accept-language": "en-US,en;q=0.9",
                "priority": "u=1, i",
            }
        )

    def _fetch(self, session: requests.Session) -> Iterable[PointsbetScraperResult]:
        self._log.debug("Getting sports")
        req = session.get(f"{self._host}/api/v2/sports/list/02May2018")

        return self._waitCollectResults(
            [
                gevent.spawn(self._fetchSport, session, sport)
                for sport in req.json()["sports"]
            ]
        )

    def _fetchSport(
        self, session: requests.Session, sport: dict
    ) -> Iterable[PointsbetScraperResult]:
        req = session.get(f"{self._host}/api/v2/sports/{sport['key']}/competitions")

        return self._waitCollectResults(
            [
                gevent.spawn(self._fetchEvents, session, comp)
                for comp in chain.from_iterable(
                    l["competitions"] for l in req.json()["locales"]
                )
            ]
        )

    def _fetchEvents(
        self, session: requests.Session, competition: dict
    ) -> Iterable[PointsbetScraperResult]:
        curPage = 1

        while curPage is not None:
            req = session.get(
                f"{self._host}/api/mes/v3/events/featured/competition/{competition['key']}",
                params={"page": curPage},
            )

            events = req.json()
            curPage = events["nextPage"]

            for event in events["events"]:
                yield from self._processMarkets(event, event["markets"])

                yield from self._processMarkets(event, event["specialFixedOddsMarkets"])

    def _processMarkets(
        self, event: dict, markets: list
    ) -> Iterable[PointsbetScraperResult]:
        for market in markets:
            yield PointsbetScraperResult(event=event, market=market)
