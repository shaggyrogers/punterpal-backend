#!/usr/bin/env python3
"""
  test_unibet_parser.py
  =====================

  Description:           TODO
  Author:                Michael De Pasquale
  Creation Date:         2024-12-23
  Modification Date:     2024-12-23

"""


import json

import pytest

from ..unibet import UnibetParser
from scrapers.unibet import UnibetScraperResult


def test_smoke() -> None:
    """Smoke test"""

    with open("parsers/tests/data/unibet.json", "r") as f:
        results = json.load(f)

    parsedResults = UnibetParser().parse([UnibetScraperResult(**r) for r in results])

    # Just do minimal amount of checking here.
    # NOTE: shouldn't rely on keys being meaningful, may change and break this test
    comp = parsedResults.sports["American Football"].competitions["NFL"]
    event = comp.events["Minnesota Vikings - Chicago Bears"]

    assert all(k in event.participants for k in ("Minnesota Vikings", "Chicago Bears"))
    assert "Match" in event.markets
