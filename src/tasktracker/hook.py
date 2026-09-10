#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The PostToolUse hook: Claude Code's own tasks, mirrored onto the board.

This is what makes the board fill itself. Claude already keeps a task list
while it works and that list dies with the session; every time it changes it,
this runs and brings the session's cards on the board in line with it.

Claude Code has kept that list two ways. Current versions use one tool call per
task - TaskCreate adds one, TaskUpdate changes its status or its text - and
older ones rewrite the whole list at once with TodoWrite. The hook listens to
all three.

It also runs when a session starts, and then all it does is put the session's
project on the board. A Claude project is a project on the board from the
moment Claude is opened in it, not only once Claude has created a task there -
many sessions never create one.

Two rules govern everything here:

  * It must never fail loudly. A hook that exits non-zero, or writes to stdout,
    is a hook that interrupts the work it was supposed to be recording. Every
    path out of `main` is exit 0, and the only thing ever written is a line on
    stderr when something unexpected happened.

  * It must be cheap. It runs on every TodoWrite, so it imports the standard
    library and the store and nothing else - no fastapi, no mcp, no web
    framework for one row.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

from . import config, store

# The tools whose calls are worth mirroring. hooks.json registers the hook with
# the same three names, so in normal operation nothing else reaches here - the
# check is for a hook wired up by hand.
TODO_WRITE = "TodoWrite"
TASK_CREATE = "TaskCreate"
TASK_UPDATE = "TaskUpdate"
TOOLS = (TODO_WRITE, TASK_CREATE, TASK_UPDATE)

# The event Claude Code sends when a session starts, resumes, or is cleared.
SESSION_START = "SessionStart"

# The two events prompts mode makes cards from: a prompt sent, an answer ended.
# Claude mode uses them too - to remind, and to catch work done without tasks.
PROMPT_SUBMIT = "UserPromptSubmit"
STOP = "Stop"

# Tools that do work. A turn that used one of these and no task tool is work
# that would otherwise leave nothing on the board. Reading, searching and
# answering in words are not on the list: a question makes no card.
WORK_TOOLS = ("Bash", "Edit", "Write", "MultiEdit", "NotebookEdit")

# How TaskCreate words its result when it comes back as text rather than as an
# object: "Task #3 created successfully: ...".
TASK_NUMBER = re.compile(r"#(\d+)")


