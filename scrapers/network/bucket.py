#!/usr/bin/env python3
"""
  bucket.py
  =========

  Description:           Handles rate limiting
  Author:                Michael De Pasquale <shaggyrogers>
  Creation Date:         2018-01-30
  Modification Date:     2025-03-09

"""

import time
import logging
from typing import Callable, Optional


class Bucket:
    """Implements a token bucket algorithm for rate limiting.

    Calling leak() consumes one token. Buckets start empty, with tokens
    refilled at a rate of 1 token per capacity/refillTime seconds.

    If no tokens are available, leak() will block until one becomes available
    by calling sleepFn().

    As tokens can be consumed at any rate, the short-term rate can exceed
    capacity/refillTime if the bucket is allowed to fill. For example, a full
    1/1 Bucket will permit 2 requests in a 1 second period.

    Usage
    -----

    For an average rate of 10 requests / minute:

        b = Bucket(sleep_function, 10, 60)
    """

    __slots__ = (
        "_amount",
        "_capacity",
        "_lastRefill",
        "_refillTime",
        "_sleepFn",
        "_logger",
    )

    def __init__(
        self,
        sleepFn: Callable[[float], None],
        capacity: int,
        refillTime: float,
        log: Optional[logging.Logger] = None,
    ):
        """Initialise a Bucket instance.

        Arguments
        ---------
        sleepFn: function(float) -> None
            Delegate thread sleep function, accepting time in seconds.

        capacity: int
            The maximum and initial number of 'tokens' in the bucket.

        refillTime: float
            The time (seconds) it takes to completely refill the bucket.

        log : logging.Logger, default None
            Enable logging if provided
        """
        assert sleepFn and capacity and refillTime
        assert capacity > 0 and refillTime > 0

        self._amount = 0.0
        self._capacity = capacity
        self._lastRefill = time.monotonic()
        self._refillTime = refillTime
        self._sleepFn = sleepFn
        self._logger = log

        self._log(f"Created {repr(self)}")

    # Interface
    def leak(self) -> None:
        """Attempt to remove one token. If necessary, calls sleepFn until
        a token is ready."""
        while not self._refill():
            fillOneTime = self._refillTime / self._capacity
            assert fillOneTime > 0

            sleepTime = min(
                fillOneTime - (time.monotonic() - self._lastRefill), fillOneTime
            )
            self._log(
                f"Waiting for {sleepTime:.4}s (amount = {self._amount:.4},"
                f" fillOneTime = {fillOneTime:.4}s)"
            )
            self._sleepFn(sleepTime)

        assert not self._empty
        self._amount -= 1
        self._log(f"Consumed 1 token, amount = {self._amount:.4}")

    # Internal methods
    def _log(self, *args, **kwargs) -> None:
        """Writes a debug message to the Logger instance, if supplied during
        instantiation.
        """
        if self._logger is not None:
            self._logger.debug(*args, **kwargs)

    def __repr__(self) -> str:
        """Returns a string representation for this instance."""
        return (
            f"{self.__class__.__name__}("
            + ", ".join(
                (
                    f"capacity={self._capacity}",
                    f"refillTime={self._refillTime}",
                    f"amount={self._amount}",
                )
            )
            + ")"
        )

    def __str__(self) -> str:
        return self.__repr__()

    @property
    def _empty(self) -> bool:
        """Return True if no tokens are available"""
        assert 0 <= self._amount <= self._capacity
        return self._amount < 1

    def _refill(self) -> bool:
        """Attempt to replenish tokens. Returns True if a token is available,
        False otherwise."""
        assert 0 <= self._amount <= self._capacity

        if self._amount < self._capacity:
            elapsed = time.monotonic() - self._lastRefill

            # Only update if enough time has passed for at least one token to be added
            if elapsed < self._refillTime / self._capacity:
                self._log(
                    "Not refilling bucket,"
                    f" {elapsed:.4}s < {self._refillTime / self._capacity:.4}s"
                )

                return not self._empty

            # Update token count, use partial tokens for accuracy
            toAdd = elapsed / self._refillTime * self._capacity
            newAmount = float(min(self._amount + toAdd, self._capacity))
            self._log(
                ", ".join(
                    [
                        "Refilling bucket",
                        f"elapsed = {elapsed:.4}s",
                        f"toAdd = {toAdd:.4}",
                        f"oldAmount = {self._amount:.4}",
                        f"newAmount = {newAmount:.4}",
                    ]
                )
            )
            self._amount = newAmount

        # Update refill time
        self._lastRefill = time.monotonic()

        return not self._empty
