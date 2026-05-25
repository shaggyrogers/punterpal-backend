#!/usr/bin/env python3
"""
  test_manager.py
  ===============

  Description:           Tests for TaskManager
  Author:                Michael De Pasquale
  Creation Date:         2025-04-21
  Modification Date:     2025-04-21

"""

from pathlib import Path

import pytest

from api.tasks.manager import TaskManager


def test_manager() -> None:
    mgr = TaskManager("sqlite:///tasks_test.db")
    mgr.clear(finishedOnly=False)

    assert len(mgr.getTasks()) == 0

    # Add tasks
    addedTask = mgr.addTask(
        "Test",
        lambda: "test_message_id",
        ("arg1", "arg2"),
        {"kwarg1": False},
    )
    assert len(mgr.getTasks()) == 1

    # Check task was added correctly and we can retrieve it both with ID and message UUID
    for task in (mgr.getTask(taskId=addedTask.id), mgr.getTask(uuid="test_message_id")):
        assert task.uuid == "test_message_id"
        assert task.args.replace(" ", "") == '["arg1","arg2"]'
        assert task.kwargs.replace(" ", "") == '{"kwarg1":false}'
        assert task.name == "Test"

    # Update task - by ID, started property
    mgr.updateTask(taskId=addedTask.id, started=True)
    assert mgr.getTask(taskId=addedTask.id).started

    # Don't clear if not finished
    mgr.clear(finishedOnly=True)
    assert mgr.getTasks()

    # Update task - by message UUID, finished property
    mgr.updateTask(uuid=addedTask.uuid, finished=True)
    assert mgr.getTask(uuid=addedTask.uuid).finished

    # Clear, now that it is finished
    mgr.clear(finishedOnly=True)
    assert not mgr.getTasks()

    # Remove database file
    Path("./tasks_test.db").unlink()
