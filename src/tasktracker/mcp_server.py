#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The MCP server: the tools Claude calls to read and write the board.

The hook beside this module mirrors Claude Code's own todo list, which covers
the common case with no tool call at all. These tools are for the two things a
mirror cannot do: putting work on the board that is NOT part of the current
session's plan - "do this next time" - and reading the queue back at the start
of a session, when the todo list is empty and the only record of what was left
over is this board.

Every tool resolves its project the same way: the argument if one was given,
otherwise the directory this process was started in, walked up to its
repository root. So a session in ~/src/app files against `app` without ever
naming it.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import store

# What the server tells Claude about itself, once, at connection.
#
# It says when NOT to call these as clearly as when to: the todo list is already
# mirrored, so a session that also files every one of its own todos through
# `task_add` doubles every card on the board.
INSTRUCTIONS = """
TaskTracker keeps a per-project task board that outlives a session.

Claude Code's own todo list is mirrored onto this board automatically - do not
re-file the todos you are already tracking with TodoWrite.

Use these tools for what the todo list cannot hold:
  * `tasks_queued` at the start of work on a project, to pick up what a previous
    session left behind.
  * `task_add` for work that is worth doing but is not part of what you are
    doing now - a follow-up, something noticed in passing, something the user
    said to do later.
  * `task_done` when you finish something that was queued by an earlier session.

Task ids are stable. Titles are one line; anything longer belongs in `detail`.
""".strip()

server: FastMCP = FastMCP("tasktracker", instructions=INSTRUCTIONS)

# Where a tool files a task when it was not told. Set by the plugin so that a
# server started somewhere other than the project - a wrapper script, a
# launcher, a shell that happened to be in ~ - still files against the work in
# hand rather than against the home directory.
PROJECT_ENV = "TASKTRACKER_PROJECT"


def default_root() -> str:
    """The project directory for a tool that named none.

    The variable is only believed when it names a directory that exists. The
    plugin sets it from `${CLAUDE_PROJECT_DIR}`, and a client that does not
    expand that hands this process the literal string - which would otherwise
    become a project named `${CLAUDE_PROJECT_DIR}`, sitting at the top of the
    panel with everything filed under it. The working directory is what the
    client started this server in, and it is right whenever the variable is
    not.
    """
    named = os.environ.get(PROJECT_ENV, "").strip()
    if named and os.path.isdir(named):
        return named
    return os.getcwd()

# What a task looks like on the way back to Claude.
#
# Eleven columns go into the table and five come out here. The rest - the float
# position, the session that wrote it, the created stamp - are the board's
# bookkeeping, and a list of thirty tasks carrying all of it is a page of
# context spent saying nothing Claude can act on.
BRIEF_FIELDS = ("id", "title", "status", "detail", "source")


def brief(task: dict[str, Any]) -> dict[str, Any]:
    trimmed = {name: task[name] for name in BRIEF_FIELDS if name in task}
    # An empty detail is noise on every card that has none.
    if not trimmed.get("detail"):
        trimmed.pop("detail", None)
    return trimmed


def resolve(conn, wanted: str) -> dict[str, Any]:
    """The project a tool acts on: what it was told, or where it is running.

    A name that matches no project is NOT created. Creating one would file the
    task under a board nobody will look at - the operator typed a name they
    expected to already exist, and the honest answer is that it does not, with
    the ones that do listed beside it.

    A path is different: `ensure_project` on a path is how a board gets its
    first project at all, and a path is unambiguous in a way a name is not.
    """
    text = (wanted or "").strip()
    if not text:
        return store.ensure_project(conn, default_root())
    if "/" in text or text.isdigit():
        try:
            return store.find_project(conn, text)
        except store.NotFound:
            if text.isdigit():
                raise
            return store.ensure_project(conn, text)
    return store.find_project(conn, text)


