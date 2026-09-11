#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Codex payloads, session isolation, and installation into an existing config."""

from __future__ import annotations

import io
import json
import os
import shlex
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tasktracker import codex_hook, codex_setup, config, store

ROOT = Path(__file__).resolve().parent.parent


def event(project, name, **fields):
    return {
        "hook_event_name": name,
        "cwd": project["path"],
        "session_id": "session-1",
        "turn_id": "turn-1",
        **fields,
    }


def plan(project, steps, **fields):
    return event(
        project,
        "PostToolUse",
        tool_name="update_plan",
        tool_input={"plan": [{"step": title, "status": status} for title, status in steps]},
        **fields,
    )


def test_native_plan_progress_reuses_cards_and_keeps_other_clients(conn, project):
    # Even the same raw id and title cannot let Codex reconcile Claude's plan.
    store.mirror_todos(
        conn, project["id"], "session-1", [{"content": "Build", "status": "pending"}]
    )
    manual = store.create_task(conn, project["id"], title="Build")
    steps = [("Build", "pending"), ("Test", "pending")]
    codex_hook.mirror(plan(project, steps))
    original = [row for row in store.tasks(conn, project["id"]) if row["source"] == "codex"]
    assert len(original) == 2
    for state, column in [("in_progress", "in_progress"), ("completed", "done")]:
        codex_hook.mirror(plan(project, [("Build", state), ("Test", "pending")]))
        assert store.task(conn, original[0]["id"])["status"] == column
    codex_hook.mirror(plan(project, []))
    rows = store.tasks(conn, project["id"])
    assert {(row["source"], row["status"]) for row in rows} == {
        ("todo", "queued"),
        ("manual", "queued"),
        ("codex", "done"),
    }
    assert store.task(conn, manual["id"])["status"] == "queued"


def test_two_codex_sessions_and_projects_keep_separate_plans(conn, project, tmp_path):
    other = store.ensure_project(conn, tmp_path / "other")
    steps = [("Same title", "pending")]
    codex_hook.mirror(plan(project, steps))
    codex_hook.mirror(plan(project, steps, session_id="session-2"))
    codex_hook.mirror(plan(other, steps))
    codex_hook.mirror(plan(project, []))
    assert [row["session_id"] for row in store.tasks(conn, project["id"])] == ["codex:session-2"]
    assert len(store.tasks(conn, other["id"])) == 1


@pytest.mark.parametrize(
    "tool_input",
    [
        None,
        {},
        {"plan": None},
        {"plan": "bad"},
        {"plan": [None]},
        {"plan": [{"step": "Build", "status": "bad"}]},
        {"plan": [{"step": "", "status": "pending"}]},
    ],
)
def test_bad_plans_do_not_withdraw_existing_cards(conn, project, tool_input):
    codex_hook.mirror(plan(project, [("Build", "pending")]))
    payload = event(project, "PostToolUse", tool_name="update_plan", tool_input=tool_input)
    assert codex_hook.mirror(payload) is None
    assert len(store.tasks(conn, project["id"])) == 1


@pytest.mark.parametrize(
    "changed",
    [
        {"hook_event_name": "PreToolUse"},
        {"tool_name": "other_update_plan"},
        {"session_id": ""},
        {"cwd": ""},
        {"tool_response": {"isError": True}},
        {"tool_response": {"success": False}},
    ],
)
def test_unrelated_or_failed_events_do_not_change_the_board(conn, project, changed):
    payload = plan(project, [("Build", "pending")])
    payload.update(changed)
    assert codex_hook.mirror(payload) is None
    assert store.tasks(conn, project["id"]) == []


def test_session_start_registers_project_and_uses_codex_instructions(home, conn, tmp_path, capsys):
    root = tmp_path / "new-repo"
    (root / ".git").mkdir(parents=True)
    payload = {"hook_event_name": "SessionStart", "cwd": str(root), "source": "resume"}
    codex_hook.mirror(payload)
    assert store.projects(conn)[0]["path"] == str(root)
    assert capsys.readouterr().out.strip() == config.CODEX_PLAN_INSTRUCTIONS
    store.set_setting(conn, config.CARDS_SETTING, config.CARDS_PROMPTS)
    codex_hook.mirror(payload)
    assert capsys.readouterr().out.strip() == config.CODEX_PROMPTS_INSTRUCTIONS


