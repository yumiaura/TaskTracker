#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The REST API the panel reads and writes.

Every response is JSON, every timestamp is a unix epoch float, and every
failure is `{"error": {"message": …}}` - one shape, so the browser has one
place that turns a failure into a sentence rather than seven screens each
rendering a different envelope.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import config, store

router = APIRouter(prefix="/api")


def connection() -> Iterator[sqlite3.Connection]:
    """One connection per request, closed when it is answered.

    A pool would be the usual answer and is the wrong one here: the panel polls
    a loopback bind a few times a minute, SQLite opens in microseconds, and a
    connection held across requests is a connection holding a WAL read snapshot
    while a hook in another process is trying to write.

    Opened with sqlite3's same-thread check off, because FastAPI runs this
    dependency and the handler that uses it on threads of its pool, and they are
    not always the same thread. With the check on, every request that landed on
    two threads failed with "SQLite objects created in a thread can only be used
    in that same thread" - a 500 on some of the panel's polls and not others,
    more often the more of them ran at once. The connection is still one
    request's alone and is used by one thread at a time; it is only created on
    one and used on the next.
    """
    conn = store.connect(check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


# The connection, as a type. FastAPI reads the dependency out of the annotation
# rather than out of a default value - which is also what keeps `Depends(...)`
# from being evaluated once at import and shared by every handler that named it
# as a default.
Conn = Annotated[sqlite3.Connection, Depends(connection)]


def fail(status: int, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": {"message": message}})


class TaskCreate(BaseModel):
    title: str
    detail: str = ""
    status: str = store.QUEUED


class TaskPatch(BaseModel):
    """Every field optional, and `None` meaning "leave it alone".

    Which is why `detail` cannot be cleared by omitting it - clearing it is
    sending an empty string. A PATCH that treated a missing field as an empty
    one would wipe the detail of every card the board edits, because the panel
    sends only what the operator changed.
    """

    title: str | None = None
    detail: str | None = None
    status: str | None = None


class TaskMove(BaseModel):
    status: str
    index: int = Field(default=0, ge=0)


class SettingsPatch(BaseModel):
    # Capped at ten years rather than left open. The value becomes a cutoff
    # timestamp, and a span long enough to put that before the epoch is a board
    # that hides everything for a reason nobody can see on the settings screen.
    done_hide_days: int = Field(ge=0, le=3650)


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "database": str(config.db_path())}


@router.get("/settings")
def read_settings(conn: Conn) -> dict[str, Any]:
    return store.settings(conn)


@router.put("/settings")
def write_settings(body: SettingsPatch, conn: Conn) -> dict[str, Any]:
    store.set_setting(conn, "done_hide_days", str(body.done_hide_days))
    return store.settings(conn)


@router.get("/projects")
def list_projects(conn: Conn) -> dict[str, Any]:
    return {"projects": store.projects(conn)}


@router.get("/projects/{project_id}")
def read_project(
    project_id: int,
    conn: Conn,
    hide_done: bool = True,
) -> dict[str, Any]:
    """One project and its cards, in one answer.

    The board needs both on every poll and they have to be consistent with each
    other: fetched separately, a card created between the two requests arrives
    in a list whose project row says a different count, and the screen shows a
    column of four under a heading that says three.
    """
    try:
        found = store.project(conn, project_id)
    except store.NotFound as exc:
        raise fail(404, str(exc)) from exc
    return {
        "project": found,
        "tasks": store.tasks(conn, project_id, hide_done=hide_done),
        "settings": store.settings(conn),
    }


@router.delete("/projects/{project_id}")
def remove_project(project_id: int, conn: Conn) -> dict[str, Any]:
    try:
        store.delete_project(conn, project_id)
    except store.NotFound as exc:
        raise fail(404, str(exc)) from exc
    return {"deleted": project_id}


@router.post("/projects/{project_id}/tasks", status_code=201)
def add_task(project_id: int, body: TaskCreate, conn: Conn) -> dict[str, Any]:
    try:
        store.project(conn, project_id)
        return store.create_task(
            conn,
            project_id,
            title=body.title,
            detail=body.detail,
            status=body.status,
            source=store.SOURCE_MANUAL,
        )
    except store.NotFound as exc:
        raise fail(404, str(exc)) from exc
    except ValueError as exc:
        raise fail(400, str(exc)) from exc


@router.patch("/tasks/{task_id}")
def edit_task(task_id: int, body: TaskPatch, conn: Conn) -> dict[str, Any]:
    try:
        return store.update_task(
            conn, task_id, title=body.title, detail=body.detail, status=body.status
        )
    except store.NotFound as exc:
        raise fail(404, str(exc)) from exc
    except ValueError as exc:
        raise fail(400, str(exc)) from exc


@router.post("/tasks/{task_id}/move")
def move(task_id: int, body: TaskMove, conn: Conn) -> dict[str, Any]:
    try:
        return store.move_task(conn, task_id, body.status, body.index)
    except store.NotFound as exc:
        raise fail(404, str(exc)) from exc
    except ValueError as exc:
        raise fail(400, str(exc)) from exc


@router.delete("/tasks/{task_id}")
def remove_task(task_id: int, conn: Conn) -> dict[str, Any]:
    try:
        store.delete_task(conn, task_id)
    except store.NotFound as exc:
        raise fail(404, str(exc)) from exc
    return {"deleted": task_id}
