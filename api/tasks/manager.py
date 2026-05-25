#!/usr/bin/env python3
"""
  manager.py
  ==========

  Description:           Records task metadata.
  Author:                Michael De Pasquale
  Creation Date:         2025-02-13
  Modification Date:     2025-04-21

"""

import json
from typing import Callable, Union

from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session, undefer

from .models import Base, Task

# Default sqlite database file path
SQLITE_PATH = "sqlite:///tasks.db"


class TaskManager:

    def __init__(self, path: str = SQLITE_PATH) -> None:
        self._engine = create_engine(path, echo=True)
        Base.metadata.create_all(self._engine)

    def addTask(
        self, name: str, startFn: Callable[[], str], args: tuple, kwargs: dict
    ) -> Task:
        """Start and add a task.

        Parameters
        ----------
        name : str
          Task name.

        startFn: function() -> str
          Callable which starts the task and returns the corresponding message UUID

        args/kwargs : tuple/dict
          Positional and keyword arguments which were passed to the task.
        """

        assert name
        assert startFn is not None

        with Session(self._engine) as session:
            uuid = startFn()
            assert uuid

            task = Task(
                name=name,
                uuid=uuid,
                args=json.dumps(list(args)),
                kwargs=json.dumps(kwargs),
            )

            session.add(task)
            session.commit()

            assert task.id is not None

        return task

    def updateTask(self, taskId: int = None, uuid: str = None, **kwargs) -> None:
        # Identify by either taskId or message uuid, not both
        if (taskId is None) == (not uuid):
            raise ValueError("One and only one of taskId and uuid must be provided.")

        with Session(self._engine) as session:
            if taskId:
                task = session.get(Task, taskId)

            else:
                task = session.scalar(select(Task).where(Task.uuid == uuid))

            for k, v in kwargs.items():
                setattr(task, k, v)

            session.commit()

    def getTasks(self) -> list[Task]:
        """Get tasks in descending order (most recent first)"""
        # TODO: Pagination, filtering
        with Session(self._engine) as session:
            tasks = list(session.scalars(select(Task).order_by(Task.id.desc())))

        return tasks

    def getTask(
        self, taskId: Union[int, None] = None, uuid: Union[str, None] = None
    ) -> Task:
        """Get a task by either ID or message UUID. Loads deferred columns."""
        if (taskId is None) == (not uuid):
            raise ValueError("One and only one of taskId and uuid must be provided.")

        with Session(self._engine) as session:
            return session.scalar(
                select(Task)
                .where((Task.id == taskId) if taskId else (Task.uuid == uuid))
                .options(undefer("*"))
            )

    def clear(self, finishedOnly: bool = True) -> None:
        """Delete tasks.

        Parameters
        ----------
        finishedOnly : bool, default True
          If True, delete only finished tasks, otherwise delete all tasks.
        """
        with Session(self._engine) as session:
            exp = delete(Task)

            if finishedOnly:
                exp = exp.where(Task.finishedTime != None)

            session.execute(exp)
            session.commit()
