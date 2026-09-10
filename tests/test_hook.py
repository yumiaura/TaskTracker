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

import pytest

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

    assert (
        run(
            payload(
                root,
                todos=[
                    {
                        "content": "Read the code",
                        "status": "completed",
                        "activeForm": "Reading the code",
                    },
                    {
                        "content": "Write the patch",
                        "status": "in_progress",
                        "activeForm": "Writing",
                    },
                    {"content": "Run the tests", "status": "pending", "activeForm": "Running"},
                ],
            )
        )
        == 0
    )

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
    # Current Claude Code keeps its list with TaskCreate/TaskUpdate; older
    # versions with TodoWrite. A matcher missing either never runs the hook.
    assert set(entry["matcher"].split("|")) == {"TaskCreate", "TaskUpdate", "TodoWrite"}
    command = entry["hooks"][0]["command"]
    assert "todo-mirror.py" in command
    assert (PLUGIN_ROOT / "hooks" / "todo-mirror.py").is_file()

    # The plugin reaches the MCP tools in the board's container, over HTTP, at
    # the path the web app mounts them on. Declared in the manifest itself: a
    # .mcp.json at the root of the checkout is ALSO read by Claude Code as the
    # project's own MCP config whenever it runs in this directory, and the
    # plugin's format - server names at the top level - fails that parser with
    # "mcpServers: Invalid input" in `claude mcp list`.
    assert manifest["mcpServers"]["tasktracker"] == {
        "type": "http",
        "url": "http://127.0.0.1:8787/mcp",
    }
    assert not (PLUGIN_ROOT / ".mcp.json").exists()


# How Claude Code names a tool served by a plugin's MCP server:
# mcp__plugin_<plugin>_<server>__<tool>. A command's `allowed-tools` has to use
# that exact name, or the pre-approval silently matches nothing and the command
# stops to ask for permission on every run.
PLUGIN_TOOL_PREFIX = "mcp__plugin_tasktracker_tasktracker__"


def test_the_commands_pre_approve_tools_by_the_names_claude_code_gives_them():
    import asyncio
    import re

    from tasktracker import mcp_server

    served = {tool.name for tool in asyncio.run(mcp_server.server.list_tools())}
    named = []
    for command in (PLUGIN_ROOT / "commands").glob("*.md"):
        header = command.read_text().split("---")[1]
        line = re.search(r"^allowed-tools:(.*)$", header, re.MULTILINE)
        if line:
            named += [
                (command.name, item.strip())
                for item in line.group(1).split(",")
                if item.strip().startswith("mcp__")
            ]

    # At least /tasktracker:tasks names its tools; a test that finds none would
    # pass without having checked anything.
    assert named
    for command, tool in named:
        assert tool.startswith(PLUGIN_TOOL_PREFIX), f"{command}: {tool}"
        assert tool[len(PLUGIN_TOOL_PREFIX) :] in served, f"{command}: {tool} is not served"


# ---------------------------------------------------------------------------
# TaskCreate / TaskUpdate: what current Claude Code sends
# ---------------------------------------------------------------------------
#
# The payload shapes below are the ones Claude Code 2.1 records for these
# tools: TaskCreate takes subject/description/activeForm and answers with the
# task's number in `task.id`; TaskUpdate takes taskId and status and answers
# with `success`.


def created(root, number, subject, description="", session="sess-1", response=None):
    return {
        "session_id": session,
        "cwd": str(root),
        "hook_event_name": "PostToolUse",
        "tool_name": "TaskCreate",
        "tool_input": {"subject": subject, "description": description, "activeForm": subject},
        "tool_response": response
        if response is not None
        else {"task": {"id": str(number), "subject": subject}},
    }


def updated(root, number, session="sess-1", success=True, **fields):
    return {
        "session_id": session,
        "cwd": str(root),
        "hook_event_name": "PostToolUse",
        "tool_name": "TaskUpdate",
        "tool_input": {"taskId": str(number), **fields},
        "tool_response": {
            "success": success,
            "taskId": str(number),
            "updatedFields": sorted(fields),
            "statusChange": fields.get("status"),
        },
    }


def board(conn, root):
    project = store.find_project(conn, str(root))
    return {row["title"]: row for row in store.tasks(conn, project["id"])}


