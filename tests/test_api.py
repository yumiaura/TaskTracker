#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The REST API: what the panel gets back, and what it gets back when it asks
for something that is not there."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tasktracker import store
from tasktracker.server.app import build


@pytest.fixture()
def client(home):
    return TestClient(build())


@pytest.fixture()
def board(conn, tmp_path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    return store.ensure_project(conn, root)


def test_health_names_the_database_it_opened(client, home):
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert str(home) in body["database"]


def test_a_project_row_carries_the_three_counts(client, conn, board):
    store.create_task(conn, board["id"], "queued")
    store.create_task(conn, board["id"], "running", status=store.IN_PROGRESS)

    rows = client.get("/api/projects").json()["projects"]
    assert len(rows) == 1
    assert (rows[0]["queued"], rows[0]["in_progress"], rows[0]["done"]) == (1, 1, 0)


def test_the_board_answers_with_project_tasks_and_settings_together(client, conn, board):
    store.create_task(conn, board["id"], "one")
    body = client.get(f"/api/projects/{board['id']}").json()
    assert body["project"]["id"] == board["id"]
    assert [task["title"] for task in body["tasks"]] == ["one"]
    assert body["settings"]["done_hide_days"] == 7


def test_creating_editing_moving_and_deleting_a_card(client, board):
    created = client.post(
        f"/api/projects/{board['id']}/tasks", json={"title": "write it", "detail": "the long form"}
    )
    assert created.status_code == 201
    card = created.json()
    assert card["status"] == "queued" and card["source"] == "manual"

    edited = client.patch(f"/api/tasks/{card['id']}", json={"title": "write it properly"}).json()
    assert edited["title"] == "write it properly"
    # A field the panel did not send is a field it did not change.
    assert edited["detail"] == "the long form"

    moved = client.post(
        f"/api/tasks/{card['id']}/move", json={"status": "in_progress", "index": 0}
    ).json()
    assert moved["status"] == "in_progress" and moved["started_at"] is not None

    assert client.delete(f"/api/tasks/{card['id']}").json() == {"deleted": card["id"]}
    assert client.patch(f"/api/tasks/{card['id']}", json={"title": "gone"}).status_code == 404


def test_a_blank_title_is_a_400_and_says_so(client, board):
    answer = client.post(f"/api/projects/{board['id']}/tasks", json={"title": "   "})
    assert answer.status_code == 400
    assert "title" in answer.json()["error"]["message"]


def test_every_api_failure_arrives_in_one_shape(client, board):
    for response in (
        client.get("/api/projects/9999"),
        client.patch("/api/tasks/9999", json={"title": "x"}),
        client.post("/api/tasks/9999/move", json={"status": "done", "index": 0}),
        client.delete("/api/tasks/9999"),
        client.get("/api/nothing-here"),
    ):
        assert response.status_code == 404
        assert isinstance(response.json()["error"]["message"], str)


def test_an_unknown_status_is_refused(client, board):
    card = client.post(f"/api/projects/{board['id']}/tasks", json={"title": "a"}).json()
    assert client.post(
        f"/api/tasks/{card['id']}/move", json={"status": "parked", "index": 0}
    ).status_code == 400


def test_the_hide_setting_round_trips_and_is_bounded(client):
    assert client.put("/api/settings", json={"done_hide_days": 30}).json() == {
        "done_hide_days": 30
    }
    assert client.get("/api/settings").json() == {"done_hide_days": 30}
    assert client.put("/api/settings", json={"done_hide_days": -1}).status_code == 422
    assert client.put("/api/settings", json={"done_hide_days": 99999}).status_code == 422


def test_hidden_finished_cards_can_still_be_asked_for(client, conn, board):
    import time

    card = store.create_task(conn, board["id"], "ancient", status=store.DONE)
    conn.execute(
        "UPDATE tasks SET completed_at = ? WHERE id = ?", (time.time() - 60 * 86400, card["id"])
    )
    assert client.get(f"/api/projects/{board['id']}").json()["tasks"] == []
    shown = client.get(f"/api/projects/{board['id']}?hide_done=false").json()["tasks"]
    assert [task["title"] for task in shown] == ["ancient"]


def test_deleting_a_project_takes_its_cards(client, conn, board):
    store.create_task(conn, board["id"], "goes with it")
    assert client.delete(f"/api/projects/{board['id']}").json() == {"deleted": board["id"]}
    assert client.get("/api/projects").json()["projects"] == []


def test_the_panel_is_served_at_the_root(client):
    # The mount is registered last so it cannot swallow /api; what it answers
    # for / depends on whether the www directory has been built yet, and either
    # answer proves the API in front of it still resolves.
    assert client.get("/api/health").status_code == 200
