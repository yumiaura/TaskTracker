#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The PostToolUse hook: what it mirrors, and what it refuses to do loudly.

The second half of this file matters more than the first. The hook runs inside
somebody's editing session, so the behaviour under test is mostly "does not
throw, does not print, exits 0" - and that is exactly the behaviour nothing
notices when it regresses.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

from tasktracker import config, hook, store

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def payload(cwd, session="sess-1", todos=None, tool="TodoWrite"):
    return {
        "session_id": session,
        "cwd": str(cwd),
        "hook_event_name": "PostToolUse",
        "tool_name": tool,
        "tool_input": {"todos": todos if todos is not None else []},
        "tool_response": {},
    }


def run(payload_dict, capsys=None):
    return hook.main(io.StringIO(json.dumps(payload_dict)))


def test_a_todo_list_lands_on_the_board(home, tmp_path, conn):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)

    assert run(payload(root, todos=[
        {"content": "Read the code", "status": "completed", "activeForm": "Reading the code"},
        {"content": "Write the patch", "status": "in_progress", "activeForm": "Writing"},
        {"content": "Run the tests", "status": "pending", "activeForm": "Running"},
    ])) == 0

    project = store.find_project(conn, str(root))
    assert project["name"] == "repo"
    rows = {row["title"]: row for row in store.tasks(conn, project["id"])}
    assert rows["Read the code"]["status"] == store.DONE
    assert rows["Write the patch"]["status"] == store.IN_PROGRESS
    assert rows["Run the tests"]["status"] == store.QUEUED
    assert all(row["source"] == store.SOURCE_TODO for row in rows.values())


def test_the_hook_is_run_from_a_subdirectory_and_still_finds_the_repository(home, tmp_path, conn):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    inner = root / "src" / "deep"
    inner.mkdir(parents=True)

    run(payload(inner, todos=[{"content": "From below", "status": "pending"}]))
    assert [row["name"] for row in store.projects(conn)] == ["repo"]


def test_a_payload_from_another_tool_is_ignored(home, tmp_path, conn):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    run(payload(root, todos=[{"content": "Not a todo write", "status": "pending"}], tool="Edit"))
    assert store.projects(conn) == []


def test_a_payload_with_no_session_is_declined(home, tmp_path, conn):
    """Two sessions in one repository reconcile against their own cards only.

    With no session id there is nothing to key the mirror on, and guessing -
    keying on the project alone - would have each session withdraw the queued
    cards the other had just written.
    """
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    run(payload(root, session="", todos=[{"content": "Whose is this", "status": "pending"}]))
    assert store.projects(conn) == []


def test_the_todos_are_taken_from_the_response_when_the_input_has_none(home, tmp_path, conn):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    body = payload(root)
    body["tool_input"] = {}
    body["tool_response"] = {"newTodos": [{"content": "Late arrival", "status": "pending"}]}
    run(body)

    project = store.find_project(conn, str(root))
    assert [row["title"] for row in store.tasks(conn, project["id"])] == ["Late arrival"]


def test_garbage_on_stdin_exits_quietly(home, capsys):
    assert hook.main(io.StringIO("this is not json")) == 0
    assert hook.main(io.StringIO("")) == 0
    assert hook.main(io.StringIO("[1, 2, 3]")) == 0
    captured = capsys.readouterr()
    # Nothing on stdout, ever - and a wiring mistake does not earn a line of
    # stderr on every keystroke either.
    assert captured.out == ""
    assert captured.err == ""


def test_a_broken_board_is_reported_on_stderr_and_still_exits_zero(
    home, tmp_path, monkeypatch, capsys
):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)

    def explode(*args, **kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(hook.store, "database", explode)
    assert run(payload(root, todos=[{"content": "Never lands", "status": "pending"}])) == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "database is locked" in captured.err


def test_the_shipped_hook_script_runs_as_the_plugin_invokes_it(tmp_path):
    """The wrapper Claude Code actually runs, on a payload, in a subprocess.

    Everything above imports `tasktracker.hook` directly, which proves the
    mirror and proves nothing about whether the file named in hooks.json can
    find the package at all. This runs it exactly as the plugin does - with
    CLAUDE_PLUGIN_ROOT set and nothing installed - and asserts it wrote a card.
    """
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    board = tmp_path / "board"

    done = subprocess.run(
        [sys.executable, str(PLUGIN_ROOT / "hooks" / "todo-mirror.py")],
        input=json.dumps(
            payload(root, todos=[{"content": "Through the wrapper", "status": "pending"}])
        ),
        capture_output=True,
        text=True,
        env={
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
            config.HOME_ENV: str(board),
            "PATH": os.environ.get("PATH", ""),
        },
    )
    assert done.returncode == 0
    assert done.stdout == ""

    conn = store.connect(board / "tasks.db")
    try:
        project = store.find_project(conn, str(root))
        assert [row["title"] for row in store.tasks(conn, project["id"])] == ["Through the wrapper"]
    finally:
        conn.close()


def test_the_plugin_manifest_names_the_files_it_ships():
    manifest = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "tasktracker"

    hooks = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text())
    entry = hooks["hooks"]["PostToolUse"][0]
    assert entry["matcher"] == "TodoWrite"
    command = entry["hooks"][0]["command"]
    assert "todo-mirror.py" in command
    assert (PLUGIN_ROOT / "hooks" / "todo-mirror.py").is_file()

    # The plugin reaches the MCP tools in the board's container, over HTTP, at
    # the path the web app mounts them on.
    servers = json.loads((PLUGIN_ROOT / ".mcp.json").read_text())
    assert servers["tasktracker"] == {"type": "http", "url": "http://127.0.0.1:8787/mcp"}
