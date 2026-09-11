#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM decisions merge one event while retaining provenance and live hook ids."""

from __future__ import annotations

import io
import json
import sqlite3
import time

import pytest

from tasktracker import codex_hook, config, hook, mcp_server, reconcile, store


def pair(conn, project, status=store.DONE):
    task = store.create_task(
        conn,
        project["id"],
        "Release 0.0.2",
        "Tagged v0.0.2",
        status=status,
        source=store.SOURCE_MCP,
    )
    prompt = store.record_turn(conn, project["id"], "session-1", "turn-1", "давай 0.0.2")
    return task, prompt


def decision(keep, duplicate):
    return {
        "keep_id": keep["id"],
        "duplicate_ids": [duplicate["id"]],
        "reason": "The Russian request and release card describe the same 0.0.2 release.",
    }


def apply_pair(conn, project, keep, duplicate):
    token = reconcile.review(conn, project["id"])["review_token"]
    return reconcile.apply(conn, project["id"], token, [decision(keep, duplicate)])


def test_cross_language_release_becomes_one_card_with_both_sources(conn, project):
    release, prompt = pair(conn, project)
    before = reconcile.review(conn, project["id"])
    assert before["needs_review"]
    assert {row["status"] for row in before["tasks"]} == {"done"}
    result = apply_pair(conn, project, release, prompt)
    assert result["merged"] == 1
    (card,) = store.tasks(conn, project["id"])
    assert card["id"] == release["id"]
    assert card["title"] == "Release 0.0.2"
    assert set(card["sources"]) == {"mcp", "prompt"}
    assert "давай 0.0.2" in card["detail"] and "Tagged v0.0.2" in card["detail"]
    assert store.projects(conn)[0]["done"] == 1
    (history,) = store.merge_history(conn, prompt["id"])
    assert [row["title"] for row in history["originals"]] == ["Release 0.0.2", "давай 0.0.2"]
    assert history["reason"] == decision(release, prompt)["reason"]
    assert not reconcile.review(conn, project["id"])["needs_review"]


def test_a_replayed_fallback_hook_and_old_mcp_id_resolve_to_surviving_card(conn, project):
    release, prompt = pair(conn, project)
    apply_pair(conn, project, release, prompt)
    replay = store.record_turn(conn, project["id"], "session-1", "turn-1", "давай 0.0.2")
    assert replay["id"] == release["id"]
    changed = store.update_task(conn, prompt["id"], title="Release shipped")
    assert changed["id"] == release["id"]
    assert store.tasks(conn, project["id"])[0]["title"] == "Release shipped"
    assert len(store.tasks(conn, project["id"])) == 1


def test_a_prompt_finishing_does_not_complete_the_substantive_task(conn, project):
    release = store.create_task(
        conn, project["id"], "Release 0.0.2", status=store.IN_PROGRESS, source=store.SOURCE_MCP
    )
    prompt = store.open_prompt_card(conn, project["id"], "codex:s1", "давай 0.0.2", turn_id="t1")
    apply_pair(conn, project, release, prompt)
    store.close_prompt_cards(conn, project["id"], "codex:s1", turn_id="t1")
    assert store.task(conn, release["id"])["status"] == store.IN_PROGRESS
    assert (
        store.open_prompt_card(conn, project["id"], "codex:s1", "давай 0.0.2", turn_id="t1")["id"]
        == release["id"]
    )


def test_llm_can_leave_related_subtasks_and_recurring_work_separate(conn, project):
    pair(conn, project)
    store.create_task(conn, project["id"], "Release 0.0.3", source=store.SOURCE_MCP)
    token = reconcile.review(conn, project["id"])["review_token"]
    # Similar words alone never trigger a merge. The server records a negative
    # LLM decision, instead of running its own fuzzy-title heuristic.
    reconcile.apply(conn, project["id"], token, [])
    assert len(store.tasks(conn, project["id"])) == 3
    assert not reconcile.review(conn, project["id"])["needs_review"]


