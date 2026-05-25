#!/usr/bin/env python3
"""
  dabble.py
  =========

  Description:           TODO
  Author:                Michael De Pasquale
  Creation Date:         2024-12-11
  Modification Date:     2025-03-17

"""

import requests
from pydantic import BaseModel

from .base_scraper import BaseScraper


class DabbleScraperResult(BaseModel):
    sport: dict
    league: dict
    event: dict


class DabbleScraper(BaseScraper):
    def __init__(self) -> None:
        super().__init__(
            headers={
                "user-agent": "okhttp/4.12.0",
                "accept": "application/json",
                "authorization": "",
            },
        )
        self._hostApi = "https://api.dabble.com.au"

    def _fetch(self, session: requests.Session) -> object:
        self._log.debug("Fetching sports")

        # Get list of sports
        page = session.get(f"{self._hostApi}/sports")
        pageData = page.json()
        assert pageData["status"] == "success"

        for sport in pageData["data"]:
            if sport["isRacing"] or sport["isHidden"]:
                self._log.warning(f"Skipping sport {sport['name']} (racing or hidden)")

            if sport["name"] == "Daily Dabbles":
                self._log.debug(f"Skipping daily dabbles")
                continue

            # Get list of competitions/leagues
            self._log.debug(f"Fetching leagues for sport {sport['name']}")

            page = session.get(
                f"{self._hostApi}/competitions/active/",
                params={
                    "sportId": sport["id"],
                },
            )
            pageData = page.json()
            assert pageData["status"] == "success"

            for league in pageData["data"]["activeCompetitions"]:
                # Get fixtures
                self._log.debug(f"Getting events/markets for league {league['name']}")

                page = session.get(
                    f"{self._hostApi}/competitions/{league['id']}/sport-fixtures",
                )
                pageData = page.json()

                for event in pageData["data"]:
                    yield DabbleScraperResult(sport=sport, league=league, event=event)
