#!/usr/bin/env python3
"""
  unibet.py
  =========

  Description:           TODO
  Author:                Michael De Pasquale
  Creation Date:         2024-12-04
  Modification Date:     2025-03-17

"""

import requests
from pydantic import BaseModel

from .base_scraper import BaseScraper


class UnibetScraperResult(BaseModel):
    sport: dict
    event: dict
    betOffer: dict


class UnibetScraper(BaseScraper):

    def __init__(self) -> None:
        super().__init__(headers={"user-agent": "okhttp/4.12.0"})
        self._hostApi = "api.unibet.com.au"
        self._hostOfferApi = "oc-offering-api.kambicdn.com"

    def _fetch(self, session: requests.Session) -> object:
        # Get all sports
        self._log.debug("Retrieving list of all sports")

        page = session.get(
            f"https://{self._hostApi}/sportsbook-feeds/views/sports/a-z",
            params={
                "brand": "unibet",
                "channel": "12",
                "clientId": "unibetpro_mobilephone-android_5.7.0",
                "jurisdiction": "NT",  # northern territory?
                "locale": "en_AU",
                "maxPopularItems": 6,
            },
        )

        pageData = page.json()
        azWidget = None

        # Find "A-Z Widget"
        for section in pageData["layout"]["sections"]:
            for widget in section["widgets"]:
                if widget["name"] == "A-Z Widget":
                    azWidget = widget

                    break

        # Get events for each sport
        for sport in azWidget["sports"]:
            self._log.debug(f"Fetching sport name={sport['name']}")

            page = session.get(
                f"https://{self._hostOfferApi}/offering/v2018/ubau/listView/{sport['termKey'].lower()}.json",
                params={
                    "lang": "en_AU",
                    "market": "AU",
                    "client_id": 2,
                    "channel_id": 3,
                    # Not sure what this is, not required.
                    # "ncid": 1733303210725,
                    "useCombined": True,
                },
            )

            pageData = page.json()

            for event in pageData["events"]:
                yield from self._handleEvent(sport, event)

    def _handleEvent(self, sport: dict, event: dict) -> object:
        eventData = event["event"]
        self._log.debug(
            f"Found event {eventData['name']} with {len(event['betOffers'])} markets"
        )

        for betOffer in event["betOffers"]:
            yield UnibetScraperResult(
                sport=sport,
                event=eventData,
                betOffer=betOffer,
            )
