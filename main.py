#!/usr/bin/env python3
""" PunterPal backend control """

from gevent import monkey

# Must apply monkey patches before requests is imported.
# Can disable this for easier debugging
monkey.patch_all()
# pylint: disable=wrong-import-position,wrong-import-order
import requests

from datetime import datetime
import logging
import json
import sys
from typing import Union
from pathlib import Path

import arguably
from pydantic import ValidationError

from api.config import REDIS_HOST, REDIS_PORT
from evaluator import Evaluator
from matcher import Matcher
from matcher.store import FileSchemaStore, RedisSchemaStore
from parsers import (
    DabbleParser,
    SportsbetParser,
    UnibetParser,
    BetfairParser,
    LadbrokesParser,
    PointsbetParser,
    PalmerbetParser,
    BluebetParser,
)
from scrapers import (
    DabbleScraper,
    DabbleScraperResult,
    SportsbetScraper,
    SportsbetScraperResult,
    UnibetScraper,
    UnibetScraperResult,
    BetfairScraper,
    BetfairScraperResult,
    LadbrokesScraper,
    LadbrokesScraperResult,
    PointsbetScraper,
    PointsbetScraperResult,
    PalmerbetScraper,
    PalmerbetScraperResult,
    BluebetScraper,
    BluebetScraperResult,
)


logging.basicConfig(level=logging.INFO)

LOG = logging.getLogger(__name__)

SCRAPERS_PARSERS = {
    "betfair": (BetfairScraper, BetfairParser, BetfairScraperResult),
    "dabble": (DabbleScraper, DabbleParser, DabbleScraperResult),
    "sportsbet": (SportsbetScraper, SportsbetParser, SportsbetScraperResult),
    "unibet": (UnibetScraper, UnibetParser, UnibetScraperResult),
    "ladbrokes": (LadbrokesScraper, LadbrokesParser, LadbrokesScraperResult),
    "pointsbet": (PointsbetScraper, PointsbetParser, PointsbetScraperResult),
    "palmerbet": (PalmerbetScraper, PalmerbetParser, PalmerbetScraperResult),
    "bluebet": (BluebetScraper, BluebetParser, BluebetScraperResult),
}


@arguably.command
def scrape(
    agency: str,
    *,
    dump_scraped: bool = False,
    dump_parsed: bool = False,
    replay: Union[str, None] = None,
) -> None:
    """Scrape data from an agency, parse it and update markets.

    Args:
        agency: The agency name to scrape.
        dump_scraped: Dump scraped data to dumps/[AGENCY]_scraped.json
        dump_parsed: Dump parsed data to dumps/[AGENCY]_parsed.json
        replay: Replay scraped data from a --dump-scraped file at the given path.
    """
    started = datetime.now()
    agency = agency.lower()

    if agency not in SCRAPERS_PARSERS:
        LOG.error(
            f"Unknown agency '{agency}'. Supported values are: "
            ", ".join(SCRAPERS_PARSERS.keys())
        )

        return 1

    if replay and dump_scraped:
        LOG.error("Options replay and dump-scraped are mutually exclusive!")

        return 2

    scraper, parser, resultCls = SCRAPERS_PARSERS[agency]
    scraper, parser = scraper(), parser()

    if replay:
        LOG.info(f"Replaying scraped {parser.agencyName} data from {replay}")
        with open(replay, "r") as file:
            scrapedData = [resultCls(**data) for data in json.load(file)]

    else:
        LOG.info(f"Scraping from {parser.agencyName}")
        scrapedData = list(scraper.fetch())

    if dump_scraped:
        dumpPath = f"dumps/{parser.agencyName}_scraped.json"
        LOG.info(f"Dumping scraped data for {parser.agencyName} to '{dumpPath}'")

        with open(dumpPath, "w") as file:
            json.dump(
                [x.model_dump(mode="json") for x in scrapedData],
                file,
                indent=4,
                separators=(", ", ": "),
            )

    parsedResults = parser.parse(scrapedData)

    if dump_parsed:
        dumpPath = f"dumps/{parser.agencyName}_parsed.json"
        LOG.info(f"Dumping parsed data for {parser.agencyName} to '{dumpPath}'")

        with open(dumpPath, "w") as file:
            json.dump(
                parsedResults.model_dump(mode="json"),
                file,
                indent=4,
                separators=(", ", ": "),
            )

    LOG.info("Loading schema")
    matcher = Matcher(RedisSchemaStore(host=REDIS_HOST, port=REDIS_PORT))

    try:
        matcher.load()

    except ValidationError:
        LOG.exception("Failed to read schema (failed to validate)")

        return 2

    if matcher.tree is None or matcher.tree.baseAgency == parser.agencyName:
        LOG.info("Updating schema")
        matcher.updateSchema(parsedResults)

    LOG.info("Cleaning schema...")
    matcher.clean()

    LOG.info("Updating markets")
    matcher.updateMarkets(parsedResults)

    LOG.info("Saving schema")
    matcher.save()

    LOG.info(f"Finished after {(datetime.now() - started).total_seconds():.0f}s.")

    return 0


