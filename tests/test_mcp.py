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
    assert "TaskCreate" in mcp_server.INSTRUCTIONS
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


def test_with_no_project_and_no_stdio_client_the_tool_asks_for_one(home, monkeypatch, conn):
    """Over HTTP the server's working directory is the image's, not Claude's.

    Guessing from it would file every task under a project called `app`. The
    tool refuses instead, in words Claude can act on - and creates nothing
    while refusing.
    """
    monkeypatch.delenv(mcp_server.PROJECT_ENV, raising=False)
    monkeypatch.setattr(mcp_server, "cwd_is_project", False)
    with pytest.raises(mcp_server.MissingProject, match="Pass `project`"):
        mcp_server.task_add("Nowhere to go")
    assert store.projects(conn) == []


def test_under_stdio_the_working_directory_is_the_project(home, tmp_path, monkeypatch):
    root = tmp_path / "stdio-repo"
    (root / ".git").mkdir(parents=True)
    monkeypatch.delenv(mcp_server.PROJECT_ENV, raising=False)
    monkeypatch.setattr(mcp_server, "cwd_is_project", True)
    monkeypatch.chdir(root)
    assert mcp_server.task_add("From the working directory")["project"] == "stdio-repo"


# What an MCP client sends: JSON-RPC, and an Accept header naming both answers
# the streamable HTTP transport may give.
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def rpc(client, ident, method, params=None, headers=None):
    body = {"jsonrpc": "2.0", "id": ident, "method": method}
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body, headers={**MCP_HEADERS, **(headers or {})})


def test_the_web_app_serves_the_tools_over_http(home, tmp_path, monkeypatch):
    """The path the plugin actually takes: the web app, /mcp, JSON-RPC over HTTP.

    Entered as a context manager so the app's lifespan runs - the session
    manager lives there, and without it every request would fail.
    """
    from fastapi.testclient import TestClient

    from tasktracker.server.app import build

    monkeypatch.delenv(mcp_server.PROJECT_ENV, raising=False)
    root = tmp_path / "overhttp"
    (root / "src").mkdir(parents=True)
    (root / ".git").mkdir()

    with TestClient(build(), base_url="http://127.0.0.1:8787") as client:
        init = rpc(
            client,
            1,
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        )
        assert init.status_code == 200
        assert init.json()["result"]["serverInfo"]["name"] == "tasktracker"

        # Filed from a subdirectory, and still lands on the repository's board -
        # the same project the hook would have chosen.
        added = rpc(
            client,
            2,
            "tools/call",
            {
                "name": "task_add",
                "arguments": {"title": "Over HTTP", "project": str(root / "src")},
            },
        )
        assert added.json()["result"]["structuredContent"]["project"] == "overhttp"

        # And with no project, an error Claude can read rather than a guess.
        bare = rpc(client, 3, "tools/call", {"name": "tasks_queued", "arguments": {}})
        result = bare.json()["result"]
        assert result["isError"] is True
        assert "Pass `project`" in result["content"][0]["text"]

        # Codex hooks on the host and its HTTP MCP client share these rows.
        # This also catches client instructions that accidentally assume that
        # every caller has Claude's TaskCreate tool.
        from tasktracker import codex_hook

        assert "For Codex with TaskTracker hooks:" in init.json()["result"]["instructions"]
        codex_hook.mirror(
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "update_plan",
                "session_id": "codex-http",
                "cwd": str(root / "src"),
                "tool_input": {"plan": [{"step": "Native plan", "status": "pending"}]},
            }
        )
        queued = rpc(
            client,
            4,
            "tools/call",
            {
                "name": "tasks_queued",
                "arguments": {"project": str(root)},
            },
        ).json()["result"]["structuredContent"]
        (card,) = [row for row in queued["queued"] if row["source"] == "codex"]
        assert queued["cards_mode"] == "claude"
        assert card["title"] == "Native plan"
        finished = rpc(
            client,
            5,
            "tools/call",
            {
                "name": "task_done",
                "arguments": {"task_id": card["id"]},
            },
        ).json()["result"]["structuredContent"]["task"]
        assert finished["status"] == "done" and finished["source"] == "codex"


