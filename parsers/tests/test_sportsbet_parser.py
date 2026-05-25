#!/usr/bin/env python3
"""
  test_sportsbet_parser.py
  ========================

  Description:           TODO
  Author:                Michael De Pasquale
  Creation Date:         2024-12-23
  Modification Date:     2024-12-23

"""

import json

import pytest

from ..sportsbet import SportsbetParser
from scrapers.sportsbet import SportsbetScraperResult


def test_smoke() -> None:
    """Smoke test"""

    with open("parsers/tests/data/sportsbet.json", "r") as f:
        results = json.load(f)

    parsedResults = SportsbetParser().parse(
        [SportsbetScraperResult(**r) for r in results]
    )

    # Just do minimal amount of checking here.
    # NOTE: shouldn't rely on keys being meaningful, may change and break this test
    comp = parsedResults.sports["American Football"].competitions["NFL"]
    event = comp.events["Chicago Bears At Minnesota Vikings"]

    assert all(k in event.participants for k in ("Minnesota Vikings", "Chicago Bears"))
    assert "Match Betting" in event.markets
