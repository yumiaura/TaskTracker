#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The store: what a card does when it moves, and what the mirror is allowed to
withdraw."""

from __future__ import annotations

import time

import pytest

from tasktracker import config, store


def test_project_is_the_repository_root_not_the_working_directory(conn, tmp_path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    inner = root / "src" / "deep"
    inner.mkdir(parents=True)

    outer = store.ensure_project(conn, root)
    nested = store.ensure_project(conn, inner)

    assert nested["id"] == outer["id"]
    assert nested["path"] == str(root.resolve())
    assert nested["name"] == "repo"


def test_a_directory_under_no_vcs_is_its_own_project(conn, tmp_path):
    loose = tmp_path / "scratch"
    loose.mkdir()
    assert store.ensure_project(conn, loose)["path"] == str(loose.resolve())


def test_new_cards_land_at_the_foot_of_their_column(conn, project):
    first = store.create_task(conn, project["id"], "first")
    second = store.create_task(conn, project["id"], "second")
    assert second["position"] > first["position"]
    assert [row["title"] for row in store.tasks(conn, project["id"])] == ["first", "second"]


def test_a_title_is_one_line_and_a_blank_one_is_refused(conn, project):
    card = store.create_task(conn, project["id"], "  keep\n\tit  one   line ")
    assert card["title"] == "keep it one line"
    with pytest.raises(ValueError):
        store.create_task(conn, project["id"], "   \n  ")


def test_finishing_stamps_the_card_and_going_back_clears_it(conn, project):
    card = store.create_task(conn, project["id"], "ship it")
    assert card["started_at"] is None and card["completed_at"] is None

    running = store.update_task(conn, card["id"], status=store.IN_PROGRESS)
    assert running["started_at"] is not None

    finished = store.update_task(conn, card["id"], status=store.DONE)
    assert finished["completed_at"] is not None
    assert finished["started_at"] == running["started_at"]

    reopened = store.update_task(conn, card["id"], status=store.QUEUED)
    assert reopened["completed_at"] is None
    # The moment it was first picked up survives being put back in the queue:
    # it happened, and nothing about reopening the card makes it not have.
    assert reopened["started_at"] == running["started_at"]


def test_moving_a_card_puts_it_where_it_was_dropped(conn, project):
    titles = ["a", "b", "c"]
    cards = [store.create_task(conn, project["id"], title) for title in titles]

    store.move_task(conn, cards[2]["id"], store.QUEUED, 0)
    assert [row["title"] for row in store.tasks(conn, project["id"])] == ["c", "a", "b"]

    # Past the end is the end, not an error: a drop below the last card is a
    # drop at the bottom, and that is what the pointer was over.
    store.move_task(conn, cards[2]["id"], store.QUEUED, 99)
    assert [row["title"] for row in store.tasks(conn, project["id"])] == ["a", "b", "c"]


def test_moving_between_columns_carries_the_status(conn, project):
    card = store.create_task(conn, project["id"], "a")
    moved = store.move_task(conn, card["id"], store.IN_PROGRESS, 0)
    assert moved["status"] == store.IN_PROGRESS
    assert moved["started_at"] is not None


def test_finished_cards_are_hidden_by_age_and_never_deleted(conn, project):
    card = store.create_task(conn, project["id"], "old news", status=store.DONE)
    long_ago = time.time() - 30 * 86400
    conn.execute("UPDATE tasks SET completed_at = ? WHERE id = ?", (long_ago, card["id"]))

    store.set_setting(conn, "done_hide_days", "7")
    assert store.tasks(conn, project["id"]) == []
    assert store.tasks(conn, project["id"], hide_done=False)[0]["id"] == card["id"]

    # Zero is "keep them all", not "hide them all".
    store.set_setting(conn, "done_hide_days", "0")
    assert store.tasks(conn, project["id"])[0]["id"] == card["id"]

    # And the row was there the whole time.
    assert store.task(conn, card["id"])["title"] == "old news"


def test_an_unreadable_hide_setting_falls_back_rather_than_raising(conn):
    store.set_setting(conn, "done_hide_days", "seven")
    assert store.done_hide_days(conn) == config.DEFAULT_DONE_HIDE_DAYS


def test_the_projects_screen_counts_what_the_board_would_draw(conn, project):
    store.create_task(conn, project["id"], "queued one")
    store.create_task(conn, project["id"], "running", status=store.IN_PROGRESS)
    finished = store.create_task(conn, project["id"], "ancient", status=store.DONE)
    conn.execute(
        "UPDATE tasks SET completed_at = ? WHERE id = ?",
        (time.time() - 30 * 86400, finished["id"]),
    )
    store.set_setting(conn, "done_hide_days", "7")

    row = store.projects(conn)[0]
    assert (row["queued"], row["in_progress"], row["done"]) == (1, 1, 0)


def test_the_mirror_adds_updates_and_withdraws_only_its_own_queued_cards(conn, project):
    typed = store.create_task(conn, project["id"], "typed by hand")

    first = store.mirror_todos(
        conn,
        project["id"],
        "sess-1",
        [
            {"content": "read the code", "status": "completed"},
            {"content": "write the patch", "status": "in_progress"},
            {"content": "run the tests", "status": "pending"},
        ],
    )
    assert first == {"added": 3, "updated": 0, "withdrawn": 0}

    # The plan changed: the finished and the running entries stay, the queued
    # one Claude dropped is withdrawn, and the card a person typed is untouched
    # even though it is queued too.
    second = store.mirror_todos(
        conn,
        project["id"],
        "sess-1",
        [
            {"content": "read the code", "status": "completed"},
            {"content": "write the patch", "status": "completed"},
        ],
    )
    assert second == {"added": 0, "updated": 1, "withdrawn": 1}

    titles = {row["title"]: row["status"] for row in store.tasks(conn, project["id"])}
    assert titles == {
        "typed by hand": store.QUEUED,
        "read the code": store.DONE,
        "write the patch": store.DONE,
    }
    assert store.task(conn, typed["id"])["source"] == store.SOURCE_MANUAL


def test_two_sessions_on_one_project_keep_their_own_cards(conn, project):
    same = [{"content": "same words", "status": "pending"}]
    store.mirror_todos(conn, project["id"], "sess-1", same)
    store.mirror_todos(conn, project["id"], "sess-2", same)
    assert len(store.tasks(conn, project["id"])) == 2

    # And one session clearing its list does not withdraw the other's card.
    store.mirror_todos(conn, project["id"], "sess-1", [])
    rows = store.tasks(conn, project["id"])
    assert len(rows) == 1 and rows[0]["session_id"] == "sess-2"


def test_a_project_can_be_named_by_id_path_or_name(conn, project, tmp_path):
    assert store.find_project(conn, str(project["id"]))["id"] == project["id"]
    assert store.find_project(conn, str(tmp_path / "repo" / "src"))["id"] == project["id"]
    assert store.find_project(conn, "repo")["id"] == project["id"]
    with pytest.raises(store.NotFound):
        store.find_project(conn, "nothing-by-that-name")


def test_an_ambiguous_name_is_refused_rather_than_guessed(conn, tmp_path):
    for parent in ("one", "two"):
        root = tmp_path / parent / "api"
        (root / ".git").mkdir(parents=True)
        store.ensure_project(conn, root)
    with pytest.raises(store.NotFound, match="names 2 projects"):
        store.find_project(conn, "api")


def test_deleting_a_project_takes_its_cards_with_it(conn, project):
    card = store.create_task(conn, project["id"], "goes with it")
    store.delete_project(conn, project["id"])
    with pytest.raises(store.NotFound):
        store.task(conn, card["id"])


def test_what_the_store_refuses(conn, project):
    with pytest.raises(ValueError, match="unknown status"):
        store.create_task(conn, project["id"], "x", status="someday")
    card = store.create_task(conn, project["id"], "x")
    with pytest.raises(ValueError, match="a task needs a title"):
        store.update_task(conn, card["id"], title="   ")
    with pytest.raises(ValueError, match="unknown status"):
        store.update_task(conn, card["id"], status="someday")
    with pytest.raises(store.NotFound):
        store.find_project(conn, "  ")
    with pytest.raises(store.NotFound):
        store.delete_project(conn, 999)


def test_a_failed_write_leaves_nothing_behind(conn, project):
    """The transaction rolls back: a write that fails half way is not half done."""
    with pytest.raises(RuntimeError):
        with store.transaction(conn):
            conn.execute(
                "UPDATE projects SET name = 'renamed' WHERE id = ?", (project["id"],)
            )
            raise RuntimeError("stop here")
    assert store.project(conn, project["id"])["name"] == project["name"]


def test_an_update_that_carries_nothing_changes_nothing(conn, project):
    card = store.mirror_task_created(conn, project["id"], "s", "1", title="kept")
    same = store.mirror_task_updated(conn, project["id"], "s", "1")
    assert same["id"] == card["id"] and same["status"] == store.QUEUED