def todos_from(payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    """The todo list out of a hook payload, whichever field carries it.

    `tool_input.todos` is where TodoWrite's arguments are, and it is the field
    this reads first. `tool_response` is checked as a fallback because it is the
    tool's own account of what it ended up with, and a version that starts
    reporting the list only there would otherwise mirror nothing at all - a
    silent stop, on the one path with no output to notice it by.

    None means "this payload has no todo list", which is not the same as an
    empty list: an empty list is Claude clearing its plan, and clearing the plan
    withdraws the queued cards that went with it.
    """
    for field in ("tool_input", "tool_response"):
        section = payload.get(field)
        if isinstance(section, dict):
            for name in ("todos", "newTodos"):
                todos = section.get(name)
                if isinstance(todos, list):
                    return todos
    return None


def created_task_id(payload: dict[str, Any]) -> str | None:
    """The number TaskCreate gave the task it created.

    It is in the tool's result, not its input - Claude asks for a task and Claude
    Code numbers it. Read from `task.id` in the result object, and from the
    "Task #N" in its text when the result arrives as a string.
    """
    response = payload.get("tool_response")
    if isinstance(response, dict):
        task = response.get("task")
        if isinstance(task, dict) and task.get("id") is not None:
            return str(task["id"])
        response = response.get("content") or response.get("text")
    if isinstance(response, list):
        response = " ".join(
            str(part.get("text", "")) for part in response if isinstance(part, dict)
        )
    if isinstance(response, str):
        found = TASK_NUMBER.search(response)
        if found:
            return found.group(1)
    return None


def text_field(section: dict[str, Any], name: str) -> str | None:
    value = section.get(name)
    return value if isinstance(value, str) else None


def register(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Put the project a session started in on the board - and in claude mode,
    tell Claude to keep a task list.

    No session id is needed: registering a project touches no card, so there is
    nothing for two sessions to disagree about.

    For this event Claude Code adds whatever the hook writes to stdout to
    Claude's context, and that is the one place the instruction reliably lands:
    the same words in the MCP server's instructions were read as advice about
    that server's tools and ignored. So in claude mode the hook prints it, and in
    prompts mode - where the cards are the user's prompts - it prints nothing.

    The mode comes from the database: the container writes it there from .env
    when it starts, and this hook, on the host, never sees the container's
    environment. No row yet means claude, the default.
    """
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd.strip():
        return None
    with store.database() as conn:
        project = store.ensure_project(conn, cwd)
        mode = config.cards_mode(store.setting(conn, config.CARDS_SETTING, config.CARDS_CLAUDE))
    if mode == config.CARDS_CLAUDE:
        print(config.PLAN_INSTRUCTIONS)
    return project


def card_mode() -> str:
    """The mode the container last recorded from .env; claude if none yet."""
    with store.database() as conn:
        return config.cards_mode(store.setting(conn, config.CARDS_SETTING, config.CARDS_CLAUDE))


def prompt_event(payload: dict[str, Any]) -> Any:
    """Prompts mode: a card per prompt, done when Claude stops answering.

    Prints nothing. For UserPromptSubmit, as for SessionStart, Claude Code adds
    the hook's stdout to Claude's context, and the board has nothing to add to
    somebody's prompt.

    A prompt that is a slash command makes no card: `/clear` or a plugin's
    command is not a piece of work, and a board of them is noise.
    """
    session_id = str(payload.get("session_id") or "").strip()
    cwd = payload.get("cwd")
    if not session_id or not isinstance(cwd, str) or not cwd.strip():
        return None
    with store.database() as conn:
        project = store.ensure_project(conn, cwd)
        if payload.get("hook_event_name") == STOP:
            return store.close_prompt_cards(conn, project["id"], session_id)
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or prompt.lstrip().startswith("/"):
            return None
        return store.open_prompt_card(conn, project["id"], session_id, prompt)


def prompt_text(content: Any) -> str | None:
    """The words of a user entry in a transcript, if it is a prompt at all.

    Tool results are user entries too, and are not prompts. Nor is anything
    Claude Code writes in angle brackets - a slash command, its output, a
    caveat - which the caller treats as the start of a turn with no prompt.
    """
    if isinstance(content, list):
        if any(isinstance(part, dict) and part.get("type") == "tool_result" for part in content):
            return None
        content = " ".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    if not isinstance(content, str):
        return None
    return content.strip()


def last_turn(transcript: str) -> tuple[str | None, str | None, list[str]]:
    """The last prompt in a session's transcript, its id, and the tools used after it.

    Read from the JSONL file Claude Code keeps and names in every hook payload,
    so nothing has to be remembered between the prompt and the Stop. A slash
    command or other bracketed entry starts a turn with no prompt, so the tools
    it runs are never pinned on the prompt before it.
    """
    prompt: str | None = None
    turn_id: str | None = None
    tools: list[str] = []
    with open(transcript, encoding="utf-8", errors="replace") as lines:
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict) or entry.get("isMeta"):
                continue
            message = entry.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if entry.get("type") == "user":
                text = prompt_text(content)
                if text is None or text.startswith("[Request interrupted"):
                    continue
                if not text or text.startswith("<"):
                    prompt, turn_id, tools = None, None, []
                else:
                    prompt, turn_id, tools = text, str(entry.get("uuid") or ""), []
                continue
            if entry.get("type") == "assistant" and isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "tool_use":
                        tools.append(str(part.get("name")))
    return prompt, turn_id, tools


def claude_mode_event(payload: dict[str, Any]) -> Any:
    """Claude mode's use of the prompt events: a reminder, and a safety net.

    On a prompt, the reminder to keep a task list goes into Claude's context -
    every prompt, not only at the session's start, where a long session soon
    leaves it behind. Slash commands get none.

    On Stop, the turn is read back from the transcript. If Claude used a tool
    that does work and never touched its task list, the prompt itself becomes
    a card in DONE, so that work is on the board after all. A turn that kept
    tasks is already there; a turn of reading and talking leaves nothing.
    """
    if payload.get("hook_event_name") == PROMPT_SUBMIT:
        prompt = payload.get("prompt")
        if isinstance(prompt, str) and prompt.strip() and not prompt.lstrip().startswith("/"):
            print(config.PROMPT_REMINDER)
        return None

    session_id = str(payload.get("session_id") or "").strip()
    cwd = payload.get("cwd")
    transcript = payload.get("transcript_path")
    if not session_id or not isinstance(cwd, str) or not isinstance(transcript, str):
        return None
    prompt, turn_id, tools = last_turn(transcript)
    if not prompt or not turn_id:
        return None
    if any(tool in TOOLS for tool in tools) or not any(tool in WORK_TOOLS for tool in tools):
        return None
    with store.database() as conn:
        project = store.ensure_project(conn, cwd)
        return store.record_turn(conn, project["id"], session_id, turn_id, prompt)


def mirror(payload: dict[str, Any]) -> Any:
    """Apply one hook payload to the board.

    A session start registers the project whatever the mode. Beyond that the
    mode in .env decides which events make cards: in prompts mode, the prompts
    and the ends of Claude's answers; in claude mode, Claude's own task tools,
    with a reminder on every prompt and a card for any turn that did work
    without them. Prompts mode ignores the task tools, so a board never gets
    both a prompt card and the tasks for the same work.
    """
    event = payload.get("hook_event_name")
    if event == SESSION_START:
        return register(payload)

    if event in (PROMPT_SUBMIT, STOP):
        if card_mode() == config.CARDS_PROMPTS:
            return prompt_event(payload)
        return claude_mode_event(payload)

    tool = payload.get("tool_name")
    if tool not in TOOLS:
        return None
    if card_mode() != config.CARDS_CLAUDE:
        return None

    # The session is part of every card's identity. Without one, two sessions in
    # one repository would reconcile against each other's cards - so a payload
    # with no session id is one this hook declines to act on rather than one it
    # guesses at.
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        return None

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    if tool == TODO_WRITE:
        todos = todos_from(payload)
        if todos is None:
            return None
        with store.database() as conn:
            project = store.ensure_project(conn, payload.get("cwd") or ".")
            return store.mirror_todos(conn, project["id"], session_id, todos)

    if tool == TASK_CREATE:
        number = created_task_id(payload)
        title = text_field(tool_input, "subject")
        if number is None or not title:
            return None
        with store.database() as conn:
            project = store.ensure_project(conn, payload.get("cwd") or ".")
            return store.mirror_task_created(
                conn,
                project["id"],
                session_id,
                number,
                title=title,
                detail=text_field(tool_input, "description") or "",
            )

    # TaskUpdate. A call the tool itself reports as failed changed nothing on
    # Claude's side, and changes nothing here.
    response = payload.get("tool_response")
    if isinstance(response, dict) and response.get("success") is False:
        return None
    number = tool_input.get("taskId")
    if number is None or str(number).strip() == "":
        return None
    with store.database() as conn:
        project = store.ensure_project(conn, payload.get("cwd") or ".")
        return store.mirror_task_updated(
            conn,
            project["id"],
            session_id,
            str(number).strip(),
            status=text_field(tool_input, "status"),
            title=text_field(tool_input, "subject"),
            detail=text_field(tool_input, "description"),
        )


def main(stdin=None) -> int:
    """Read one hook payload and mirror it. Always exit 0.

    Every failure is swallowed here, and that is the design rather than
    laziness. This runs inside somebody's editing session: a traceback on a
    locked database, a board directory that cannot be created, a payload in a
    shape a later version invented - none of them is a reason to put an error in
    front of the work. The board is a record of the work, not a participant in
    it.

    The one thing that IS reported is the line on stderr, which Claude Code
    shows when it is looking. It names the failure without ever being able to
    stop anything.
    """
    source = stdin if stdin is not None else sys.stdin
    try:
        raw = source.read()
    except Exception as exc:  # noqa: BLE001 - see the docstring
        print(f"tasktracker: could not read the hook payload: {exc}", file=sys.stderr)
        return 0

    try:
        payload = json.loads(raw or "{}")
    except ValueError:
        # Not JSON. Nothing to mirror and nothing worth saying: a hook fed
        # something else is a wiring mistake, and it will be equally silent on
        # every subsequent call, so one line per TodoWrite would be noise.
        return 0

    if not isinstance(payload, dict):
        return 0

    try:
        mirror(payload)
    except Exception as exc:  # noqa: BLE001 - see the docstring
        print(f"tasktracker: the task mirror failed: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