def test_a_task_claude_creates_lands_queued_and_moves_with_it(home, tmp_path, conn):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)

    run(created(root, 1, "Read the code", "Start with the store"))
    run(created(root, 2, "Write the patch"))
    cards = board(conn, root)
    assert cards["Read the code"]["status"] == store.QUEUED
    assert cards["Read the code"]["detail"] == "Start with the store"
    assert cards["Read the code"]["source"] == store.SOURCE_TODO

    run(updated(root, 1, status="in_progress"))
    assert board(conn, root)["Read the code"]["status"] == store.IN_PROGRESS
    run(updated(root, 1, status="completed"))
    assert board(conn, root)["Read the code"]["status"] == store.DONE

    # A new subject is written onto the same card rather than making another.
    run(updated(root, 2, subject="Write the patch and its test"))
    assert set(board(conn, root)) == {"Read the code", "Write the patch and its test"}


def test_a_task_claude_deletes_leaves_the_board_whatever_its_column(home, tmp_path, conn):
    """The board mirrors Claude's tasks one for one."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    run(created(root, 1, "Queued then dropped"))
    run(created(root, 2, "Finished then dropped"))
    run(updated(root, 2, status="completed"))

    run(updated(root, 1, status="deleted"))
    run(updated(root, 2, status="deleted"))
    assert board(conn, root) == {}


def test_the_number_is_read_from_a_text_result_too(home, tmp_path, conn):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    run(created(root, 4, "From text", response="Task #4 created successfully: From text"))
    run(updated(root, 4, status="in_progress"))
    assert board(conn, root)["From text"]["status"] == store.IN_PROGRESS


def test_a_hook_run_twice_for_one_create_makes_one_card(home, tmp_path, conn):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    run(created(root, 1, "Only once"))
    run(created(root, 1, "Only once"))
    assert list(board(conn, root)) == ["Only once"]


def test_numbers_are_per_session(home, tmp_path, conn):
    """Every session's task list starts again at 1."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    run(created(root, 1, "First session's task", session="a"))
    run(created(root, 1, "Second session's task", session="b"))
    run(updated(root, 1, session="b", status="completed"))

    cards = board(conn, root)
    assert cards["First session's task"]["status"] == store.QUEUED
    assert cards["Second session's task"]["status"] == store.DONE


def test_updates_that_cannot_be_applied_change_nothing(home, tmp_path, conn):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    run(created(root, 1, "Stays queued"))

    # A number with no card: a task created before the plugin was installed.
    run(updated(root, 9, status="completed"))
    # An update the tool itself reports as failed.
    run(updated(root, 1, success=False, status="completed"))

    assert {title: row["status"] for title, row in board(conn, root).items()} == {
        "Stays queued": store.QUEUED
    }


