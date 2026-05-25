"""
  scrapers package
  ================

  Description:           Classes handling scraping (only)
  Author:                Michael De Pasquale
  Creation Date:         2024-12-15
  Modification Date:     2025-04-04

"""

from .betfair import BetfairScraper, BetfairScraperResult
from .dabble import DabbleScraper, DabbleScraperResult
from .ladbrokes import LadbrokesScraper, LadbrokesScraperResult
from .sportsbet import SportsbetScraper, SportsbetScraperResult
from .unibet import UnibetScraper, UnibetScraperResult
from .pointsbet import PointsbetScraper, PointsbetScraperResult
from .palmerbet import PalmerbetScraper, PalmerbetScraperResult
from .bluebet import BluebetScraper, BluebetScraperResult
