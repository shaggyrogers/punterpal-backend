#!/usr/bin/env python3
"""
  matcher.py
  ==========

  Description:           TODO
  Author:                Michael De Pasquale
  Creation Date:         2025-01-29
  Modification Date:     2026-05-25

"""

# NOTE:
# * "Schema" means everything not agency-specific (i.e. not markets)
# * Current approach is to treat one agency as source of truth and use it only for
#   updating schema (sports/leagues/teams/events/participants).
#   - Need to updateSchema with this agency first, then updateMarkets again for this
#     agency and everything else

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from itertools import chain
import logging
import math
import statistics
from typing import Union

from parsers.types import AgencyData
from matcher.types import (
    NameScoringType,
    NamedBaseModel,
    CanonTree,
    CanonSport,
    CanonCompetition,
    CanonEvent,
    CanonParticipant,
    CanonMarket,
    CanonMarketOutcome,
)
from matcher.scoring import (
    scoreGeneric,
    scorePersonalNames,
    scoreLeagueNames,
    scoreTimeDelta,
)
from matcher.store import SchemaStore

# FIXME: A lot of duplicated logic in _find methods, can probably refactor
# TODO: Anchor base agency to sports? This way can use other agencies for particular sports
# TODO: Store/compare region when available

# Thresholds for a valid match.
MIN_CONFIDENCE = 0.9
MIN_CONFIDENCE_PARTICIPANT = 0.8

# Score to return if no score can be computed
# FIXME: Is this appropriate?
FALLBACK_SCORE = 0.75

# Maximum difference between two start times. Used for scoring and matching events.
MAX_MINS = 2880  # 2 days, was 6 hours

# Amount of time, in mins, after an event has started before it should be pruned
EVENT_PRUNE_MINS = 0


