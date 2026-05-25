#!/usr/bin/env python3
"""
  test_dabble_parser.py
  =====================

  Description:           TODO
  Author:                Michael De Pasquale
  Creation Date:         2024-12-23
  Modification Date:     2024-12-23

"""

import json

import pytest

from ..dabble import DabbleParser
from scrapers.dabble import DabbleScraperResult


def test_smoke() -> None:
    """Smoke test"""

    with open("parsers/tests/data/dabble.json", "r") as f:
        results = json.load(f)

    parsedResults = DabbleParser().parse([DabbleScraperResult(**r) for r in results])

    # Just do minimal amount of checking here.
    # NOTE: shouldn't rely on keys being meaningful, may change and break this test
    comp = parsedResults.sports["Rugby Union"].competitions["England Premiership"]
    event = comp.events["Gloucester v Harlequins"]

    assert all(k in event.participants for k in ("Harlequins", "Gloucester"))
    assert "Match Winner (Draw No Bet)" in event.markets
