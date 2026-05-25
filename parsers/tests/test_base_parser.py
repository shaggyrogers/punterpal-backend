#!/usr/bin/env python3
"""
  test_base_parser.py
  ===================

  Description:           TODO
  Author:                Michael De Pasquale
  Creation Date:         2024-12-17
  Modification Date:     2025-04-07

"""

from datetime import timezone
import math

import pytest

from ..base_parser import BaseParser


def test_parseISO8601() -> None:
    # UTC 'Z' suffix
    dt = BaseParser.parseISO8601("2019-02-17T08:12:02Z")
    assert dt.tzinfo == timezone.utc
    assert (dt.day, dt.month, dt.year) == (17, 2, 2019)
    assert (dt.hour, dt.minute, dt.second) == (8, 12, 2)

    # UTC offset
    dt = BaseParser.parseISO8601("1945-09-02T02:13:37+01:00")
    assert dt.utcoffset().seconds == 3600
    assert (dt.day, dt.month, dt.year) == (2, 9, 1945)
    assert (dt.hour, dt.minute, dt.second) == (2, 13, 37)

    # Microseconds
    assert BaseParser.parseISO8601("2025-03-20T08:30:00.000Z").utcoffset().seconds == 0
    assert BaseParser.parseISO8601("2025-04-07T13:30:00.0000000Z")

    # Timestamp missing timezone info should fail
    with pytest.raises(ValueError):
        BaseParser.parseISO8601("1943-04-19T01:23:45")


def test_parseTimestamp() -> None:
    dt = BaseParser.parseTimestamp(1550391122)
    assert dt.tzinfo == timezone.utc
    assert (dt.day, dt.month, dt.year) == (17, 2, 2019)
    assert (dt.hour, dt.minute, dt.second) == (8, 12, 2)


@pytest.mark.parametrize(
    "odds,expected",
    [
        (-500, 1.2),
        ("-110.0", 1.91),
        ("100", 2),
        (300, 4),
    ],
)
def test_americanOddsToDecimal(odds: float, expected: float) -> None:
    assert math.isclose(BaseParser.americanOddsToDecimal(odds), expected, rel_tol=0.001)


@pytest.mark.parametrize(
    "num,denom,expected",
    [
        (1, 5, 1.2),
        (1, 1, 2),
        (5, 4, 2.25),
        (7, 1, 8),
    ],
)
def test_fractionalOddsToDecimal(num: float, denom: float, expected: float) -> None:
    assert math.isclose(
        BaseParser.fractionalOddsToDecimal(num, denom), expected, rel_tol=0.001
    )
