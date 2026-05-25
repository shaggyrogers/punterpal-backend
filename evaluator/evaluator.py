#!/usr/bin/env python3
"""
  evaluator.py
  ============

  Description:           TODO
  Author:                Michael De Pasquale
  Creation Date:         2025-02-06
  Modification Date:     2025-08-23

"""

from collections import namedtuple
from collections.abc import Iterable
from datetime import datetime
from itertools import permutations
import json
import logging
from typing import Union

import pandas

from matcher.types import MarketType
from matcher import Matcher


class Evaluator:
    """Evaluate markets for arbitrage potential."""

    PricedOutcome = namedtuple(
        "PricedOutcome",
        [
            "agency",
            "outcome",
            "price",
        ],
    )
    Market = namedtuple(
        "Market",
        [
            # Metadata
            "sport",
            "competition",
            "start",
            "participant1",
            "participant2",
            "marketType",
            # Outcomes - list of PricedOutcome
            "outcomes",
            # Describes how much we should expect to get back from total wager.
            # e.g. 1.05 => expect to earn additional 5%. Can't call it 'return'
            # This is the inverse of book percentage
            "returnFactor",
        ],
    )

    def __init__(self) -> None:
        self._log = logging.getLogger(
            self.__class__.__module__ + "." + self.__class__.__qualname__
        )
        self._log.setLevel("DEBUG")

    def evaluate(
        self,
        matcher: Matcher,
        sportKey: Union[str, None] = None,
        compKey: Union[str, None] = None,
        considerAgencies: Union[Iterable[str], None] = None,
        includeAgencies: Union[Iterable[str], None] = None,
        resultCount: Union[int, None] = None,
        beforeDate: Union[datetime, None] = None,
    ) -> pandas.DataFrame:
        """Evaluate, optionally filtering/limiting results.

        Note that considerAgencies are those that may be considered, while
        includeAgencies must all be included in returned results.
        """
        self._log.debug(
            f"evaluating sportKey={sportKey} compKey={compKey}"
            f" considerAgencies={considerAgencies} includeAgencies={includeAgencies}"
            f" resultCount={resultCount}"
        )

        # Should have sportKey if compKey was provided
        if compKey and not sportKey:
            raise ValueError("compKey provided with no sportKey!")

        assert not beforeDate or beforeDate.tzinfo is not None
        assert matcher.tree

        # Evaluate everything, sort by return
        df = (
            pandas.DataFrame.from_records(
                self._iterMarkets(
                    matcher,
                    sportKey=sportKey,
                    compKey=compKey,
                    considerAgencies=self._validateAgencyList(
                        matcher, considerAgencies
                    ),
                    includeAgencies=self._validateAgencyList(matcher, includeAgencies),
                    beforeDate=beforeDate,
                ),
                columns=self.Market._fields,
            )
            .sort_values(
                by="returnFactor",
                ascending=False,
                ignore_index=True,
            )
            .loc[: (resultCount - 1 if resultCount else None)]
        )

        return df

    @classmethod
    def toCSV(cls, df: pandas.DataFrame, *args, **kwargs) -> str:
        """Convert a result DataFrame to CSV. Remaining arguments are passed directly to
        pandas.DataFrame.to_csv()."""
        df["start"] = df["start"].map(lambda s: s.isoformat())
        df["marketType"] = df["marketType"].map(lambda mt: mt.name)
        df["outcomes"] = df["outcomes"].map(cls._serialiseOutcomes)

        return df.to_csv(*args, **kwargs)

    def _validateAgencyList(
        self, matcher: Matcher, agencies: Union[None, Iterable[str]]
    ) -> Union[None, set[str]]:
        """Validate an optional agency list. Returns an equivalent set, or None if
        agencies is None. Raises an exception if validation fails."""
        if agencies is None:
            return None

        agencies = set(agencies)

        if not all(x in matcher.tree.agencies for x in agencies):
            raise ValueError(f"One or more agency keys are unknown: {agencies}")

        if not agencies:
            raise ValueError("Agency list must not be empty!")

        return agencies

    @staticmethod
    def _serialiseOutcomes(outcomes: list["Evaluator.PricedOutcome"]) -> str:
        return json.dumps(
            {
                "agency": [o.agency for o in outcomes],
                "outcome": [o.outcome for o in outcomes],
                "price": [o.price for o in outcomes],
            }
        )

    def _iterMarkets(
        self,
        matcher: Matcher,
        sportKey: Union[str, None] = None,
        compKey: Union[str, None] = None,
        considerAgencies: Union[set[str], None] = None,
        includeAgencies: Union[set[str], None] = None,
        beforeDate: Union[datetime, None] = None,
    ) -> Iterable["Evaluator.Market"]:
        """Generator which yields Market instances matching the given filters"""
        for curSportKey, sport in matcher.tree.sports.items():
            if sportKey and sportKey != curSportKey:
                continue

            for curCompKey, comp in sport.competitions.items():
                if compKey and compKey != curCompKey:
                    continue

                for event in comp.events.values():
                    if beforeDate and event.start > beforeDate:
                        continue

                    for market in event.markets.values():
                        result = self._makeMarket(
                            sport,
                            comp,
                            event,
                            market,
                            considerAgencies=considerAgencies,
                            includeAgencies=includeAgencies,
                        )

                        if result is not None:
                            yield result

    def _makeMarket(
        self,
        sport: "CanonSport",
        comp: "CanonCompetition",
        event: "CanonEvent",
        market: "CanonMarket",
        considerAgencies: Union[set[str], None] = None,
        includeAgencies: Union[set[str], None] = None,
    ) -> Union["Evaluator.Market", None]:
        """Make a Market tuple corresponding to the best set of prices, optionally
        requiring the inclusion of specific agencies."""
        if not market.outcomes:
            self._log.debug(
                f"Skipping market with no outcomes (sport={sport.name} comp={comp.name}"
                f" event={event.name}"
            )

            return None

        # Get set of PricedOutcomes with the best sum of prices
        bestPerms = list(
            sorted(
                self._iterAgencyPerms(
                    market,
                    considerAgencies,
                    includeAgencies,
                ),
                key=lambda tup: tup[0],
                reverse=True,
            )
        )

        if not bestPerms:
            # Will happen if there aren't enough agencies with prices for the number of
            # outcomes.
            return None

        bestPerm = bestPerms[0]

        # Construct Market
        outcomes = bestPerm[1:]
        partNames = list(sorted(event.participantNames))
        assert len(partNames) == 2

        return self.Market(
            sport=sport.name,
            competition=comp.name,
            start=event.start,
            participant1=partNames[0],
            participant2=partNames[1],
            marketType=market.marketType,
            outcomes=outcomes,
            returnFactor=self._computeReturn(outcomes),
        )

    def _computeReturn(self, odds: tuple["PricedOutcome"]) -> float:
        """Compute expected return for matched betting on a set of odds covering all
        possible outcomes"""
        overround = sum(1 / outcome.price for outcome in odds) - 1

        return 1 - overround

    def _iterAgencyPerms(
        self,
        market: "CanonMarket",
        considerAgencies: Union[set[str], None],
        includeAgencies: Union[set[str], None],
    ) -> Iterable[tuple]:
        """Take a market and yield tuples like (return, (agency1, outcome1, price1) ...)"""
        # HACK: Need to handle None draw key separately.
        # Probably would be better to just use 'Draw' as key.

        # Map of ordering to outcome names
        if market.marketType == MarketType.WINNER_DRAW:
            outcomeNames = list(sorted(filter(None, market.outcomes.keys())))
            outcomeNames.insert(1, None)

        else:
            outcomeNames = list(sorted(market.outcomes.keys()))

        # Get agencies and combined prices. Assumes agencies have prices for every outcome
        for agencyTup in permutations(
            list(market.outcomes.values())[0].prices.keys(), len(market.outcomes)
        ):
            incAgencies = set()
            outcomeTups = []

            for idx, agency in zip(range(len(agencyTup)), agencyTup):
                outcome = outcomeNames[idx]
                outcomeTups.append(
                    self.PricedOutcome(
                        agency,
                        outcome or "Draw",
                        market.outcomes[outcome].prices[agency],
                    )
                )
                incAgencies.add(agency)

            # Agency filters
            if considerAgencies and not incAgencies.issubset(considerAgencies):
                continue

            if includeAgencies and not all(
                map(lambda a: a in incAgencies, includeAgencies)
            ):
                continue

            yield [self._computeReturn(outcomeTups)] + outcomeTups


#  vim: set ts=4 sw=4 tw=88 fdm=expr ff=unix fenc=utf-8 et :
