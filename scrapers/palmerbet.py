#!/usr/bin/env python3
"""
  palmerbet.py
  ============

  Description:           Yoink data from palmerbet
  Author:                Michael De Pasquale
  Creation Date:         2025-03-22
  Modification Date:     2026-05-25

"""

from itertools import chain
import re
from typing import Iterable
import urllib

import gevent
from pydantic import BaseModel
import requests

from .base_scraper import BaseScraper
from .network.palmerbet_adapter import PalmerbetAdapter


class PalmerbetScraperResult(BaseModel):
    sport: dict
    league: dict
    match: dict

    def __str__(self) -> str:
        return repr(self)

    def __repr__(self) -> str:
        eventTitle = " vs ".join(
            (
                self.match["homeTeam"]["title"],
                self.match["awayTeam"]["title"],
            )
        )
        marketCount = len(self.match.get("additionalMarkets", [])) + (
            1 if "win" in self.match["homeTeam"] else 0
        )

        return (
            f"{self.__class__.__name__}("
            + ", ".join(
                (
                    f"sport='{self.sport['title']}'",
                    f"league='{self.league['title']}'",
                    f"event='{eventTitle}'",
                    f"marketCount={marketCount}",
                )
            )
            + ")"
        )


class PalmerbetScraper(BaseScraper):
    _sportTypeExp = re.compile(r"sportType=(?P<sportType>\w+)")

    def __init__(self) -> None:
        self._host = "fixture.palmerbet.online"
        self._uri = f"https://{self._host}"
        self._appVersion = "6.35.214627"
        super().__init__(
            headers={
                "user-agent": "Dart/3.8 (dart:io)",
                "accept": "application/json",
                "accept-encoding": "gzip",
                "host": self._host,
            },
            # Drop rate from default, otherwise we will get 429 / Too Many Requests
            # If this happens, server applies ban for 24 hours (see 'Retry-After')
            rate=10,
        )

    def _fetch(self, session: requests.Session) -> Iterable[PalmerbetScraperResult]:
        # Remove Connection header
        if "Connection" in session.headers:
            del session.headers["Connection"]

        # Install our adapter
        session.adapters.pop("https://", None)
        session.adapters.pop("http://", None)
        session.mount("https://", PalmerbetAdapter())

        # FIXME: We now trigger cloudflare bot detection...
        # seems to be due to differences in how the TLS connection is established, see RE notes...

        req = session.get(
            # Root node containing all sports
            f"{self._uri}/fixtures/sports/845c3c3b-da2c-4c46-9b6c-2525e9e53f75",
            params={
                "sportType": "Unknown",
                "channel": "mobile",
                "app-version": self._appVersion,
            },
        )

        sports = req.json()
        assert sports["sportItem"]

        return self._waitCollectResults(
            [
                gevent.spawn(self._fetchSport, session, sport)
                for sport in sports["sportItem"]["subItems"]
            ]
        )

    def _splitHrefSportType(self, href: str) -> tuple[str]:
        """Takes a path with sport type included as a query string,
        returns a tuple of form (path, sportType)
        """
        # Extract sportType
        sportURI = urllib.parse.urlparse(href)
        sportType = self._sportTypeExp.match(sportURI.query).groups("sportType")[0]
        assert sportType and sportType != "Unknown"

        return sportURI.path, sportType

    def _fetchSport(
        self, session: requests.Session, sport: dict
    ) -> Iterable[PalmerbetScraperResult]:
        # Should only be one link for each sport, method should be GET
        assert len(sport["_links"]) == 1
        assert sport["_links"][0]["method"].lower() == "get"

        path, sportType = self._splitHrefSportType(sport["_links"][0]["href"])

        # Minor optimisation: skip stuff we don't support
        if sportType.lower() in (
            "novelties",
            "entertainment",
            "motorracing",
            "politics",
        ):
            self._log.debug(f"Ignoring unsupported sportType {sportType}")

            return

        req = session.get(
            f"{self._uri}{path}",
            params={
                "sportType": sportType,
                "channel": "mobile",
                "app-version": self._appVersion,
            },
        )

        return self._waitCollectResults(
            [
                gevent.spawn(self._fetchLeague, session, sport, league)
                for league in req.json()["sportItem"]["subItems"]
            ]
        )

    def _fetchLeague(
        self, session: requests.Session, sport: dict, league: dict
    ) -> Iterable[PalmerbetScraperResult]:
        self._log.debug(f"Getting {league['sportType']} league {league['title']}")

        path, sportType = self._splitHrefSportType(sport["_links"][0]["href"])
        req = session.get(
            f"{self._uri}{path}",
            params={
                "sportType": sportType,
                "channel": "mobile",
                "app-version": self._appVersion,
            },
        )
        leaguePage = req.json()

        return self._fetchMatches(session, sport, league, leaguePage)

    def _fetchMatches(
        self, session: requests.Session, sport: dict, league: dict, leaguePage: dict
    ) -> Iterable[PalmerbetScraperResult]:
        # Follow the 'matches' link
        matchesLinks = [
            l for l in leaguePage["sportItem"]["_links"] if l["rel"] == "matches"
        ]

        assert len(matchesLinks) == 1
        path, sportType = self._splitHrefSportType(matchesLinks[0]["href"])
        req = session.get(
            f"{self._uri}{path}",
            params={
                "sportType": sportType,
                "channel": "mobile",
                "app-version": self._appVersion,
            },
        )

        for match in req.json()["matches"]:
            yield PalmerbetScraperResult(sport=sport, league=league, match=match)
