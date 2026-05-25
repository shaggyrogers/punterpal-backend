#!/usr/bin/env python3
"""
  models.py
  =========

  Description:           TODO
  Author:                Michael De Pasquale
  Creation Date:         2025-02-14
  Modification Date:     2025-04-21

"""

from datetime import datetime, timezone
from typing import Union

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, validates
from sqlalchemy.ext.hybrid import hybrid_property


class Base(DeclarativeBase):
    pass


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Message UUID.
    uuid: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, index=True
    )

    # Task name
    name: Mapped[str] = mapped_column(nullable=False)

    # Keyword and positional arguments, serialised
    args: Mapped[str] = mapped_column(nullable=False)
    kwargs: Mapped[str] = mapped_column(nullable=False)

    # None until the task finishes, then True if successful, False otherwise.
    success: Mapped[bool] = mapped_column(nullable=True, default=None)

    # Exception or error message. None if successful or not finished.
    errorInfo: Mapped[str] = mapped_column(nullable=True, default=None)

    _addedTime: Mapped[datetime] = mapped_column(
        nullable=True, default=lambda: datetime.now(timezone.utc)
    )
    _startedTime: Mapped[datetime] = mapped_column(nullable=True, default=None)
    _finishedTime: Mapped[datetime] = mapped_column(nullable=True, default=None)

    stdout: Mapped[str] = mapped_column(
        deferred=True, nullable=True, deferred_group="stdout_stderr"
    )
    stderr: Mapped[str] = mapped_column(
        deferred=True, nullable=True, deferred_group="stdout_stderr"
    )

    # These avoid need to serialise start/finish times when updating
    @property
    def started(self) -> bool:
        """True if the task has started running, False otherwise."""
        return self.startedTime is not None

    @started.setter
    def started(self, val: bool) -> None:
        """Update start time."""
        if val is not True:
            raise ValueError(f"started may only be set to True. (got {val})")

        if self.startedTime is not None:
            return

        self.startedTime = datetime.now(timezone.utc)

    @property
    def finished(self) -> bool:
        """True if the task has finished running, False otherwise."""
        return self.finishedTime is not None

    @finished.setter
    def finished(self, val: bool) -> None:
        """Update finish time."""
        if val is not True:
            raise ValueError(f"finished may only be set to True. (got {val})")

        if self.finishedTime is not None:
            return

        self.finishedTime = datetime.now(timezone.utc)

    # For SQLite, SQLAlchemy converts to UTC and drops timezone info.
    # These add timezone back in on access without otherwise changing behaviour.
    @hybrid_property
    def addedTime(self) -> datetime:
        return self._addedTime.replace(tzinfo=timezone.utc)

    @addedTime.setter
    def addedTime(self, val: datetime) -> datetime:
        self._addedTime = val

    # pylint: disable=no-self-argument
    @addedTime.expression
    def addedTime(cls) -> object:
        return cls._addedTime

    @hybrid_property
    def startedTime(self) -> Union[datetime, None]:
        if not self._startedTime:
            return None

        return self._startedTime.replace(tzinfo=timezone.utc)

    @startedTime.setter
    def startedTime(self, val: Union[datetime, None]) -> datetime:
        self._startedTime = val

    @startedTime.expression
    def startedTime(cls) -> object:
        return cls._startedTime

    @hybrid_property
    def finishedTime(self) -> Union[datetime, None]:
        if not self._finishedTime:
            return None

        return self._finishedTime.replace(tzinfo=timezone.utc)

    @finishedTime.setter
    def finishedTime(self, val: Union[datetime, None]) -> datetime:
        self._finishedTime = val

    @finishedTime.expression
    def finishedTime(cls) -> object:
        return cls._finishedTime

    def __repr__(self) -> str:
        return (
            f"Task(id={self.id}, name='{self.name}', started={self.started},"
            f" finished={self.finished}, success={self.success})"
        )
