#!/usr/bin/env python3
"""
  sportsbet.py
  ============

  Description:           Sportsbet scraper.
  Author:                Michael De Pasquale
  Creation Date:         2024-04-23
  Modification Date:     2025-04-19

"""

from collections.abc import Iterable
from itertools import chain
import re
from typing import Union
import urllib

import gevent
import requests
from pydantic import BaseModel

from .base_scraper import BaseScraper

# NOTE:
# * Occasionally get 404 on some requests.
# * Can get 403 on any request if rate is too high.


class SportsbetScraperResult(BaseModel):
    """Result node for sportsbet scraper."""

    # Sport
    page: dict

    # Match
    event: dict

    marketGroup: dict
    market: dict

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            + ", ".join(
                (
                    f"sport='{self.page['name']}'",
                    f"league='{self.event['competitionName']}'",
                    f"event='{self.event['name']}'",
                    f"market='{self.market['name']}'",
                )
            )
            + ")"
        )


class SportsbetScraper(BaseScraper):

    def __init__(self) -> None:
        super().__init__(
            # TODO: Should probably check to make sure headers are OK
            headers={"user-agent": "okhttp/4.10.0"},
            # Drop rate from default 20 - slightly too high? sometimes get 403
            rate=19,
        )

        self._hostGWAPI = "gwapi.sportsbet.com.au"
        self._hostDCMS = "dcms.sportsbet.com.au"
        self._classIdExp = re.compile(".*classIds=([^&]+).*")

    def _fetch(self, session: requests.Session) -> Iterable[SportsbetScraperResult]:
        page = session.get(
            f"https://{self._hostDCMS}/app/page",
            params={
                "pagePath": "sports-&-novelties",
                "loggedIn": "false",
                "region": "UNK",
                "density": "Unknown",
            },
        )

        return self._waitCollectResults(
            [
                gevent.spawn(self._fetchSport, session, menu)
                for menu in page.json()["sections"][0]["cards"][0]["menu"]
            ]
        )

    def _fetchSport(
        self, session: requests.Session, menu: dict
    ) -> Iterable[SportsbetScraperResult]:
        classID = int(self._classIdExp.match(menu["link"]["url"]).groups(1)[0])
        self._log.debug(
            f"Fetching sport: id={menu['id']} title={menu['title']} classID={classID}"
        )

        resp = session.get(
            f"https://{self._hostDCMS}/app/page",
            params={
                "classId": classID,
                "loggedIn": False,
                "region": "UNK",
                "density": "Unknown",
            },
        )

        return self._fetchAllCompetitions(session, resp.json(), classID) or []

    def _fetchAllCompetitions(
        self, session: requests.Session, sportPage: dict, classID: int
    ) -> dict:
        """Get 'all competitions' section."""
        allComps = list(
            filter(
                lambda s: s["path"].endswith("/all-competitions"), sportPage["sections"]
            )
        )
        assert len(allComps) == 1

        allComps = allComps[0]

        # build URL from datasource string, get list of all competitions
        resp = session.get(
            urllib.parse.urljoin(
                f"https://{self._hostGWAPI}/sportsbook-sports/",
                allComps["cards"][0]["datasources"][0].format(classId=classID),
            ),
        )

        # Check response
        if resp.status_code != requests.codes.OK:
            self._log.error(
                f"Failed to retrieve 'all competitions' for sport: {sportPage['name']}"
                f" code={resp.status_code} text={resp.text}"
            )

            return

        competitions = resp.json()

        if not competitions:
            self._log.error(f"No competitions found for {sportPage['name']}")

            return

        # Check for sport with competitions divided into regions, handle separately
        if "id" not in competitions[0]:
            self._log.debug(
                f"Handling regional competitions for sport {sportPage['name']}"
            )

            return (
                self._fetchRegionalCompetitions(session, sportPage, competitions) or []
            )

        # Get list of events for each competition
        return self._waitCollectResults(
            [
                gevent.spawn(self._fetchCompetition, session, comp, sportPage, False)
                for comp in competitions
            ]
        )

    def _fetchRegionalCompetitions(
        self,
        session: requests.Session,
        sportPage: dict,
        regions: Iterable[dict],
    ) -> dict:
        results = []

        for region in regions:
            self._log.debug(
                f"Fetching {sportPage['name']} competitions for region {region['name']}"
            )
            resp = session.get(
                urllib.parse.urljoin(
                    f"https://{self._hostGWAPI}/sportsbook-sports/", region["httpLink"]
                ),
            )

            regionCompGroups = resp.json()

            # Get list of events for each competition
            results.extend(
                self._waitCollectResults(
                    [
                        gevent.spawn(
                            self._fetchCompetition, session, comp, sportPage, True
                        )
                        for comp in chain.from_iterable(
                            map(lambda cg: cg["competitions"], regionCompGroups)
                        )
                    ]
                )
            )

        return results

    def _fetchCompetition(
        self,
        session: requests.Session,
        comp: dict,
        sportPage: dict,
        isEventGrouped: bool,
    ) -> Iterable[SportsbetScraperResult]:
        logInfo = " ".join(
            (
                (
                    f"className={comp['className']}"
                    if "classId" in comp
                    else f"competitionName={comp['competitionName']}"
                ),
                f"name={comp['name']}",
                f"id={comp['id']}",
            )
        )

        # HACK: Improve performance by skipping futures markets
        if comp["name"].endswith(" Futures"):
            self._log.debug(f"Skipping futures market: {logInfo}")

            return None

        self._log.debug(f"Fetching competition: {logInfo}")
        resp = session.get(
            urllib.parse.urljoin(
                f"https://{self._hostGWAPI}/sportsbook-sports/", comp["httpLink"]
            ),
        )

        # Check response
        if resp.status_code != requests.codes.OK:
            self._log.error(
                f"Failed to retrieve events for competition: {logInfo}"
                f" code={resp.status_code} text={resp.text}"
            )

            return None

        compData = resp.json()

        # Get data for each event
        return self._waitCollectResults(
            [
                gevent.spawn(self._fetchEvent, session, compEvent, sportPage)
                for compEvent in (
                    chain.from_iterable(map(lambda eg: eg["events"], compData))
                    if isEventGrouped
                    else compData
                )
            ]
        )

    def _fetchEvent(
        self, session: requests.Session, compEvent: dict, sportPage: dict
    ) -> Union[None, Iterable[SportsbetScraperResult]]:
        self._log.debug(
            f"Fetching event: id={compEvent['id']} name={compEvent['name']}"
            # f" className={comp['className']} competitionName={comp['name']}"
        )
        resp = session.get(
            urllib.parse.urljoin(
                f"https://{self._hostGWAPI}/sportsbook-sports/",
                compEvent["httpLink"],
            ),
        )

        # Check response
        if resp.status_code != requests.codes.OK:
            self._log.error(
                f"Failed to retrieve event:"
                f"id={compEvent['id']} name={compEvent['name']} "
                f" code={resp.status_code} text={resp.text}"
            )

            return None

        return self._fetchEventMarkets(
            session,
            page=sportPage,
            event=resp.json(),
        )

    def _fetchEventMarkets(
        self, session: requests.Session, page: dict, event: dict
    ) -> dict:
        if event["bettingStatus"] == "OFF":
            return

        results = []

        for marketGroup in event["marketGrouping"]:
            # Allow 'Other Markets' for these; winner markets are grouped under
            # 'Other Markets' for some less popular sports
            allowOther = page["name"] in (
                "Handball",
                "Ice Hockey - Other",
                "Ice Hockey - US",
                "Table Tennis",
                "UFC - MMA",
                "Volleyball",
            )

            # HACK: Improve performance by skipping market groups we don't support
            if marketGroup["name"] not in (
                "Top Markets",
                "Win Markets",
                "Other Markets" if allowOther else "__NO_OTHER_ALLOWED__",
            ):
                self._log.debug(
                    f"Skipping unsupported marketGroup: name={marketGroup['name']}"
                )

                continue

            self._log.debug(f"Fetching marketGroup: name={marketGroup['name']}")

            resp = session.get(
                urllib.parse.urljoin(
                    f"https://{self._hostGWAPI}/sportsbook-sports/",
                    marketGroup["httpLink"],
                ),
            )

            # Check response
            if resp.status_code != requests.codes.OK:
                self._log.error(
                    f"Failed to retrieve market name={marketGroup['name']}"
                    f" code={resp.status_code} text={resp.text}"
                )

                continue

            markets = resp.json()

            for market in markets:
                results.append(
                    SportsbetScraperResult(
                        page=page,
                        event=event,
                        marketGroup=marketGroup,
                        market=market,
                    )
                )

        return results