def test_each_prompt_reminds_codex_to_keep_its_plan_without_a_card(conn, project, capsys):
    for prompt in ("Build it", "Build it"):
        codex_hook.mirror(event(project, "UserPromptSubmit", prompt=prompt))
        assert capsys.readouterr().out.strip() == config.CODEX_PLAN_INSTRUCTIONS
    codex_hook.mirror(event(project, "Stop"))
    assert store.tasks(conn, project["id"]) == []


def test_prompt_lifecycle_is_idempotent_and_late_stop_cannot_finish_next_turn(
    conn, project, capsys
):
    store.set_setting(conn, config.CARDS_SETTING, "prompts")
    payload = event(project, "UserPromptSubmit", prompt="Исправь ошибку\nОписание ошибки")
    first = codex_hook.mirror(payload)
    assert first["status"] == "in_progress"
    assert first["title"] == "Исправь ошибку"
    assert first["detail"] == payload["prompt"]
    assert codex_hook.mirror(payload)["id"] == first["id"]
    codex_hook.mirror(plan(project, [("Hidden plan", "pending")]))
    second = codex_hook.mirror(event(project, "UserPromptSubmit", prompt="Next", turn_id="turn-2"))
    assert store.task(conn, first["id"])["status"] == "done"
    codex_hook.mirror(event(project, "Stop"))
    assert store.task(conn, second["id"])["status"] == "in_progress"
    codex_hook.mirror(event(project, "Stop", turn_id="turn-2"))
    codex_hook.mirror(event(project, "Stop", turn_id="turn-2"))
    codex_hook.mirror(payload)
    rows = store.tasks(conn, project["id"])
    assert len(rows) == 2 and all(row["status"] == "done" for row in rows)
    assert capsys.readouterr().out == ""


def test_prompt_stop_does_not_touch_other_sessions(conn, project):
    store.set_setting(conn, config.CARDS_SETTING, "prompts")
    claude = store.open_prompt_card(conn, project["id"], "session-1", "Claude prompt")
    codex_hook.mirror(event(project, "UserPromptSubmit", prompt="First"))
    other = codex_hook.mirror(
        event(project, "UserPromptSubmit", prompt="Second", session_id="session-2")
    )
    codex_hook.mirror(event(project, "Stop"))
    assert store.task(conn, claude["id"])["status"] == "in_progress"
    assert store.task(conn, other["id"])["status"] == "in_progress"


def test_concurrent_copies_of_a_prompt_leave_one_card_in_progress(conn, project, monkeypatch):
    store.set_setting(conn, config.CARDS_SETTING, "prompts")
    lookup = store.mirrored_task
    both_read = threading.Barrier(2)

    def read_before_either_writes(*args):
        existing = lookup(*args)
        if existing is None:
            both_read.wait(timeout=5)
        return existing

    monkeypatch.setattr(store, "mirrored_task", read_before_either_writes)
    payload = event(project, "UserPromptSubmit", prompt="Only once")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(codex_hook.mirror, [payload, payload]))
    assert results[0]["id"] == results[1]["id"]
    rows = store.tasks(conn, project["id"])
    assert len(rows) == 1 and rows[0]["status"] == "in_progress"


@pytest.mark.parametrize("prompt", [None, "", "  ", " /clear", "/mcp"])
def test_empty_prompts_and_slash_commands_make_no_cards(conn, project, prompt, capsys):
    store.set_setting(conn, config.CARDS_SETTING, "prompts")
    codex_hook.mirror(event(project, "UserPromptSubmit", prompt=prompt))
    assert store.tasks(conn, project["id"]) == []
    assert capsys.readouterr().out == ""