@arguably.command()
def evaluate(
    *,
    sportKey: str = None,
    compKey: str = None,
    agencies: str = None,
    outfile: str = None,
) -> None:
    """Evaluate arbitrage opportunities.

    Args:
        sportKey: if provided, limit scope to the given sport key.
        compKey: if provided, limit scope to the given competition key.
                 Usage requires that sportKey is also provided.
        agencies: a comma-separated list of agency keys. If provided, all results must
                  feature the specified agencies.
        outfile: path to write results to, in CSV format. If not provided, prints to
                 stdout.
    """
    # WARNING: results will be blank if an agency key is incorrect.
    if agencies:
        agencies = list(map(lambda a: a.strip(), agencies.split(",")))

    sportKey = sportKey.strip() if sportKey else None
    compKey = compKey.strip() if compKey else None

    if "" in (sportKey, compKey):
        LOG.error("Invalid sportKey or compKey!")

    LOG.info("Loading schema")
    matcher = Matcher(RedisSchemaStore(host=REDIS_HOST, port=REDIS_PORT))

    try:
        matcher.load()

    except ValidationError:
        LOG.exception("Failed to read schema (no data)")

        return 2

    LOG.info(f"Evaluating sportKey={sportKey} compKey={compKey} agencies={agencies}")
    evaluator = Evaluator()
    df = evaluator.evaluate(
        matcher, sportKey=sportKey, compKey=compKey, agencies=agencies
    )

    if outfile is not None:
        LOG.info(f"Saving results to {outfile}")
        evaluator.toCSV(df, outfile)

    else:
        LOG.info("Printing results to stdout")
        print(evaluator.toCSV(df))

    return 0


@arguably.command()
def read_schema(schema_file: str = "schema.json") -> None:
    """Read schema and save to file."""
    assert schema_file

    fileSchema = FileSchemaStore(schema_file)
    redisSchema = RedisSchemaStore(host=REDIS_HOST, port=REDIS_PORT)

    fileSchema.save(redisSchema.load())


@arguably.command()
def write_schema(schema_file: str = "schema.json") -> None:
    """Write schema file to redis."""
    assert schema_file

    fileSchema = FileSchemaStore(schema_file)
    redisSchema = RedisSchemaStore(host=REDIS_HOST, port=REDIS_PORT)

    redisSchema.save(fileSchema.load())


@arguably.command()
def clean_schema() -> None:
    """Perform cleanup."""
    matcher = Matcher(RedisSchemaStore(host=REDIS_HOST, port=REDIS_PORT))
    matcher.load()
    matcher.clean()
    matcher.save()


if __name__ == "__main__":
    sys.exit(arguably.run())
