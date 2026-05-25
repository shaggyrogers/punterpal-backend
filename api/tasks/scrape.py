#!/usr/bin/env python3
"""
  scrape.py
  =========

  Description:           Defines the 'scrape' task
  Author:                Michael De Pasquale
  Creation Date:         2025-02-13
  Modification Date:     2025-04-21

"""


from datetime import datetime, timezone
import logging
import subprocess
import traceback

import dramatiq
from dramatiq.middleware import CurrentMessage, TimeLimitExceeded
import requests

from api.config import API_PORT

LOG = logging.getLogger(__name__)

# Install 'Current Message' broker
dramatiq.get_broker().add_middleware(CurrentMessage())


def _updateTaskReq(**kwargs) -> None:
    kwargs["uuid"] = CurrentMessage.get_current_message().message_id

    assert requests.post(
        f"http://localhost:{API_PORT}/tasks/update",
        json=kwargs,
        timeout=30,
    ).json()["success"]


@dramatiq.actor(
    max_retries=0,
    # These are in milliseconds (3 hours)
    max_age=10800000,
    time_limit=10800000,
)
def scrape(agency: str) -> None:
    """Run scraper/parser for given agency and update markets."""
    msg = CurrentMessage.get_current_message()
    print(f"Processing {msg} / {msg.message_id}")

    try:
        LOG.debug(f"Started scrape {agency}")

        _updateTaskReq(started=True)
        completedProcess = _scrapeInner(agency)

        # Repurpose "errorInfo" for any nonzero exit code
        errorInfo = (
            None
            if completedProcess.returncode == 0
            else str(completedProcess.returncode)
        )

        if errorInfo:
            LOG.error(f"_scrapeInner failed with code {errorInfo}")

        _updateTaskReq(
            success=errorInfo is None,
            errorInfo=errorInfo,
            stdout=None if not completedProcess else completedProcess.stdout,
            stderr=None if not completedProcess else completedProcess.stderr,
            finished=True,
        )

    except TimeLimitExceeded as ex:
        _updateTaskReq(
            success=False,
            started=True,
            errorInfo="".join(traceback.format_exception(ex)),
            finished=True,
        )


def _scrapeInner(agency: str) -> subprocess.CompletedProcess:
    # Just run backend scrape script... avoids duplication and solves issue
    # of limiting updates to 1 agency at a time while allowing multitasking
    if not agency.isalpha():
        raise ValueError(f"Bad agency: '{agency}'")

    # NOTE: Use of capture_output means stdout/stderr won't appear in terminal
    return subprocess.run(
        ["pipenv", "run", "python", "main.py", "scrape", agency],
        check=False,
        capture_output=True,
        encoding="UTF-8",
    )
