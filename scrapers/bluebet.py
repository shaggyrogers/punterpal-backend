#!/usr/bin/env python3
"""
  bluebet.py
  ==========

  Description:           Scrape from Bluebet/Betr
  Author:                Michael De Pasquale
  Creation Date:         2025-04-04
  Modification Date:     2025-08-15

"""
from typing import Generator, Iterable

import gevent
from pydantic import BaseModel
import requests

from .base_scraper import BaseScraper


# Harvested from memory dump
CATEGORIES = [
    # Unsupported
    # {"Id": 1, "Ico": "horse_profile"},
    # {"Id": 2, "Ico": "harness_profile"},
    # {"Id": 3, "Ico": "greyhound_profile"},
    # {"Id": 113, "Ico": "entertainment"},
    # {"Id": 114, "Ico": "cycling"},
    # {"Id": 117, "Ico": "motor-sport"},
    # {"Id": 120, "Ico": "politics"},
    # {"Id": 200, "Ico": "promotions"},
    # Currently empty? Maybe try enable in future
    # {"Id": 119, "Ico": "volleyball"},
    # {"Id": 201, "Ico": "mixed-martial-arts"},
    # {"Id": 202, "Ico": "netball"},
    # {"Id": 203, "Ico": "surfing"},
    {"Id": 100, "Ico": "soccer"},
    {"Id": 101, "Ico": "australian-rules"},
    {"Id": 102, "Ico": "rugby-league"},
    {"Id": 103, "Ico": "baseball"},
    {"Id": 104, "Ico": "tennis"},
    {"Id": 105, "Ico": "rugby-union"},
    {"Id": 106, "Ico": "golf"},
    {"Id": 107, "Ico": "basketball"},
    {"Id": 108, "Ico": "american-football"},
    {"Id": 109, "Ico": "cricket"},
    {"Id": 110, "Ico": "boxing"},
    {"Id": 111, "Ico": "ice-hockey"},
    {"Id": 112, "Ico": "handball"},
    {"Id": 115, "Ico": "darts"},
    {"Id": 116, "Ico": "snooker"},
]


class BluebetScraperResult(BaseModel):
    # "Soccer" / 100
    eventType: str = None
    eventTypeId: int = None

    # "England" / 19
    masterCategory: str = None
    masterCategoryId: int = None

    # "English Premier League" / 36715
    category: str = None
    categoryId: int = None

    # Event data
    # Outcomes for one or more markets are grouped under event.Markets
    event: dict

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            + ", ".join(
                (
                    f"sport='{self.eventType}'",
                    f"league='{self.category}'",
                    f"event='{self.event['MasterEventName']}'",
                )
            )
            + ")"
        )


class BluebetScraper(BaseScraper):
    def __init__(self) -> None:
        self._host = "https://android-api.bluebet.com.au"
        super().__init__(
            headers={
                # TODO: UPDATE VERSION
                "user-agent": "BlueBet/3.3.0 34284 (Android/sdk_gphone64_x86_64)",
                "content-type": "application/json",
                "accept": "application/json",
                "accept-encoding": "gzip",
            }
        )

    def _fetch(self, session: requests.Session) -> Iterable[BluebetScraperResult]:
        return self._waitCollectResults(
            [gevent.spawn(self._fetchSport, session, cat) for cat in CATEGORIES]
        )

    def _fetchSport(
        self, session: requests.Session, category: dict
    ) -> Iterable[BluebetScraperResult]:
        req = session.get(
            f"{self._host}/MasterCategory",
            params={
                "eventTypeId": category["Id"],
                "withLevelledMarkets": True,
            },
        )

        sport = req.json()

        # Can occur if there's no markets for a sport.
        if "EventTypeDesc" not in sport:
            self._log.warning(f"Sport is missing EventTypeDesc! category: {category}")

            return

        # Separate into events
        for masterCat in sport["MasterCategories"]:
            for category in masterCat["Categories"]:
                for event in category["MasterEvents"]:
                    yield BluebetScraperResult(
                        # x/xDesc/xName.. why
                        eventType=sport["EventTypeDesc"],
                        eventTypeId=sport["EventTypeId"],
                        masterCategory=masterCat["MasterCategory"],
                        masterCategoryId=masterCat["MasterCategoryId"],
                        category=category["CategoryName"],
                        categoryId=category["CategoryId"],
                        event=event,
                    )