def test_stale_llm_decisions_change_nothing(conn, project):
    release, prompt = pair(conn, project)
    token = reconcile.review(conn, project["id"])["review_token"]
    store.update_task(conn, release["id"], detail="New facts")
    with pytest.raises(ValueError, match="board changed"):
        reconcile.apply(conn, project["id"], token, [decision(release, prompt)])
    assert len(store.tasks(conn, project["id"])) == 2
    assert store.merge_history(conn, release["id"]) == []


@pytest.mark.parametrize(
    "bad",
    [
        "other_project",
        "same_id",
        "overlap",
        "prompt_keeper",
        "no_reason",
        "manual",
        "same_source",
        "boolean_id",
    ],
)
def test_invalid_group_rolls_back_the_entire_review(conn, project, tmp_path, bad):
    release, prompt = pair(conn, project)
    other_project = store.ensure_project(conn, tmp_path / "another")
    other = store.create_task(
        conn, other_project["id"], "Release 0.0.2", source=store.SOURCE_PROMPT
    )
    manual = store.create_task(conn, project["id"], "Manual release")
    mcp = store.create_task(conn, project["id"], "Other MCP", source=store.SOURCE_MCP)
    invalid = decision(release, prompt)
    if bad == "other_project":
        invalid["duplicate_ids"] = [other["id"]]
    elif bad == "same_id":
        invalid["duplicate_ids"] = [release["id"]]
    elif bad == "prompt_keeper":
        invalid = decision(prompt, release)
    elif bad == "no_reason":
        invalid["reason"] = " "
    elif bad == "manual":
        invalid["duplicate_ids"] = [manual["id"]]
    elif bad == "same_source":
        invalid["duplicate_ids"] = [mcp["id"]]
    elif bad == "boolean_id":
        invalid["keep_id"] = True
    token = reconcile.review(conn, project["id"])["review_token"]
    with pytest.raises(ValueError):
        reconcile.apply(conn, project["id"], token, [decision(release, prompt), invalid])
    assert len(store.tasks(conn, project["id"])) == 4
    assert store.merge_history(conn, release["id"]) == []


def test_native_plan_alias_keeps_updates_and_cannot_be_recreated(conn, project):
    release = store.create_task(conn, project["id"], "Release 0.0.2", source=store.SOURCE_MCP)
    todos = [{"content": "Ship 0.0.2", "status": "pending"}]
    store.mirror_todos(conn, project["id"], "codex:s", todos, source=store.SOURCE_CODEX)
    (native,) = [row for row in store.tasks(conn, project["id"]) if row["source"] == "codex"]
    apply_pair(conn, project, release, native)
    store.mirror_todos(conn, project["id"], "codex:s", [], source=store.SOURCE_CODEX)
    store.mirror_todos(conn, project["id"], "codex:s", todos, source=store.SOURCE_CODEX)
    assert len(store.tasks(conn, project["id"])) == 1
    store.mirror_todos(
        conn,
        project["id"],
        "codex:s",
        [{"content": "Ship 0.0.2", "status": "completed"}],
        source=store.SOURCE_CODEX,
    )
    assert store.task(conn, release["id"])["status"] == "done"


def test_native_keeper_is_not_withdrawn_when_it_has_other_sources(conn, project):
    store.mirror_todos(conn, project["id"], "s", [{"content": "Build", "status": "pending"}])
    (native,) = store.tasks(conn, project["id"])
    prompt = store.open_prompt_card(conn, project["id"], "s", "Build it")
    apply_pair(conn, project, native, prompt)
    assert store.mirror_todos(conn, project["id"], "s", [])["withdrawn"] == 0
    assert store.task(conn, native["id"])["status"] == "queued"


