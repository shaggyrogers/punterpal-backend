#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
  test_bucket.py
  ============

  Description:           Unit tests for Bucket.
  Author:                Michael De Pasquale
  Creation Date:         2018-05-25
  Modification Date:     2025-03-09

"""

import logging
import time

import gevent
import pytest

from ..bucket import Bucket


@pytest.mark.parametrize(
    "capacity,refillTime,threadCnt,delay,target",
    [
        (5, 5, 5, 0, 5),
        (3, 1, 9, 0, 3),
        (1, 1, 4, 0, 4),
        # Test behaviour when allowed to fill
        (4, 2, 8, 2, 2),
    ],
)
def test_leak(
    capacity: int, refillTime: float, threadCnt: int, delay: float, target: float
) -> None:
    """Test rate limiting works"""
    b = Bucket(
        gevent.sleep, capacity=capacity, refillTime=refillTime, log=logging.getLogger()
    )

    gevent.sleep(delay)
    startTime = time.monotonic()
    gevent.wait([gevent.spawn(b.leak) for i in range(0, threadCnt)])

    assert target - 0.5 <= time.monotonic() - startTime <= target + 0.5
