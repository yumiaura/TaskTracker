#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The MCP tools: what Claude gets back, and how a project is resolved.

The tool functions are called directly. FastMCP's decorator registers them and
returns the function unchanged, so there is nothing between these tests and the
code the protocol reaches - and the one thing that IS in between, the transport,
has an end-to-end test of its own at the foot of the file.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tasktracker import config, mcp_server, store


@pytest.fixture()
def repo(tmp_path, monkeypatch, home):
    """A project, and an MCP server that believes it is running inside it."""
    root = tmp_path / "widget"
    (root / ".git").mkdir(parents=True)
    monkeypatch.setenv(mcp_server.PROJECT_ENV, str(root))
    return root


def test_a_tool_files_against_the_project_it_is_running_in(repo):
    added = mcp_server.task_add("Rename the widget")
    assert added["project"] == "widget"
    assert added["task"]["status"] == "queued"
    assert added["task"]["source"] == "mcp"

    queued = mcp_server.tasks_queued()
    assert [task["title"] for task in queued["queued"]] == ["Rename the widget"]
    assert queued["in_progress"] == []


def test_the_brief_shape_leaves_out_the_bookkeeping(repo):
    task = mcp_server.task_add("Short", detail="the long form")["task"]
    assert set(task) == {"id", "title", "status", "detail", "source"}

    # And a card with no detail does not carry an empty field on every row.
    bare = mcp_server.task_add("No detail here")["task"]
    assert "detail" not in bare


def test_starting_and_finishing_a_task(repo):
    task = mcp_server.task_add("Ship it")["task"]
    assert mcp_server.task_start(task["id"])["task"]["status"] == "in_progress"
    assert mcp_server.task_done(task["id"])["task"]["status"] == "done"

    # Finished work is out of the queue but still on the board.
    assert mcp_server.tasks_queued()["queued"] == []
    assert [row["title"] for row in mcp_server.tasks_all()["tasks"]] == ["Ship it"]


def test_an_empty_field_on_update_leaves_that_field_alone(repo):
    task = mcp_server.task_add("Original", detail="keep me")["task"]
    updated = mcp_server.task_update(task["id"], title="Renamed")["task"]
    assert updated["title"] == "Renamed"
    assert updated["detail"] == "keep me"


def test_deleting_is_not_finishing(repo):
    task = mcp_server.task_add("Filed by mistake")["task"]
    assert mcp_server.task_delete(task["id"]) == {"deleted": task["id"]}
    assert mcp_server.tasks_all()["tasks"] == []


def test_a_name_that_matches_nothing_is_refused_rather_than_created(repo, conn):
    with pytest.raises(store.NotFound):
        mcp_server.task_add("Wrong board", project="no-such-project")
    # And nothing was created under that name while failing.
    assert [row["name"] for row in store.projects(conn)] == []


def test_a_path_creates_the_project_it_names(repo, tmp_path, conn):
    other = tmp_path / "second"
    (other / ".git").mkdir(parents=True)
    added = mcp_server.task_add("Filed elsewhere", project=str(other))
    assert added["project"] == "second"
    assert {row["name"] for row in store.projects(conn)} == {"second"}


def test_an_existing_project_can_be_named(repo, conn):
    mcp_server.task_add("First")
    listed = mcp_server.projects_list()["projects"]
    assert [row["name"] for row in listed] == ["widget"]

    by_name = mcp_server.task_add("Second", project="widget")
    assert by_name["project"] == "widget"
    assert len(store.projects(conn)) == 1


def test_the_instructions_tell_claude_not_to_double_file_its_todos():
    # The one instruction the server cannot do without: the hook mirrors
    # TodoWrite already, and a session that also files each todo through
    # `task_add` puts every card on the board twice.
    assert "TodoWrite" in mcp_server.INSTRUCTIONS
    assert "task_add" in mcp_server.INSTRUCTIONS


def test_the_server_speaks_the_protocol_over_stdio(tmp_path):
    """One real client, one real subprocess, over the transport the plugin uses.

    Everything above calls the functions directly, which proves the board is
    right and proves nothing about the wire. This is the test that fails if a
    stray print reaches stdout - stdout IS the protocol on this path, and one
    line of it is a client reporting a malformed server with no clue which line
    did it.
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    root = tmp_path / "overwire"
    (root / ".git").mkdir(parents=True)
    source = str(Path(__file__).resolve().parent.parent / "src")

    async def talk():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tasktracker.cli", "mcp"],
            env={
                "PYTHONPATH": source,
                config.HOME_ENV: str(tmp_path / "board"),
                mcp_server.PROJECT_ENV: str(root),
                "PATH": os.environ.get("PATH", ""),
            },
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                info = await session.initialize()
                tools = await session.list_tools()
                added = await session.call_tool("task_add", {"title": "Over the wire"})
                queued = await session.call_tool("tasks_queued", {})
                return info, {tool.name for tool in tools.tools}, added, queued

    info, names, added, queued = asyncio.run(talk())

    assert info.serverInfo.name == "tasktracker"
    assert {"tasks_queued", "task_add", "task_done", "projects_list"} <= names
    assert added.structuredContent["task"]["title"] == "Over the wire"
    assert queued.structuredContent["project"] == "overwire"


def test_nothing_on_the_import_path_writes_to_stdout():
    """Importing the package must be silent.

    The stdio test above would catch a print in a tool, but a print at import
    time happens before the first message and breaks the handshake itself - a
    failure that reads as "the server did not start" rather than as anything to
    do with the line that caused it.
    """
    source = str(Path(__file__).resolve().parent.parent / "src")
    done = subprocess.run(
        [sys.executable, "-c", "import tasktracker, tasktracker.mcp_server, tasktracker.cli"],
        capture_output=True,
        env={**os.environ, "PYTHONPATH": source},
        check=True,
    )
    assert done.stdout == b""
