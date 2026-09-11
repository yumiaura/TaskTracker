#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Codex lifecycle hooks: mirror update_plan, or track prompts until Stop.

Only the documented hook payload is read. Codex transcripts are not a stable
interface, and neither scanning them nor running an MCP server is needed here.
Like the Claude hook, this entry point uses only the standard library.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from . import config, reconcile, store

EVENTS = ("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop")


def text_field(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    return value.strip() if isinstance(value, str) else ""


def plan_from(payload: dict[str, Any]) -> list[dict[str, str]] | None:
    """Adapt the whole Codex plan to the store's todo format.

    A missing or malformed plan is not an empty plan: only an actual empty
    list is allowed to withdraw queued cards. Validate before changing any row.
    """
    section = payload.get("tool_input")
    if not isinstance(section, dict) or not isinstance(section.get("plan"), list):
        return None
    response = payload.get("tool_response")
    if isinstance(response, dict) and (
        response.get("isError") is True or response.get("success") is False
    ):
        return None
    todos = []
    for entry in section["plan"]:
        if not isinstance(entry, dict):
            return None
        step = text_field(entry, "step")
        status = text_field(entry, "status")
        if not step or status not in store.TODO_STATUS:
            return None
        todos.append({"content": step, "status": status})
    return todos


def mirror(payload: dict[str, Any]) -> Any:
    event = payload.get("hook_event_name")
    cwd = text_field(payload, "cwd")
    if event not in EVENTS or not cwd:
        return None
    session = text_field(payload, "session_id")
    if event != "SessionStart" and not session:
        return None
    # Two clients can use the same raw session id without owning each other's
    # cards. Prefix even prompt sessions, which share the generic PROMPT badge.
    session_id = f"codex:{session}"
    with store.database() as conn:
        mode = config.cards_mode(store.setting(conn, config.CARDS_SETTING, config.CARDS_CLAUDE))
        if event == "SessionStart":
            project = store.ensure_project(conn, cwd)
            print(
                config.CODEX_PLAN_INSTRUCTIONS
                if mode == config.CARDS_CLAUDE
                else config.CODEX_PROMPTS_INSTRUCTIONS
            )
            return project

        if event == "UserPromptSubmit":
            prompt = text_field(payload, "prompt")
            if not prompt or prompt.startswith(("/", reconcile.INTERNAL_PREFIX)):
                return None
            if mode == config.CARDS_CLAUDE:
                print(config.CODEX_PLAN_INSTRUCTIONS)
                return None
            turn_id = text_field(payload, "turn_id")
            if not turn_id:
                return None
            project = store.ensure_project(conn, cwd)
            return store.open_prompt_card(conn, project["id"], session_id, prompt, turn_id=turn_id)

        if event == "Stop":
            turn_id = text_field(payload, "turn_id")
            if mode != config.CARDS_PROMPTS or not turn_id:
                return None
            project = store.ensure_project(conn, cwd)
            return store.close_prompt_cards(conn, project["id"], session_id, turn_id=turn_id)

        if mode != config.CARDS_CLAUDE or payload.get("tool_name") != "update_plan":
            return None
        todos = plan_from(payload)
        if todos is None:
            return None
        project = store.ensure_project(conn, cwd)
        return store.mirror_todos(conn, project["id"], session_id, todos, source=store.SOURCE_CODEX)


def main(stdin=None) -> int:
    """A board failure must not stop the editing session or change a tool result."""
    try:
        payload = json.loads((stdin if stdin is not None else sys.stdin).read() or "{}")
        if isinstance(payload, dict):
            mirror(payload)
            reconcile.request_on_stop(payload, "codex")
    except ValueError:
        return 0
    except Exception as exc:  # noqa: BLE001 - advisory hook, as with the Claude mirror
        print(f"tasktracker: the Codex mirror failed: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
