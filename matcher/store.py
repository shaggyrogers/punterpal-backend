#!/usr/bin/env python3
"""
  store.py
  ========

  Description:           Manage schema read/writes
  Author:                Michael De Pasquale
  Creation Date:         2025-02-11
  Modification Date:     2025-03-23

"""

import redis

from matcher.types import CanonTree

# FIXME: This is not ideal.. have to update entire tree at once, and make sure only
# one update operation happens at any time to prevent overwriting changes


class SchemaStore:
    """Interface"""

    def save(self, tree: CanonTree, *args, **kwargs) -> None:
        """Write tree."""
        raise NotImplementedError()

    def load(self, *args, **kwargs) -> CanonTree:
        """Read tree."""
        raise NotImplementedError()


class FileSchemaStore:
    """Storage using a file."""

    def __init__(self, path: str) -> None:
        self._path = path

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(path="{self._path}")'

    def save(self, tree: CanonTree) -> None:
        tree.save(self._path)

    def load(self) -> CanonTree:
        return CanonTree.load(self._path)


class RedisSchemaStore:
    """Storage using a JSON blob in Redis."""

    def __init__(self, **kwargs) -> None:
        assert "decode_responses" not in kwargs
        self._kwargs = kwargs
        self._connection = redis.Redis(decode_responses=True, **kwargs)

        # Ensure connection
        assert self._connection.ping()

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(kwargs="{self._kwargs}")'

    @property
    def key(self) -> str:
        return "tree"

    def save(self, tree: CanonTree) -> None:
        self._connection.set(self.key, tree.toJSON())

    def load(self) -> CanonTree:
        return CanonTree.fromJSON(self._connection.get(self.key))