def test_missing_turn_does_not_close_a_valid_prompt(conn, project):
    store.set_setting(conn, config.CARDS_SETTING, "prompts")
    payload = event(project, "UserPromptSubmit", prompt="Keep open")
    created = codex_hook.mirror(payload)
    codex_hook.mirror(event(project, "Stop", turn_id=None))
    assert codex_hook.mirror({**payload, "turn_id": None}) is None
    assert store.task(conn, created["id"])["status"] == "in_progress"


@pytest.mark.parametrize("raw", ["not json", "[]", "null", "{}"])
def test_invalid_input_is_quiet(raw, capsys):
    assert codex_hook.main(io.StringIO(raw)) == 0
    assert capsys.readouterr().out == ""


def test_an_unwritable_board_cannot_interrupt_codex(tmp_path, monkeypatch, capsys):
    blocked = tmp_path / "file"
    blocked.write_text("not a directory")
    monkeypatch.setenv(config.HOME_ENV, str(blocked))
    raw = json.dumps({"hook_event_name": "SessionStart", "cwd": str(tmp_path)})
    assert codex_hook.main(io.StringIO(raw)) == 0
    captured = capsys.readouterr()
    assert not captured.out and "Codex mirror failed" in captured.err


def test_install_preserves_other_hooks_and_is_idempotent(tmp_path):
    target = tmp_path / "hooks.json"
    unrelated = {"type": "command", "command": "echo custom"}
    document = {
        "description": "My hooks",
        "hooks": {
            "PostToolUse": [{"matcher": "Bash", "hooks": [unrelated]}],
            "Stop": [{"hooks": [unrelated]}],
        },
    }
    original = json.dumps(document)
    target.write_text(original)
    wrapper = ROOT / "hooks" / "codex-mirror.py"
    assert codex_setup.install(target, wrapper)
    installed = json.loads(target.read_text())
    assert installed["description"] == "My hooks"
    assert installed["hooks"]["PostToolUse"][0] == document["hooks"]["PostToolUse"][0]
    assert installed["hooks"]["Stop"][0] == document["hooks"]["Stop"][0]
    assert installed["hooks"]["PostToolUse"][1]["matcher"] == "^update_plan$"
    assert set(installed["hooks"]) == set(codex_hook.EVENTS)
    (backup,) = tmp_path.glob("hooks.json.*.bak")
    assert backup.read_text() == original
    assert not codex_setup.install(target, wrapper)
    assert len(list(tmp_path.glob("*.bak"))) == 1


@pytest.mark.parametrize("raw", ["broken", "[]", '{"hooks": []}', '{"hooks": {"Stop": [{}]}}'])
def test_install_refuses_malformed_config_without_changing_it(tmp_path, raw):
    target = tmp_path / "hooks.json"
    target.write_text(raw)
    with pytest.raises(ValueError):
        codex_setup.install(target, ROOT / "hooks" / "codex-mirror.py")
    assert target.read_text() == raw
    assert list(tmp_path.glob("*.bak")) == []


def test_installer_and_generated_command_work_without_pip_from_another_directory(tmp_path):
    target = tmp_path / "profile with spaces" / "hooks.json"
    env = {**os.environ, "CODEX_HOME": str(target.parent), config.HOME_ENV: str(tmp_path / "board")}
    installed = subprocess.run(
        [sys.executable, "-S", str(ROOT / "hooks" / "install-codex.py")],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert str(target) in installed.stdout
    group = json.loads(target.read_text())["hooks"]["PostToolUse"][0]
    command = shlex.split(group["hooks"][0]["command"])
    # -S disables site-packages, proving the wrapper imports only its own
    # checkout and the standard library; the hook needs no pip installation.
    done = subprocess.run(
        [command[0], "-S", *command[1:]],
        cwd=tmp_path,
        env=env,
        input=json.dumps(plan({"path": str(tmp_path)}, [("From Codex", "pending")])),
        text=True,
        capture_output=True,
        check=True,
    )
    assert not done.stdout and not done.stderr
    with store.database(tmp_path / "board" / "tasks.db") as conn:
        project = store.find_project(conn, str(tmp_path))
        assert store.tasks(conn, project["id"])[0]["source"] == "codex"
