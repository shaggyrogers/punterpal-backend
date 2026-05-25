#!/usr/bin/env python3
"""
  base_scraper.py
  ===============

  Description:           Shared functionality for scrapers
  Author:                Michael De Pasquale
  Creation Date:         2024-12-11
  Modification Date:     2025-10-25

"""

import logging
import traceback
from typing import Iterable

import gevent
import requests

from .network.session import RateLimitSession


class BaseScraper:

    def __init__(
        self,
        headers: dict = None,
        logLevel: str = "INFO",
        rate: int = 20,
        timeout: float = 30,
    ) -> None:
        """Initialise.

        Parameters
        ----------
        headers: dict, optional
          HTTP headers to send

        logLevel: str, default "INFO"
          Logging verbosity level.

        rate: int, default 20
          The average request rate, in requests per second.

        timeout: float, default 30
          Timeout for requests, in seconds.
        """
        self._log = logging.getLogger(
            self.__class__.__module__ + "." + self.__class__.__qualname__
        )
        self._log.setLevel(logLevel)

        self._headers = headers
        self._timeout = timeout
        self._rate = rate

    def fetch(self) -> Iterable:
        """Retrieve all available market data."""
        with RateLimitSession(
            sleepFn=gevent.sleep,
            capacity=self._rate,
            refillTime=1,
            timeout=self._timeout,
        ) as session:
            # Set headers
            session.headers.update(self._headers)

            # Uncomment this block to use mitmproxy.
            # session.proxies.update(
            #     {
            #         "http": "http://localhost:8080",
            #         "https": "http://localhost:8080",
            #     }
            # )
            # session.verify = False

            # Get everything
            return self._fetch(session)

    def _fetch(self, session: requests.Session) -> object:
        raise NotImplementedError("_fetch() must be implemented!")

    def _greenletOnException(self, greenlet: gevent.Greenlet) -> None:
        try:
            greenlet.get()

        except Exception as ex:
            self._log.exception("Exception in greenlet")

    def _waitCollectResults(self, greenlets: Iterable[gevent.Greenlet]) -> list:
        """Wait for greenlets and return a list of results.
        Expects greenlets to return an Iterable or None.
        """
        results = []

        for greenlet in greenlets:
            greenlet.link_exception(self._greenletOnException)

        for greenlet in filter(
            lambda g: g.successful and g.value, gevent.iwait(greenlets)
        ):
            results.extend(greenlet.value)

        return results
