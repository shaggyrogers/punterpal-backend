#!/usr/bin/env python3
"""
  test_ladbrokes.py
  =================

  Description:           Unit tests for Ladbrokes scraper
  Author:                Michael De Pasquale
  Creation Date:         2025-03-17
  Modification Date:     2025-03-17

"""

import pytest

from ..ladbrokes import LadbrokesScraper


@pytest.mark.parametrize(
    "testInput,expected",
    [
        ("AFL", "afl"),
        ("TT Cup - Men - Singles", "tt-cup-men-singles"),
    ],
)
def test__makeSlug(testInput: str, expected: str) -> None:
    # pylint: disable=protected-access
    assert LadbrokesScraper._makeSlug(testInput) == expected