def test_chained_merges_keep_all_history_and_aliases(conn, project):
    release, prompt = pair(conn, project)
    apply_pair(conn, project, release, prompt)
    native = store.mirror_task_created(conn, project["id"], "s", "7", "Ship release")
    apply_pair(conn, project, native, release)
    assert store.task(conn, prompt["id"])["id"] == native["id"]
    assert len(store.merge_history(conn, native["id"])) == 2
    store.move_task(conn, prompt["id"], store.IN_PROGRESS, 0)
    assert store.task(conn, native["id"])["status"] == store.IN_PROGRESS
    store.delete_task(conn, release["id"])
    assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM task_merge_history").fetchone()[0] == 0


def test_long_originals_survive_detail_limits_and_are_available_over_mcp(conn, project):
    release, prompt = pair(conn, project)
    store.update_task(conn, release["id"], detail="A" * config.DETAIL_MAX)
    store.update_task(conn, prompt["id"], detail="B" * config.DETAIL_MAX)
    view = reconcile.review(conn, project["id"])
    assert all(card["detail_truncated"] for card in view["tasks"])
    apply_pair(conn, project, release, prompt)
    full = mcp_server.task_get(prompt["id"])
    originals = full["merge_history"][0]["originals"]
    assert originals[0]["detail"] == "A" * config.DETAIL_MAX
    assert originals[1]["detail"] == "B" * config.DETAIL_MAX


def test_stop_requests_one_llm_pass_and_review_prompts_make_no_cards(conn, project, capsys):
    pair(conn, project)
    payload = {"hook_event_name": "Stop", "session_id": "s", "cwd": project["path"]}
    reconcile.request_on_stop(payload, "codex")
    message = json.loads(capsys.readouterr().out)
    assert message["decision"] == "block"
    assert "tasks_review" in message["reason"] and "tasks_reconcile" in message["reason"]
    reconcile.request_on_stop(payload, "codex")
    reconcile.request_on_stop({**payload, "stop_hook_active": True}, "claude")
    assert capsys.readouterr().out == ""
    store.set_setting(conn, config.CARDS_SETTING, "prompts")
    synthetic = {
        **payload,
        "hook_event_name": "UserPromptSubmit",
        "turn_id": "internal",
        "prompt": message["reason"],
    }
    assert hook.main(io.StringIO(json.dumps(synthetic))) == 0
    assert codex_hook.main(io.StringIO(json.dumps(synthetic))) == 0
    assert len(store.tasks(conn, project["id"])) == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("client", [hook, codex_hook])
def test_real_stop_entrypoints_request_reconciliation_after_closing_prompt(
    conn, project, capsys, client
):
    store.set_setting(conn, config.CARDS_SETTING, "prompts")
    pair(conn, project)
    raw = json.dumps(
        {"hook_event_name": "Stop", "session_id": "s", "cwd": project["path"], "turn_id": "t"}
    )
    assert client.main(io.StringIO(raw)) == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "block"


def test_v1_database_migrates_without_losing_cards(tmp_path):
    path = tmp_path / "old.db"
    legacy = sqlite3.connect(path)
    legacy.executescript(store.SCHEMA)
    legacy.execute("PRAGMA user_version=1")
    legacy.execute("INSERT INTO projects VALUES (1, '/repo', 'repo', 1, 1)")
    legacy.execute(
        "INSERT INTO tasks (id, project_id, title, status, position, created_at, updated_at) "
        "VALUES (1, 1, 'Existing work', 'queued', 1, 1, 1)"
    )
    legacy.commit()
    legacy.close()
    with store.database(path) as conn:
        assert store.task(conn, 1)["title"] == "Existing work"
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        store.migrate(conn)
        assert store.merge_history(conn, 1) == []


def test_old_done_cards_are_included_in_review(conn, project):
    release, prompt = pair(conn, project)
    old = time.time() - 30 * 86400
    conn.execute("UPDATE tasks SET completed_at = ?, updated_at = ?", (old, old))
    assert store.tasks(conn, project["id"]) == []
    assert len(reconcile.review(conn, project["id"])["tasks"]) == 2
