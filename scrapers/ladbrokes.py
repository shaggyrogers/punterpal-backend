#!/usr/bin/env python3
"""
  ladbrokes.py
  ============

  Description:           TODO
  Author:                Michael De Pasquale
  Creation Date:         2024-11-21
  Modification Date:     2025-09-23

"""

from typing import Iterable
import re

import gevent
from pydantic import BaseModel
import requests

from .base_scraper import BaseScraper


class LadbrokesScraperResult(BaseModel):
    category: dict
    competition: dict
    event: dict
    market: dict

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            + ", ".join(
                (
                    f"sport='{self.category['name']}'",
                    f"league='{self.competition['name']}'",
                    f"event='{self.event['name']}'",
                    f"market='{self.market['name']}'",
                )
            )
            + ")"
        )


class LadbrokesScraper(BaseScraper):
    _slugStripExp = re.compile("--+")

    def __init__(self) -> None:
        self._host = "https://api.ladbrokes.com.au/gql/router"
        super().__init__(
            headers={
                "content-type": "application/json",
                "graphql-client-name": "rn-android",
                "graphql-client-version": "9.25.0",
                "graphql-client-build": "963994",
                "User-Agent": "okhttp/5.1.0",
                # requests otherwise sends gzip/deflate, different from the normal client
                "Accept-Encoding": "gzip",
                "FromKotlin": "EntainOkHttpClientFactoryStatic",
            }
        )

    @classmethod
    def _makeSlug(cls, name: str) -> str:
        #  "TT Cup - Men - Singles" -> tt-cup-men-singles
        return cls._slugStripExp.sub("-", name.lower().replace(" ", "-"))

    def _fetch(self, session: requests.Session) -> Iterable[LadbrokesScraperResult]:
        # FIXME: Maybe only get OPEN events, probably dont need LIVE
        self._log.debug("Fetching sport categories")

        page = session.post(
            self._host,
            json={
                "extensions": {
                    "persistedQuery": {
                        "sha256Hash": "922a0f37ace11aebaf858ea742d79bffc8f98a1d7de7b3ba828906488f39b4d2",
                        "version": 1,
                    }
                },
                "operationName": "SportingCategories",
            },
        )

        return self._waitCollectResults(
            [
                gevent.spawn(self._fetchCategory, session, cat)
                for cat in page.json()["data"]["categories"]
            ]
        )

    def _fetchCategory(
        self, session: requests.Session, category: dict
    ) -> Iterable[LadbrokesScraperResult]:
        """Get leagues for category."""
        self._log.debug(f"Getting leagues sport={category['name']}")
        page = session.post(
            self._host,
            json={
                "extensions": {
                    "persistedQuery": {
                        "sha256Hash": "145602a7c1144946947df14361323d973dcc50724b4477787b564d4f6561e17e",
                        "version": 1,
                    }
                },
                "operationName": "SportingCompetitionsList",
                "variables": {
                    "category": category["category"],
                    "statuses": ["LIVE", "OPEN"],
                },
            },
        )

        return self._waitCollectResults(
            [
                gevent.spawn(self._fetchLeague, session, category, league)
                for league in page.json()["data"]["leagues"]["nodes"]
            ]
        )

    def _fetchLeague(
        self, session: requests.Session, category: dict, league: dict
    ) -> Iterable[LadbrokesScraperResult]:
        self._log.debug(
            f"Getting events sport='{category['name']}' league='{league["name"]}'"
            f" region='{league['region']}'"
        )

        # TODO: Ignore more unsupported stuff where possible
        if league["name"].endswith("Multi Builder"):
            return

        page = session.post(
            self._host,
            json={
                "extensions": {
                    "persistedQuery": {
                        "sha256Hash": "5037e1f121cb206760ec025fb28a5db962f9e9cb6809255d0876d05297e08941",
                        "version": 1,
                    }
                },
                "operationName": "SportingCompetitionEvents",
                "variables": {
                    "anyTeamVsAnyTeamEnabled": False,
                    "category": category["category"],
                    "competitionSlug": self._makeSlug(league["name"]),
                    "regionSlug": (
                        "" if not league["region"] else league["region"]["slug"]
                    ),
                    "showIndicators": True,
                    "statuses": ["LIVE", "OPEN"],
                },
            },
        )

        # Many more markets are available, for now just get the main ones
        events = page.json()

        # Sometimes can be null
        if not events["data"]["competition"]:
            return

        for event in events["data"]["competition"]["events"]["nodes"]:
            for market in event["markets"]["nodes"]:
                yield LadbrokesScraperResult(
                    category=category,
                    competition=events["data"]["competition"],
                    event=event,
                    market=market,
                )
