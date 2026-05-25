#!/usr/bin/env python3
"""
  scoring.py
  ==========

  Description:           TODO
  Author:                Michael De Pasquale
  Creation Date:         2024-12-24
  Modification Date:     2025-08-23

"""

# https://users.cecs.anu.edu.au/~Peter.Christen/publications/tr-cs-06-02.pdf

## Scoring ideas
# - Strip redundant suffixes based on sport
#   + e.g. soccer remove "FC" or "Football Club"
#   + Six Nations Championship / The Six Nations
# - Replace (M)/(W) with Mens/Womens and vice versa, return highest score
# - For competition names, strip suffixes like "Matches", separators like " - "
# - 1, 2, 3: Try one, two, three
# - "Saint": St. -> St
# - "-" -> " "

# Region-specific normalisation
## Soccer
# Germany: Strip "FC" from start
# England: Strip "FC"/"Football Club" from end
# Spain: Strip "Real", "CA" from start
# Brazil: Strip trailing "SP"

# League names
# - Acronyms should be exact (e.g. NCAA vs NCAAF)

# Team names
# ..


# TODO: Esports
# - Counter-Strike, CS2 -> Counter-Strike 2
# - LoL -> League of Legends
# - Dota / Defense of the Ancients
#

from datetime import datetime
import math
import unicodedata

# pylint: disable=import-error
import Levenshtein

from .countries import Countries


def _normaliseGeneric(name: str) -> str:
    # Disabled this for now, slow and shouldn't have much of a performance impact
    # FIXME: Something like rust's deunicode whould be good to do here..
    # FIXME: Parsers should probably do this once, rather than doing it here many times
    # name = unicodedata.normalize("NFKC", name)

    return name.lower()


def scoreGeneric(a: str, b: str) -> float:
    """Generic name similarity scoring function."""
    return Levenshtein.jaro_winkler(_normaliseGeneric(a), _normaliseGeneric(b))


def _normalisePersonalName(name: str) -> str:
    # Handle pair names - e.g. 'Martin, A/Neuchrist, M' for unibet
    # FIXME: Review other agencies to see how they handle this case
    if name.find("/") != -1:
        return "/".join(map(_normalisePersonalName, name.split("/")))

    # unibet: 'Mpetshi, Perricard, D' -> D Mpetshi Perricard
    if name.find(",") != -1:
        ns = name.split(",")

        return _normaliseGeneric(
            " ".join(map(lambda s: s.strip(), [ns[-1]] + ns[0:-1]))
        )

    return _normaliseGeneric(name)


def scorePersonalNames(a: str, b: str) -> float:
    """Similarity scoring function for two personal names."""
    # TODO: handle potentially missing middle name
    return Levenshtein.jaro_winkler(
        _normalisePersonalName(a), _normalisePersonalName(b)
    )


def _normaliseLeagueName(name: str) -> str:
    words = name.split(" ")

    # Remove country names/adjectives
    # Just look at first 1 or 2 words
    if len(words) > 1 and Countries.lookup(words[0] + " " + words[1]):
        words = words[2:]

    elif Countries.lookup(words[0]):
        words = words[1:]

    # Remove any other bullshit
    # Should probably remove trailing "League", but this will lead to issues, e.g.
    # "A League" -> "A"
    if words and words[-1].lower() in ("matches",):
        words = words[:-1]

    return _normaliseGeneric(" ".join(words))


def scoreLeagueNames(a: str, b: str) -> float:
    """Score two league names."""
    # NOTE: Issue - sometimes better to have country names/adjectives
    # e.g. "Serbia Cup" -> "Cup"
    # Team name scoring should put the correct match over the line, but maybe good idea
    # to add extra penalty/bonus for exact match without changes
    return Levenshtein.jaro_winkler(_normaliseLeagueName(a), _normaliseLeagueName(b))


def scoreTimeDelta(a: datetime, b: datetime, maxMins: float) -> float:
    """Compute a score between 0 and 1 reflecting how close together two times are
    relative to maxMins.

    Parameters
    ----------
    a, b : datetime
      The times to compare.

    maxMins : float
      Time difference, in minutes, at and above which score should be 0
    """
    assert maxMins > 0

    delta = a - b
    deltaMins = min(math.fabs(delta.total_seconds()) / 60, maxMins)

    # % of remaining maxMins
    return (maxMins - deltaMins) / maxMins