class Matcher:
    """Integrates data from parsers."""

    def __init__(self, store: SchemaStore) -> None:
        assert store

        self._store = store
        self._tree = None
        self._log = logging.getLogger(
            self.__class__.__module__ + "." + self.__class__.__qualname__
        )
        self._log.setLevel("DEBUG")

    def save(self) -> None:
        """Write contents of _tree to the given file path."""
        self._log.info(f"Saving schema, store={self._store}")
        assert self._tree is not None
        self._store.save(self._tree)

    def load(self) -> None:
        """Load contents of _tree from the given file path."""
        self._log.info(f"Loading schema, store={self._store} ")
        assert self._tree is None
        self._tree = self._store.load()

    def updateSchema(self, agencyData: AgencyData) -> None:
        """Updates the tree of canonical sports/leagues/teams/events using new data
        from the agency originally used to create the tree."""
        self._log.info(f"Updating schema (from {agencyData.agencyName})")

        if not self._tree:
            self._tree = CanonTree(baseAgency=agencyData.agencyName)

        # Must only update schema from same agency
        if self._tree.baseAgency != agencyData.agencyName:
            raise ValueError(
                f"Agency mismatch: got {agencyData.agencyName}, expected"
                f" {self._tree.baseAgency}"
            )

        self._tree.setSchemaLastUpdated()
        updateStarted = datetime.now()
        stats = {
            "addedSports": 0,
            "addedComps": 0,
            "addedEvents": 0,
            "addedParts": 0,
        }

        # FIXME: Better to use name only and not synonyms? names should be the same
        for agencySport in agencyData.sports.values():
            sport = self._findExactMatch(agencySport.name, self._tree.sports.values())

            # Add sport if necessary
            if not sport:
                self._log.debug(f"Creating new sport '{agencySport.name}'")
                sport = CanonSport(name=agencySport.name)
                self._tree.sports[agencySport.name] = sport
                stats["addedSports"] += 1

            for agencyComp in agencySport.competitions.values():
                comp = self._findExactMatch(
                    agencyComp.name, sport.competitions.values()
                )

                # Add competitions if necessary
                participants = self._getAgencyParticipantNames(agencyComp)

                if not comp:
                    self._log.debug(f"Creating league '{agencySport.name}'")
                    comp = CanonCompetition(name=agencyComp.name)
                    comp.participants = {
                        name: CanonParticipant(name=name) for name in participants
                    }
                    sport.competitions[comp.name] = comp
                    stats["addedComps"] += 1

                # Update participants, checking synonyms for matches just in case
                toAddMap = {
                    name: self._findExactMatch(name, comp.participants.values())
                    for name in participants
                }

                for name, _ in filter(lambda tup: not tup[1], toAddMap.items()):
                    self._log.debug(f"Creating new participant '{name}'")
                    comp.participants[name] = CanonParticipant(name=name)
                    stats["addedParts"] += 1

                for agencyEvent in agencyComp.events.values():
                    # Potential issue with adding duplicates if start time is changed.
                    # Address this by looking for match with the same participant names and
                    # reasonably close start times.
                    eventParticipants = [
                        self._findExactMatch(name, comp.participants.values())
                        for name in agencyEvent.participants
                    ]
                    assert all(eventParticipants)

                    event = self._findEventExactMatch(
                        eventParticipants,
                        agencyEvent.start,
                        comp.events.values(),
                    )

                    # Add event if necessary
                    # Don't add markets / marketoutcomes here, only care about schema
                    if not event:
                        event = CanonEvent(
                            start=agencyEvent.start,
                            participantNames={p.name for p in eventParticipants},
                        )
                        self._log.debug(f"Creating new event '{event.name}'")
                        comp.events[event.name] = event
                        stats["addedEvents"] += 1

        self._log.info(
            "Schema update finished after"
            f" {(datetime.now() - updateStarted).total_seconds():.1f}s."
        )
        self._log.info(
            f"Added {stats['addedSports']} sports, {stats['addedComps']} competitions,"
            f" {stats['addedEvents']} events and {stats['addedParts']} participants"
        )

    def updateMarkets(self, agencyData: AgencyData) -> None:
        """Update market data."""
        self._tree.onUpdateStarted(agencyData.agencyName)

        # TODO: add missing values from non-base agencies?
        # - flag auto-added nodes?
        self._log.info(f"Updating market data for agency {agencyData.agencyName}")
        updateStarted = datetime.now()

        for agencySport in agencyData.sports.values():
            sport = self._findSport(
                agencyData.agencyName, agencySport, self._tree.sportScorer
            )

            if not sport:
                continue

            # Use alternate scorers if specified
            sportCompScorer = self._tree.defaultCompScorer.update(sport.compScorer)
            sportPartScorer = self._tree.defaultPartScorer.update(sport.partScorer)

            for agencyComp in agencySport.competitions.values():
                comp = self._findCompetition(
                    agencyData.agencyName,
                    sport,
                    agencyComp,
                    sportCompScorer,
                    sportPartScorer,
                )

                if not comp:
                    continue

                # Use alternate part scorer if specified
                compPartScorer = sportPartScorer.update(comp.partScorer)

                for agencyEvent in agencyComp.events.values():
                    event = self._findEvent(
                        agencyData.agencyName, sport, comp, agencyEvent, compPartScorer
                    )

                    if not event:
                        continue

                    self._tree.stats[
                        agencyData.agencyName
                    ].updatedMarkets += self._updateMarketData(
                        sport,
                        comp,
                        event,
                        agencyEvent,
                        agencyData.agencyName,
                        compPartScorer,
                    )

        self._log.info(
            f"{self._tree.stats[agencyData.agencyName].updatedMarkets} markets updated"
            f" for {agencyData.agencyName}"
            f" after {(datetime.now() - updateStarted).total_seconds():.1f}s."
            f" {repr(self._tree.stats[agencyData.agencyName])}"
        )

    def clean(self) -> None:
        """Prune redundant event nodes"""
        # Remove expired events
        self._log.info("Pruning expired events")
        pruneTime = datetime.now(timezone.utc) - timedelta(minutes=EVENT_PRUNE_MINS)
        pruneCount = 0

        for comp in chain.from_iterable(
            map(lambda s: s.competitions.values(), self._tree.sports.values())
        ):
            delEventKeys = list(
                map(
                    lambda t: t[0],
                    filter(lambda t: pruneTime > t[1].start, comp.events.items()),
                )
            )
            pruneCount += len(delEventKeys)

            for k in delEventKeys:
                del comp.events[k]

        self._log.info(f"clean() removed {pruneCount} expired events")

        # Remove markets with no prices for any outcome. not sure how this happens?
        pruneCount = 0

        for event in chain.from_iterable(
            map(
                lambda c: c.events.values(),
                chain.from_iterable(
                    map(lambda s: s.competitions.values(), self._tree.sports.values())
                ),
            )
        ):

            delMarkets = list(
                filter(
                    lambda market: any(
                        map(lambda o: not o.prices, market.outcomes.values())
                    ),
                    event.markets.values(),
                )
            )

            for market in delMarkets:
                pruneCount += 1
                del event.markets[market.marketType]

        getattr(self._log, "warning" if pruneCount else "info")(
            f"clean() removed {pruneCount} markets missing prices"
        )

    @property
    def tree(self) -> CanonTree:
        """Returns the CanonTree instance."""
        return self._tree

    def _findExactMatch(
        self, name: str, candidates: Iterable[NamedBaseModel]
    ) -> Union[NamedBaseModel, None]:
        """Find a NamedBaseModel exactly matching a given name, checking both
        name and synonyms.

        Returns
        -------
        A matching NamedBaseModel if found, otherwise None. Raises ValueError if more
        than one match exists.
        """
        match = None

        for candidate in candidates:
            if name == candidate.name or name in candidate.synonyms:
                if match is not None:
                    raise ValueError(
                        f"Multiple matches found for name '{name}'!"
                        f" New match: {candidate}, current match: {match}"
                    )

                match = candidate

        return match

    def _findEventExactMatch(
        self,
        participants: Iterable[CanonParticipant],
        agencyStart: datetime,
        candidates: Iterable[CanonEvent],
        maxMins: float = MAX_MINS,
    ) -> Union[CanonEvent, None]:
        """Find an event in candidates with participant canonical names matching canonNames
        where start times are no more than maxMins minutes apart.

        Returns
        -------
        A matching CanonEvent, or None if no match was found. Raises ValueError if
        more than one match exists.
        """
        match = None
        canonNames = {p.name for p in participants}

        for candidate in candidates:
            if canonNames != candidate.participantNames:
                continue

            if (
                math.fabs((candidate.start - agencyStart).total_seconds() / 60)
                <= maxMins
            ):
                if match is not None:
                    raise ValueError(
                        f"Multiple matches found for event! participants={canonNames}"
                        f" start={agencyStart.isoformat()}"
                        f" New match {repr(candidate)}, previous match: {repr(match)}"
                    )

                match = candidate

        return match

    @classmethod
    def _getAgencyParticipantNames(cls, agencyComp: "AgencyCompetition") -> set:
        """Return the set of all participant names for the given competition."""
        return set(
            chain.from_iterable(
                map(lambda p: p.name, event.participants.values())
                for event in agencyComp.events.values()
            )
        )

    @classmethod
    def _scoreName(
        cls, candidate: str, target: NamedBaseModel, scorer: NameScoringType
    ) -> float:
        """Compute the highest similarity score for candidate amongst all known names of
        target.
        """
        if candidate in target.antonyms:
            return 0

        scoreFn = None

        if scorer == NameScoringType.GENERIC:
            scoreFn = scoreGeneric

        elif scorer == NameScoringType.PERSONAL_NAME:
            scoreFn = scorePersonalNames

        elif scorer == NameScoringType.LEAGUE_NAME:
            scoreFn = scoreLeagueNames

        assert scoreFn is not None

        return max(map(lambda syn: scoreFn(candidate, syn), target.synonyms))

    @classmethod
    def _scoreNameGroup(
        cls, candidate: str, targets: Iterable[NamedBaseModel], scorer: NameScoringType
    ) -> float:
        """Run _scoreName for each target and return the highest score."""
        return max(map(lambda t: cls._scoreName(candidate, t, scorer), targets))

    def _evaluateCompNameScore(
        self,
        agencySport: "AgencySport",
        sport: "CanonSport",
        compScorer: NameScoringType,
    ) -> float:
        # FIXME: Should probably omit competition names like "Matches" etc.
        scores = (
            [
                self._scoreNameGroup(
                    agencyComp.name, sport.competitions.values(), compScorer
                )
                for agencyComp in agencySport.competitions.values()
            ]
            if sport.competitions
            else None
        )

        # No scores available
        if not scores:
            # self._log.warning(
            #     f"Using fallback comp name score for sport {agencySport.name}"
            # )
            return FALLBACK_SCORE

        # FIXME: Is there a more appropriate measure than mean?
        return statistics.mean(scores)

    def _evaluateCompTeamScore(
        self,
        agencyComp: "AgencyCompetition",
        comp: CanonCompetition,
        partScorer: NameScoringType,
    ) -> float:
        """Compute a score for participant name similarity between the two competitions."""
        parts = self._getAgencyParticipantNames(agencyComp)

        if not parts or not comp.participants:
            # self._log.warning(
            #     f"Using fallback comp team score for competition {agencyComp.name}"
            # )
            return FALLBACK_SCORE

        scores = [
            self._scoreNameGroup(
                agencyParticipant, comp.participants.values(), partScorer
            )
            for agencyParticipant in self._getAgencyParticipantNames(agencyComp)
        ]

        return statistics.mean(scores)

    def _evaluateSportCompTeamScore(
        self, agencySport: "AgencySport", sport: CanonSport, partScorer: NameScoringType
    ) -> float:
        """Compute a score reflecting how many team/participant names are
        shared/similar for the two sports."""
        # For each competition, get the highest team score for any canonical competition
        scores = (
            [
                max(
                    (
                        self._evaluateCompTeamScore(
                            agencyComp, comp, partScorer.update(comp.partScorer)
                        )
                        for comp in sport.competitions.values()
                    )
                )
                for agencyComp in agencySport.competitions.values()
            ]
            if sport.competitions
            else None
        )

        if not scores:
            # self._log.warning(
            #     f"Using fallback sport comp team score for sport {agencySport.name}"
            # )
            return FALLBACK_SCORE

        return statistics.mean(scores)

    def _findSport(
        self, agency: str, agencySport: "AgencySport", sportScorer: NameScoringType
    ) -> CanonSport:
        """Find the CanonSport corresponding to the given AgencySport."""
        highestScore = 0
        highestScoreSport = None
        matchNameScore = 0
        matchCompScore = 0
        matchCompTeamScore = 0

        for sport in self._tree.sports.values():
            nameScore = self._scoreName(agencySport.name, sport, sportScorer)
            compScore = self._evaluateCompNameScore(
                agencySport,
                sport,
                self._tree.defaultCompScorer.update(sport.compScorer),
            )
            compTeamScore = self._evaluateSportCompTeamScore(
                agencySport,
                sport,
                self._tree.defaultPartScorer.update(sport.partScorer),
            )

            # Compute overall score
            # TODO: Maybe bump up compScore weight when we have more data
            score = 0.72 * nameScore + 0.05 * compScore + 0.23 * compTeamScore

            # 20% score bonus for exact name matches
            # FIXME: Probably better to just store everything in lowercase?
            if agencySport.name.lower() in set(
                map(lambda s: s.lower(), sport.synonyms)
            ):
                score = score + (1 - score) * 0.20

            if score > highestScore:
                highestScore = score
                highestScoreSport = sport
                matchNameScore = nameScore
                matchCompScore = compScore
                matchCompTeamScore = compTeamScore

        self._log.debug(
            f"Best match for sport {agencySport.name} is {highestScoreSport.name}"
            f" score={highestScore:.3f} nameScore={matchNameScore:.3f}"
            f" compScore={matchCompScore:.3f} compTeamScore={matchCompTeamScore:.3f}"
        )

        # Score must be above threshold
        success = highestScore >= MIN_CONFIDENCE

        if not success:
            self._log.debug(f"Failed to find match for sport '{agencySport.name}'")
            self._tree.recordMatchFail(
                agency,
                agencySport.name,
                highestScoreSport.name if highestScoreSport else None,
                highestScore,
                matchNameScore=matchNameScore,
                matchCompScore=matchCompScore,
                matchCompTeamScore=matchCompTeamScore,
            )

        return highestScoreSport if success else None

    def _findCompetition(
        self,
        agency: str,
        sport: "CanonSport",
        agencyCompetition: "AgencyCompetition",
        compScorer: NameScoringType,
        partScorer: NameScoringType,
    ) -> CanonCompetition:
        """Find the CanonCompetition corresponding to the given AgencyCompetition."""
        highestScoreComp = None
        highestScore = 0
        matchNameScore = 0
        matchTeamScore = 0

        # TODO: Score similarity between event start times, participants?
        for comp in sport.competitions.values():
            nameScore = self._scoreName(agencyCompetition.name, comp, compScorer)
            teamScore = self._evaluateCompTeamScore(
                agencyCompetition, comp, partScorer.update(comp.partScorer)
            )

            score = 0.7 * nameScore + 0.3 * teamScore

            if score > highestScore:
                highestScore = score
                highestScoreComp = comp
                matchNameScore = nameScore
                matchTeamScore = teamScore

        self._log.debug(
            f"Best match for competition {agencyCompetition.name} is {highestScoreComp.name}"
            f" score={highestScore:.3f} nameScore={matchNameScore:.3f}"
            f" teamScore={matchTeamScore:.3f}"
        )

        # Score must be above threshold
        success = highestScore >= MIN_CONFIDENCE

        if not success:
            self._log.debug(
                f"Failed to find match for competition '{agencyCompetition.name}'"
            )
            self._tree.recordMatchFail(
                agency,
                agencyCompetition.name,
                highestScoreComp.name if highestScoreComp else None,
                highestScore,
                sport=sport.name,
                matchNameScore=matchNameScore,
                matchTeamScore=matchTeamScore,
            )

        return highestScoreComp if highestScore >= MIN_CONFIDENCE else None

    def _findEvent(
        self,
        agency: str,
        sport: "CanonSport",
        competition: "CanonCompetition",
        agencyEvent: "AgencyEvent",
        partScorer: NameScoringType,
    ) -> "CanonEvent":
        """ """
        highestScoreEvent = None
        highestScore = -1
        matchParticipantScore = float("nan")
        matchTimeScore = float("nan")

        if not competition.events:
            self._log.debug("_findEvent(): Competition has no events!")

            return None

        for event in competition.events.values():
            # Immediate fail if there is a different number of participants.
            if len(event.participantNames) != len(agencyEvent.participants):
                self._log.warning(
                    f"Participant count mismatch for event {agencyEvent.name}"
                )

                continue

            canonParticipants = [
                competition.participants[p] for p in event.participantNames
            ]
            participantScore = statistics.mean(
                [
                    self._scoreNameGroup(part, canonParticipants, partScorer)
                    for part in agencyEvent.participants
                ]
            )
            timeScore = scoreTimeDelta(agencyEvent.start, event.start, MAX_MINS)
            score = statistics.mean([participantScore, timeScore])

            if score > highestScore:
                highestScoreEvent = event
                highestScore = score
                matchParticipantScore = participantScore
                matchTimeScore = timeScore

        if highestScoreEvent is None:
            # Let exception occur, this likely means parser is broken
            self._log.error(
                "No matching events! Draw may have been included as a participant"
            )

        self._log.debug(
            f"Best match for event {agencyEvent.name} is {highestScoreEvent.name}"
            f" score={highestScore:.3f} participantScore={matchParticipantScore:.3f}"
            f" timeScore={matchTimeScore:.3f}"
        )

        success = highestScore >= MIN_CONFIDENCE

        if not success:
            self._log.debug(f"Failed to find match for event '{agencyEvent.name}'")
            self._tree.recordMatchFail(
                agency,
                agencyEvent.name,
                highestScoreEvent.name if highestScoreEvent else None,
                highestScore,
                sport=sport.name,
                league=competition.name,
                matchParticipantScore=matchParticipantScore,
                matchTimeScore=matchTimeScore,
            )

        return highestScoreEvent if highestScore >= MIN_CONFIDENCE else None

    def _findEventParticipantCanonName(
        self,
        agency: str,
        sport: CanonSport,
        comp: CanonCompetition,
        event: CanonEvent,
        name: str,
        partScorer: NameScoringType,
    ) -> Union[str, None]:
        """Find the canonical name for a participant within an event from an agency
        name. Returns a match if found, None if unsuccessful."""
        highestScore = 0
        highestScoreName = None

        for part in map(lambda key: comp.participants[key], event.participantNames):
            score = self._scoreName(name, part, partScorer)

            if score > highestScore:
                if highestScore > MIN_CONFIDENCE_PARTICIPANT:
                    # Fail - inability to pick out event participants is catastrophic
                    self._log.error(
                        f"Multiple matches for participant '{name}' in event {event.name}!"
                        f" Prev. match was '{highestScoreName}'"
                    )

                    return None

                highestScore = score
                highestScoreName = part.name

        self._log.debug(
            f"Best match for event participant {name} is {highestScoreName}"
            f" score={highestScore:.3f}"
        )

        # NOTE: We use a lower minimum confidence here, since we have had multiple
        # rounds of checks for parent nodes up to this point.
        success = highestScore > MIN_CONFIDENCE_PARTICIPANT

        if not success:
            self._log.debug(f"Failed to find match for participant '{name}'")
            self._tree.recordMatchFail(
                agency,
                name,
                highestScoreName,
                highestScore,
                sport=sport.name,
                league=comp.name,
            )

        return highestScoreName if success else None

    def _updateMarketData(
        self,
        sport: CanonSport,
        comp: CanonCompetition,
        event: CanonEvent,
        agencyEvent: "AgencyEvent",
        agencyName: str,
        partScorer: NameScoringType,
    ) -> None:
        """Update odds"""
        updatedMarketCount = 0

        for agencyMarket in agencyEvent.markets.values():
            if self._updateMarketDataSingle(
                sport, comp, event, agencyEvent, agencyMarket, agencyName, partScorer
            ):
                updatedMarketCount += 1

        return updatedMarketCount

    def _updateMarketDataSingle(
        self,
        sport: CanonSport,
        comp: CanonCompetition,
        event: CanonEvent,
        agencyEvent: "AgencyEvent",
        agencyMarket: "AgencyMarket",
        agencyName: str,
        partScorer: NameScoringType,
    ) -> bool:
        """Update odds for a single market."""
        outcomeData = {}

        for agencyOutcome in agencyMarket.outcomes.values():
            outcomeKey = None

            if not agencyOutcome.isDraw:
                outcomeKey = self._findEventParticipantCanonName(
                    agencyName,
                    sport,
                    comp,
                    event,
                    agencyOutcome.associatedParticipant.name,
                    partScorer,
                )

                # Make sure we can unqiuely identify each participant
                if outcomeKey is None:
                    self._log.error(
                        f"Skipping market {agencyMarket.marketType} for event {agencyEvent.name}, unable to"
                        f" identify participant '{agencyOutcome.associatedParticipant.name}'"
                    )

                    return False

            # Possible for both agency participant names to be incorrectly resolved to
            # the same canonical name
            if outcomeKey in outcomeData:
                self._log.error(
                    f"Skipping market {agencyMarket.marketType} for event {agencyEvent.name},"
                    f" resolved participant keys are duplicated!"
                )

                return False

            assert (outcomeKey is None) == agencyOutcome.isDraw
            outcomeData[outcomeKey] = {
                "associatedParticipantName": outcomeKey,
                "isDraw": agencyOutcome.isDraw,
                "price": agencyOutcome.price,
            }

        assert outcomeData

        # Can't build CanonMarket incrementally as validation will fail.
        if agencyMarket.marketType not in event.markets:
            event.markets[agencyMarket.marketType] = CanonMarket(
                marketType=agencyMarket.marketType,
                outcomes={
                    k: CanonMarketOutcome(
                        prices={agencyName: v["price"]},
                        associatedParticipantName=v["associatedParticipantName"],
                        isDraw=v["isDraw"],
                    )
                    for k, v in outcomeData.items()
                },
            )

        else:
            for k, v in outcomeData.items():
                outcome = event.markets[agencyMarket.marketType].outcomes[k]
                assert v["isDraw"] == outcome.isDraw
                outcome.prices[agencyName] = v["price"]

        return True
