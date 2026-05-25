#!/usr/bin/env python3
"""
  test_scoring.py
  ===============

  Description:           Tests for matcher.scoring
  Author:                Michael De Pasquale
  Creation Date:         2025-02-05
  Modification Date:     2025-03-12

"""

from datetime import datetime, timedelta

import pytest

from matcher.scoring import scorePersonalNames, scoreLeagueNames, scoreTimeDelta


@pytest.mark.parametrize(
    "testInput,equivalent",
    [
        ("Winger, Jeff", "Jeff Winger"),
        ("Simpson, Homer J.", "Homer J. Simpson"),
        ("Soprano, Tony", "Tony Soprano"),
        ("Cheung, Ki Wai", "Ki Wai Cheung"),
        ("sal marino", "Sal Marino"),
    ],
)
def test_scorePersonalNames(testInput: str, equivalent: str) -> None:
    assert scorePersonalNames(testInput, equivalent) > 0.99


@pytest.mark.parametrize(
    "testInput,equivalent",
    [
        ("Finnish Korisliiga", "Korisliiga"),
        ("NeW ZeAlAnD doesn't EXIST", "DOESN'T exist"),
        ("JAPAN J-LEAGUE", "j-league"),
        ("Puerto Rican BSN", "BSN"),
        ("vietnamese", ""),
    ],
)
def test_scoreLeagueNames(testInput: str, equivalent: str) -> None:
    assert scoreLeagueNames(testInput, equivalent) > 0.99


def test_scoreTimeDelta() -> None:
    now = datetime.now()
    assert scoreTimeDelta(now, now, 1) == 1
    assert scoreTimeDelta(now, now + timedelta(minutes=1), 1) == 0
    assert scoreTimeDelta(now, now + timedelta(microseconds=1), 1) > 0.95