def test_a_todo_write_in_the_same_session_leaves_task_cards_alone(home, tmp_path, conn):
    """The TodoWrite mirror reconciles its own cards, never ones TaskCreate made."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    run(created(root, 1, "From TaskCreate"))
    run(payload(root, todos=[{"content": "From TodoWrite", "status": "pending"}]))
    run(payload(root, todos=[]))
    assert list(board(conn, root)) == ["From TaskCreate"]


def test_the_shipped_wrapper_mirrors_a_task_create(tmp_path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    board_dir = tmp_path / "board"

    done = subprocess.run(
        [sys.executable, str(PLUGIN_ROOT / "hooks" / "todo-mirror.py")],
        input=json.dumps(created(root, 1, "Through the wrapper")),
        capture_output=True,
        text=True,
        env={
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
            config.HOME_ENV: str(board_dir),
            "PATH": os.environ.get("PATH", ""),
        },
    )
    assert done.returncode == 0
    assert done.stdout == ""
    assert done.stderr == ""

    conn = store.connect(board_dir / "tasks.db")
    try:
        assert list(board(conn, root)) == ["Through the wrapper"]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# SessionStart: the project appears when Claude is opened in it
# ---------------------------------------------------------------------------


def session_start(cwd, source="startup", session="sess-1"):
    return {
        "session_id": session,
        "cwd": str(cwd),
        "hook_event_name": "SessionStart",
        "source": source,
        "transcript_path": "/dev/null",
    }


def test_a_session_starting_in_a_folder_puts_its_project_on_the_board(home, tmp_path, conn, capsys):
    root = tmp_path / "fresh"
    (root / ".git").mkdir(parents=True)
    (root / "src").mkdir()

    # Started in a subdirectory, and resumed later: one project, the repository.
    assert run(session_start(root / "src")) == 0
    assert run(session_start(root, source="resume")) == 0

    projects = store.projects(conn)
    assert [row["name"] for row in projects] == ["fresh"]
    assert store.tasks(conn, projects[0]["id"]) == []

    # Claude Code adds a SessionStart hook's stdout to Claude's context. In
    # claude mode - the default, with no mode recorded - that is the instruction
    # to keep a task list, once per start, and nothing else.
    out = capsys.readouterr().out
    assert out.count(config.PLAN_INSTRUCTIONS) == 2
    assert out.replace(config.PLAN_INSTRUCTIONS, "").strip() == ""


def test_a_session_start_with_no_folder_registers_nothing(home, conn):
    body = session_start("")
    assert run(body) == 0
    assert store.projects(conn) == []


def test_the_plugin_runs_the_hook_on_session_start():
    hooks = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text())["hooks"]
    start = hooks["SessionStart"][0]["hooks"][0]["command"]
    assert start == hooks["PostToolUse"][0]["hooks"][0]["command"]


# ---------------------------------------------------------------------------
# Payloads the hook declines, quietly
# ---------------------------------------------------------------------------


def test_task_payloads_missing_what_they_need_change_nothing(home, tmp_path, conn):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)

    # TaskCreate with no number anywhere in its result, and one with no subject.
    run(created(root, 1, "No number", response={}))
    run(created(root, 1, "", response={"task": {"id": "1"}}))
    # TaskUpdate with no task id, and one whose input is not an object at all.
    no_id = updated(root, 1, status="completed")
    no_id["tool_input"].pop("taskId")
    run(no_id)
    garbled = updated(root, 1, status="completed")
    garbled["tool_input"] = "not an object"
    run(garbled)
    # TodoWrite whose input carries no list.
    empty = payload(root)
    empty["tool_input"] = {}
    run(empty)

    projects = store.projects(conn)
    assert all(store.tasks(conn, row["id"]) == [] for row in projects)


def test_the_task_number_is_read_from_a_content_list(home, tmp_path, conn):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    response = {"content": [{"type": "text", "text": "Task #7 created successfully"}]}
    run(created(root, 7, "From a content list", response=response))
    run(updated(root, 7, status="in_progress"))
    assert board(conn, root)["From a content list"]["status"] == store.IN_PROGRESS


def test_an_unreadable_stdin_is_reported_and_still_exits_zero(capsys):
    class Broken:
        def read(self):
            raise OSError("stdin went away")

    assert hook.main(Broken()) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "stdin went away" in captured.err


def test_in_prompts_mode_a_session_start_says_nothing(home, tmp_path, conn, capsys):
    root = tmp_path / "quiet"
    (root / ".git").mkdir(parents=True)
    store.set_setting(conn, config.CARDS_SETTING, config.CARDS_PROMPTS)
    run(session_start(root))
    assert [row["name"] for row in store.projects(conn)] == ["quiet"]
    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# Prompts mode: a card per prompt
# ---------------------------------------------------------------------------


def prompt_sent(cwd, prompt, session="sess-1"):
    return {
        "session_id": session,
        "cwd": str(cwd),
        "hook_event_name": "UserPromptSubmit",
        "prompt": prompt,
    }


def answer_ended(cwd, session="sess-1"):
    return {"session_id": session, "cwd": str(cwd), "hook_event_name": "Stop"}


@pytest.fixture()
def prompts_mode(home, conn):
    store.set_setting(conn, config.CARDS_SETTING, config.CARDS_PROMPTS)


def test_a_prompt_is_a_card_in_progress_until_claude_stops(prompts_mode, tmp_path, conn, capsys):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)

    run(prompt_sent(root, "Fix the login form\nIt rejects valid emails."))
    card = board(conn, root)["Fix the login form"]
    assert card["status"] == store.IN_PROGRESS
    assert card["source"] == store.SOURCE_PROMPT
    assert card["detail"] == "Fix the login form\nIt rejects valid emails."

    run(answer_ended(root))
    assert board(conn, root)["Fix the login form"]["status"] == store.DONE

    # UserPromptSubmit and Stop add their stdout to Claude's context: nothing.
    assert capsys.readouterr().out == ""


def test_the_next_prompt_closes_an_answer_that_was_interrupted(prompts_mode, tmp_path, conn):
    """An interrupted answer fires no Stop; the next prompt finishes its card."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    run(prompt_sent(root, "First request"))
    run(prompt_sent(root, "Second request"))
    cards = board(conn, root)
    assert cards["First request"]["status"] == store.DONE
    assert cards["Second request"]["status"] == store.IN_PROGRESS