@server.tool()
def tasks_queued(project: str = "") -> dict[str, Any]:
    """What is waiting and what is in flight on a project's board.

    Call this when you start work on a project: it is the record of what earlier
    sessions left behind, which nothing in the current session's context knows
    about. Finished tasks are not listed - ask `tasks_all` for those.

    project: a name, a path, or an id. Omit it for the project you are in.
    """
    with store.database() as conn:
        found = resolve(conn, project)
        rows = store.tasks(conn, found["id"], statuses=(store.QUEUED, store.IN_PROGRESS))
        return {
            "project": found["name"],
            "queued": [brief(row) for row in rows if row["status"] == store.QUEUED],
            "in_progress": [brief(row) for row in rows if row["status"] == store.IN_PROGRESS],
        }


@server.tool()
def tasks_all(project: str = "", include_hidden: bool = False) -> dict[str, Any]:
    """Every task on a project's board, finished ones included.

    include_hidden: also return finished tasks old enough that the panel has
    stopped drawing them. Off by default, because that is a list that only grows
    and is almost never what the question was about.
    """
    with store.database() as conn:
        found = resolve(conn, project)
        rows = store.tasks(conn, found["id"], hide_done=not include_hidden)
        return {"project": found["name"], "tasks": [brief(row) for row in rows]}


@server.tool()
def task_add(
    title: str, detail: str = "", project: str = "", start: bool = False
) -> dict[str, Any]:
    """Put a task on a project's board.

    For work worth doing that is not part of what you are doing right now - a
    follow-up, something noticed in passing, something to pick up next session.
    Do NOT use it to re-file the todos you are already tracking with TodoWrite:
    those are mirrored onto the board already, and filing them twice puts every
    one of them on it twice.

    title: one line. Anything longer belongs in `detail`.
    start: file it as already in progress rather than as queued.
    """
    with store.database() as conn:
        found = resolve(conn, project)
        task = store.create_task(
            conn,
            found["id"],
            title=title,
            detail=detail,
            status=store.IN_PROGRESS if start else store.QUEUED,
            source=store.SOURCE_MCP,
        )
        return {"project": found["name"], "task": brief(task)}


@server.tool()
def task_start(task_id: int) -> dict[str, Any]:
    """Move a task into the in-progress column."""
    with store.database() as conn:
        return {"task": brief(store.update_task(conn, task_id, status=store.IN_PROGRESS))}


@server.tool()
def task_done(task_id: int) -> dict[str, Any]:
    """Mark a task finished.

    The card stays on the board until the age set on the settings screen, and is
    never deleted by this.
    """
    with store.database() as conn:
        return {"task": brief(store.update_task(conn, task_id, status=store.DONE))}


@server.tool()
def task_update(
    task_id: int, title: str = "", detail: str = "", status: str = ""
) -> dict[str, Any]:
    """Edit a task. Every field is optional; an empty one is left as it was.

    status: queued, in_progress or done.
    """
    with store.database() as conn:
        return {
            "task": brief(
                store.update_task(
                    conn,
                    task_id,
                    title=title or None,
                    detail=detail or None,
                    status=status or None,
                )
            )
        }


@server.tool()
def task_delete(task_id: int) -> dict[str, Any]:
    """Remove a task from the board for good.

    Finishing a task is `task_done`. This is for a card that should never have
    been there - a duplicate, or something filed against the wrong project.
    """
    with store.database() as conn:
        store.delete_task(conn, task_id)
        return {"deleted": task_id}


@server.tool()
def projects_list() -> dict[str, Any]:
    """Every project on the board, most recently touched first, with its counts.

    Use it when a task belongs to a project other than the one you are in and
    you need the name the board knows it by.
    """
    with store.database() as conn:
        return {
            "projects": [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "path": row["path"],
                    "queued": row["queued"],
                    "in_progress": row["in_progress"],
                }
                for row in store.projects(conn)
            ]
        }


def main() -> int:
    """Speak MCP over stdio until the client hangs up.

    Nothing is printed to stdout anywhere in this package's import path, and it
    matters here more than anywhere else: stdout IS the protocol, and one stray
    print is a client that reports the server as malformed with no clue as to
    which line did it.
    """
    server.run(transport="stdio")
    return 0
