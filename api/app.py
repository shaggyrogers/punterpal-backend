#!/usr/bin/env python3
"""
  app.py
  ======

  Description:           TODO
  Author:                Michael De Pasquale
  Creation Date:         2025-02-13
  Modification Date:     2025-08-23

"""

import logging

from flask import Flask, request

from api_types import (
    EvaluateRequest,
    EvaluateResponse,
    EvaluateKeysRequest,
    EvaluateKeysResponse,
    EvaluatorPricedOutcome,
    EvaluatorResult,
    StatusResponse,
)

from evaluator import Evaluator
from matcher import Matcher
from matcher.store import RedisSchemaStore
from .tasks.app import TASKS
from .config import REDIS_HOST, REDIS_PORT

LOG = logging.getLogger(__name__)
LOG.setLevel("DEBUG")

APP = Flask(__name__)
APP.register_blueprint(TASKS, url_prefix="/tasks")


@APP.route("/status", methods=["GET"])
def status():
    """Get backend status"""
    matcher = Matcher(RedisSchemaStore(host=REDIS_HOST, port=REDIS_PORT))
    matcher.load()

    return StatusResponse(
        lastSchemaUpdate=matcher.tree.lastSchemaUpdate,
        lastMarketUpdate={k: v.lastUpdated for k, v in matcher.tree.stats.items()},
        stats={k: v.model_dump(mode="json") for k, v in matcher.tree.stats.items()},
    ).model_dump(mode="json")


@APP.route("/evaluate", methods=["POST"])
def evaluate():
    """Perform evaluation"""
    req = EvaluateRequest(**request.get_json())

    matcher = Matcher(RedisSchemaStore(host=REDIS_HOST, port=REDIS_PORT))
    matcher.load()
    df = Evaluator().evaluate(
        matcher,
        sportKey=req.sport,
        compKey=req.competition,
        considerAgencies=req.considerAgencies,
        includeAgencies=req.includeAgencies,
        resultCount=req.resultCount,
        beforeDate=req.getBeforeDate(),
    )

    return EvaluateResponse(
        results=[
            EvaluatorResult(
                sport=row["sport"],
                competition=row["competition"],
                start=row["start"],
                participant1=row["participant1"],
                participant2=row["participant2"],
                # FIXME: using name instead of object
                marketType=row["marketType"].name,
                outcomes=[
                    EvaluatorPricedOutcome(
                        agency=o.agency, outcome=o.outcome, price=o.price
                    )
                    for o in row["outcomes"]
                ],
                returnFactor=row["returnFactor"],
            )
            for _, row in df.iterrows()
        ]
    ).model_dump(mode="json")


@APP.route("/evaluate/keys", methods=["POST"])
def keys():
    """Get schema keys"""
    req = EvaluateKeysRequest(**request.get_json())

    matcher = Matcher(RedisSchemaStore(host=REDIS_HOST, port=REDIS_PORT))
    matcher.load()

    # FIXME: Prune keys with no markets
    return EvaluateKeysResponse(
        agencies=list(sorted(matcher.tree.stats.keys())),
        sports=list(sorted(matcher.tree.sports.keys())),
        competitions=(
            None
            if not req.sport
            else list(sorted(matcher.tree.sports[req.sport].competitions.keys()))
        ),
    ).model_dump(mode="json")
