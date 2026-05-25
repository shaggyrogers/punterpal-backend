#!/usr/bin/env python3
"""
  app.py
  ======

  Description:           Endpoints for tasks API
  Author:                Michael De Pasquale
  Creation Date:         2025-02-13
  Modification Date:     2025-04-21

"""

from flask import Blueprint, request

from api_types import (
    TaskInfo,
    TaskExtendedInfoResponse,
    TaskListResponse,
    TaskRunResponse,
    ScraperListResponse,
)

import parsers
from .manager import TaskManager
from .scrape import scrape

TASKS = Blueprint("tasks", __name__)
TASK_MANAGER = TaskManager()


@TASKS.route("/")
@TASKS.route("/list")
def task_list() -> None:
    """Get task list."""
    return TaskListResponse(
        tasks=[TaskInfo.fromModel(t) for t in TASK_MANAGER.getTasks()]
    ).model_dump(mode="json")


@TASKS.route("/")
@TASKS.route("/clear_finished")
def task_clear_finished() -> None:
    """Clear all finished tasks."""
    TASK_MANAGER.clearFinishedTasks()

    return {"success": True}


@TASKS.route("/info/<taskId>")
def task_info(taskId: int) -> None:
    """Get extended task info by ID."""
    task = TASK_MANAGER.getTask(taskId)

    if not task:
        return {"success": False, "error": f"Task {taskId} does not exist"}, 404

    return TaskExtendedInfoResponse.fromModel(task).model_dump(mode="json")


@TASKS.route("/scraper_list")
def get_scrapers() -> None:
    """Get list of scrapers."""
    # HACK: get names from parser classes
    return ScraperListResponse(
        scrapers=[x.replace("Parser", "") for x in dir(parsers) if x[0].isupper()]
    ).model_dump(mode="json")


@TASKS.route("/scrape/<agency>", methods=["GET", ""])
def scrape_task_runner(agency: str) -> None:
    """Queue a scrape/update task."""

    # Create entry for task
    task = TASK_MANAGER.addTask(
        "scrape",
        lambda: scrape.send(agency=agency).message_id,
        (agency,),
        {},
    )

    return TaskRunResponse.fromModel(task).model_dump(mode="json")


@TASKS.route("/update", methods=["POST"])
def update() -> None:
    """Update task details. Should be used by task processes only."""
    # TODO: use body for stdout
    params = request.get_json()
    assert "taskId" in params or "uuid" in params
    TASK_MANAGER.updateTask(**params)

    return {"success": True}