def test_the_http_endpoint_refuses_a_foreign_host(home):
    """A page in the same browser cannot rebind a DNS name to the board.

    The endpoint reads and writes the board with no authentication, which is
    safe only while nothing but 127.0.0.1 and localhost can address it. A Host
    header naming anything else is refused before any tool runs.
    """
    from fastapi.testclient import TestClient

    from tasktracker.server.app import build

    with TestClient(build(), base_url="http://127.0.0.1:8787") as client:
        refused = rpc(client, 1, "tools/list", headers={"Host": "evil.example:8787"})
        assert refused.status_code == 421


def test_a_project_id_that_does_not_exist_is_refused(repo):
    with pytest.raises(store.NotFound):
        mcp_server.tasks_queued(project="999")


def test_the_stdio_entry_point_trusts_the_working_directory(monkeypatch):
    ran = []
    monkeypatch.setattr(mcp_server, "cwd_is_project", False)
    monkeypatch.setattr(mcp_server.server, "run", lambda transport: ran.append(transport))
    assert mcp_server.main() == 0
    assert ran == ["stdio"]
    assert mcp_server.cwd_is_project is True


def test_claude_mode_tells_claude_to_keep_a_task_list():
    told = mcp_server.instructions("claude")
    assert "TaskCreate" in told and "in_progress" in told
    assert told.startswith("For Claude Code with TaskTracker hooks:")
    assert config.PLAN_INSTRUCTIONS in told
    assert "For Codex with TaskTracker hooks:" in told
    assert config.CODEX_PLAN_INSTRUCTIONS in told
    # In prompts mode the cards are the user's prompts, and Claude is not asked
    # to keep a list for the board's sake.
    assert "prompts mode" in mcp_server.instructions("prompts")
    assert config.PLAN_INSTRUCTIONS not in mcp_server.instructions("prompts")
    assert config.CODEX_PLAN_INSTRUCTIONS not in mcp_server.instructions("prompts")


def test_queue_reports_the_current_card_mode(repo, conn):
    assert mcp_server.tasks_queued()["cards_mode"] == "claude"
    store.set_setting(conn, config.CARDS_SETTING, "prompts")
    assert mcp_server.tasks_queued()["cards_mode"] == "prompts"


def test_llm_reconciliation_over_http_is_visible_in_the_panel(home, project, conn):
    from fastapi.testclient import TestClient

    from tasktracker.server.app import build

    release = store.create_task(conn, project["id"], "Release 0.0.2", source=store.SOURCE_MCP)
    prompt = store.record_turn(conn, project["id"], "s", "t", "давай 0.0.2")
    with TestClient(build(), base_url="http://127.0.0.1:8787") as client:
        view = rpc(
            client,
            1,
            "tools/call",
            {
                "name": "tasks_review",
                "arguments": {"project": project["path"]},
            },
        ).json()["result"]["structuredContent"]
        result = rpc(
            client,
            2,
            "tools/call",
            {
                "name": "tasks_reconcile",
                "arguments": {
                    "project": project["path"],
                    "review_token": view["review_token"],
                    "merges": [
                        {
                            "keep_id": release["id"],
                            "duplicate_ids": [prompt["id"]],
                            "reason": "Both refer to the same requested 0.0.2 release.",
                        }
                    ],
                },
            },
        ).json()["result"]
        assert not result.get("isError")
        assert result["structuredContent"]["merged"] == 1
        board = client.get(f"/api/projects/{project['id']}").json()
        assert len(board["tasks"]) == 1
        assert set(board["tasks"][0]["sources"]) == {"mcp", "prompt"}
        # Finishing a prompt must not finish the queued release.
        assert board["tasks"][0]["status"] == "queued"
        history = client.get(f"/api/tasks/{prompt['id']}").json()
        assert history["task"]["id"] == release["id"]
        assert history["merge_history"][0]["originals"][1]["title"] == "давай 0.0.2"
        assert client.get("/api/tasks/999999").status_code == 404


def test_the_server_records_the_card_mode_for_the_hooks(home, monkeypatch, conn):
    """The hooks run on the host and read the mode from the database."""
    from fastapi.testclient import TestClient

    from tasktracker.server.app import build

    monkeypatch.setenv(config.CARDS_ENV, "prompts")
    with TestClient(build(), base_url="http://127.0.0.1:8787"):
        pass
    assert store.setting(conn, config.CARDS_SETTING, "") == "prompts"
