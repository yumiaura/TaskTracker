#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The MCP server: the tools Claude calls to read and write the board.

The hook beside this module mirrors Claude Code's own todo list, which covers
the common case with no tool call at all. These tools are for the two things a
mirror cannot do: putting work on the board that is NOT part of the current
session's plan - "do this next time" - and reading the queue back at the start
of a session, when the todo list is empty and the only record of what was left
over is this board.

It is served two ways. The plugin reaches it over HTTP, inside the container
that also serves the panel (`http_manager`, mounted by the web app at /mcp).
`tasktracker mcp` still speaks it over stdio for a client started in the
project itself (`main`).

The difference that matters between the two is the project. Over stdio the
client starts this process in the directory it is working in, so a tool that
names no project can take the working directory. Over HTTP this process is the
web server - its working directory is the image's /app - so there a tool must be
told, and one that is not says so instead of guessing.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from . import store

# What the server tells Claude about itself, once, at connection.
#
# It says when NOT to call these as clearly as when to: the todo list is already
# mirrored, so a session that also files every one of its own todos through
# `task_add` doubles every card on the board.
INSTRUCTIONS = """
TaskTracker keeps a per-project task board that outlives a session.

Claude Code's own task list is mirrored onto this board automatically - do not
re-file the tasks you are already tracking with TaskCreate (or TodoWrite).

Pass `project` on every call: the absolute path of the directory you are
working in. The board may be running somewhere that cannot see where you are.

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

# Whether a tool that named no project may take the working directory as one.
#
# Off unless `main` turns it on, and only `main` does: under stdio the client
# started this process inside the project, and the working directory is the
# answer. Everywhere else it is not - over HTTP this process is the web server,
# and falling back to its working directory would file every task on the board
# under a project called `app`.
cwd_is_project = False


class MissingProject(ValueError):
    """A tool was called with no project and there is nothing to infer one from.

    Raised rather than guessed, and worded as the instruction the caller needs:
    the message reaches Claude as the tool's result, and Claude acts on what it
    reads there.
    """


def default_root() -> str:
    """The project directory for a tool that named none.

    The variable is only believed when it names a directory that exists: a
    client that does not expand a `${...}` in its config hands this process the
    literal string, which would otherwise become a project with that string for
    a name. The working directory is only believed under stdio, for the reason
    on `cwd_is_project`.
    """
    named = os.environ.get(PROJECT_ENV, "").strip()
    if named and os.path.isdir(named):
        return named
    if cwd_is_project:
        return os.getcwd()
    raise MissingProject(
        "No project given. Pass `project`: the absolute path of the directory you are working in."
    )


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

    project: the absolute path of the directory you are working in. A project
    name or id also works.
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

    project: the absolute path of the directory you are working in.
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
    Do NOT use it to re-file the tasks you are already tracking with TaskCreate
    or TodoWrite: those are mirrored onto the board already, and filing them
    twice puts every one of them on it twice.

    title: one line. Anything longer belongs in `detail`.
    project: the absolute path of the directory you are working in.
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


def http_manager() -> StreamableHTTPSessionManager:
    """A fresh HTTP session manager for these tools, for one web app to mount.

    Built here rather than taken from `server.streamable_http_app()`, because
    FastMCP keeps the one it builds for the life of the process and a manager
    can be run exactly once. One manager per app means every app - the one in
    the container, and each one a test builds - gets its own.

    Stateless, with plain JSON answers. There is nothing held between two calls
    that a session would carry, and a stateful session is one a container
    restart invalidates under a client that does not know to reconnect.

    `server._mcp_server` is the SDK's own attribute - FastMCP has no public name
    for the low-level server its tools are registered on. The transport security
    is FastMCP's default for a server on 127.0.0.1: requests are accepted only
    with a Host of 127.0.0.1 or localhost, which is what stands between a board
    with no authentication and a web page in the same browser rebinding a DNS
    name to it.
    """
    return StreamableHTTPSessionManager(
        app=server._mcp_server,
        json_response=True,
        stateless=True,
        security_settings=server.settings.transport_security,
    )


def main() -> int:
    """Speak MCP over stdio until the client hangs up.

    Nothing is printed to stdout anywhere in this package's import path, and it
    matters here more than anywhere else: stdout IS the protocol, and one stray
    print is a client that reports the server as malformed with no clue as to
    which line did it.
    """
    global cwd_is_project
    cwd_is_project = True
    server.run(transport="stdio")
    return 0
