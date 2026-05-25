#!/usr/bin/env python3
"""
  session.py
  ==========

  Description:           Wrapper for requests.Session which adds rate limiting.
  Author:                Michael De Pasquale
  Creation Date:         2025-03-09
  Modification Date:     2026-05-25

"""

from functools import partial
from typing import Union

import requests

from .bucket import Bucket

# TODO: Retries would be nice to have

REQUEST_METHODS = {
    "delete",
    "get",
    "head",
    "options",
    "patch",
    "post",
    "put",
    "request",
}


class RateLimitSession:
    __slots__ = (
        "_session",
        "_bucket",
        "_timeout",
    ) + tuple(REQUEST_METHODS)

    def __init__(self, *args, timeout: Union[float, None] = None, **kwargs) -> None:
        """Create a wrapped Session. Positional and keyword arguments other than those
        explicitly listed are passed to Bucket().

        Parameters
        ----------
        timeout: float or tuple, optional
          Timeout in seconds, or tuple of form (connect_timeout, read_timeout). Default
          is no timeout.
        """
        assert timeout is None or timeout >= 0

        self._session = requests.Session()
        self._bucket = Bucket(*args, **kwargs)
        self._timeout = timeout

        for m in REQUEST_METHODS:
            setattr(self, m, partial(self._callRateLimited, m))

    # Wrapper method - intercepts request(), get() etc and adds rate limiting
    def _callRateLimited(self, name: str, *args, **kwargs) -> requests.Response:
        """Wait for bucket to leak, then call the specified function on _session."""
        self._bucket.leak()

        if self._timeout and "timeout" not in kwargs:
            kwargs["timeout"] = self._timeout

        return getattr(self._session, name)(*args, **kwargs)

    # Context manager methods
    def __enter__(self) -> requests.Session:
        self._session.__enter__()

        return self

    def __exit__(self, *args) -> None:
        self._session.__exit__(*args)

    # Attribute access/modification falls through to _session
    # __getattr__ is only called if normal attribute access fails, __setattr__ is always called.
    def __getattr__(self, name: str) -> object:
        return getattr(self._session, name)

    def __setattr__(self, name: str, value: object) -> None:
        if name in self.__class__.__slots__:
            return super().__setattr__(name, value)

        return setattr(self._session, name, value)