def test_slash_commands_and_empty_prompts_make_no_card(prompts_mode, tmp_path, conn):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    run(prompt_sent(root, "/clear"))
    run(prompt_sent(root, "   "))
    assert all(store.tasks(conn, row["id"]) == [] for row in store.projects(conn))


def test_in_prompts_mode_claude_s_tasks_are_not_mirrored(prompts_mode, tmp_path, conn):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    run(created(root, 1, "A task of Claude's"))
    run(payload(root, todos=[{"content": "A todo of Claude's", "status": "pending"}]))
    assert all(store.tasks(conn, row["id"]) == [] for row in store.projects(conn))


def test_in_claude_mode_prompts_make_no_card(home, tmp_path, conn):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    run(prompt_sent(root, "Not a card in claude mode"))
    run(answer_ended(root))
    assert all(store.tasks(conn, row["id"]) == [] for row in store.projects(conn))


def test_the_plugin_runs_the_hook_on_prompts_and_stops():
    hooks = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text())["hooks"]
    command = hooks["PostToolUse"][0]["hooks"][0]["command"]
    for event in ("UserPromptSubmit", "Stop"):
        assert hooks[event][0]["hooks"][0]["command"] == command


# ---------------------------------------------------------------------------
# Claude mode: a reminder on every prompt, and a card for work done untracked
# ---------------------------------------------------------------------------


def transcript(tmp_path, *entries):
    """A session transcript in the JSONL shape Claude Code writes."""
    path = tmp_path / "session.jsonl"
    with path.open("w", encoding="utf-8") as out:
        for entry in entries:
            out.write(json.dumps(entry) + "\n")
    return path


def said(text, uuid):
    return {"type": "user", "uuid": uuid, "message": {"role": "user", "content": text}}


def used(*tools):
    return {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": name, "input": {}} for name in tools]},
    }


def returned():
    return {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}}


def stopped(root, path, session="sess-1"):
    return {**answer_ended(root, session), "transcript_path": str(path)}


def test_in_claude_mode_every_prompt_carries_the_reminder(home, tmp_path, conn, capsys):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    run(prompt_sent(root, "Update everything and push"))
    assert capsys.readouterr().out.strip() == config.PROMPT_REMINDER
    # A slash command gets none, and no prompt makes a card by itself here.
    run(prompt_sent(root, "/clear"))
    assert capsys.readouterr().out == ""
    assert all(store.tasks(conn, row["id"]) == [] for row in store.projects(conn))


def test_work_done_without_a_task_list_becomes_a_done_card(home, tmp_path, conn):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    path = transcript(
        tmp_path,
        said("Earlier question", "u0"),
        said("Merge everything into main\nand push it", "u1"),
        used("Bash"),
        returned(),
        used("Edit", "Bash"),
        returned(),
    )
    run(stopped(root, path))
    card = board(conn, root)["Merge everything into main"]
    assert card["status"] == store.DONE
    assert card["source"] == store.SOURCE_PROMPT
    assert card["detail"] == "Merge everything into main\nand push it"

    # The same Stop again is the same turn: still one card.
    run(stopped(root, path))
    assert list(board(conn, root)) == ["Merge everything into main"]


def test_a_turn_that_kept_tasks_makes_no_extra_card(home, tmp_path, conn):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    path = transcript(tmp_path, said("Do three things", "u1"), used("TaskCreate", "Bash"))
    run(stopped(root, path))
    assert all(store.tasks(conn, row["id"]) == [] for row in store.projects(conn))


def test_a_question_answered_by_reading_makes_no_card(home, tmp_path, conn):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    path = transcript(tmp_path, said("What does this function do?", "u1"), used("Read", "Grep"))
    run(stopped(root, path))
    assert all(store.tasks(conn, row["id"]) == [] for row in store.projects(conn))


def test_a_slash_command_turn_is_not_pinned_on_the_prompt_before_it(home, tmp_path, conn):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    path = transcript(
        tmp_path,
        said("Look at the logs", "u1"),
        used("Read"),
        said("<command-name>/deploy</command-name>", "u2"),
        used("Bash"),
        {"type": "user", "isMeta": True, "message": {"content": "caveat"}},
        said("[Request interrupted by user]", "u3"),
    )
    run(stopped(root, path))
    assert all(store.tasks(conn, row["id"]) == [] for row in store.projects(conn))


def test_a_missing_transcript_is_quiet(home, tmp_path, conn, capsys):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    assert run(stopped(root, tmp_path / "nowhere.jsonl")) == 0
    assert capsys.readouterr().out == ""
    assert all(store.tasks(conn, row["id"]) == [] for row in store.projects(conn))
