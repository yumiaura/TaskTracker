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
    """QUEUE, IN PROGRESS and DONE - the three columns the projects table shows."""
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


def test_a_request_connection_works_on_another_thread_than_the_one_that_opened_it(home):
    """FastAPI opens a request's connection on one pool thread and may use it on
    another. sqlite3 refuses that by default, and every request that landed that
    way answered 500 - intermittently, on the panel's own polls.
    """
    import threading

    from tasktracker.server import routes_api

    opened = routes_api.connection()
    conn = next(opened)
    failures = []

    def use():
        try:
            conn.execute("SELECT count(*) FROM projects").fetchone()
        except Exception as exc:  # noqa: BLE001 - the failure is what is asserted on
            failures.append(exc)

    worker = threading.Thread(target=use)
    worker.start()
    worker.join()
    opened.close()
    assert failures == []


def test_the_panel_s_concurrent_polls_all_answer_200(client, board):
    """The header and the board poll at the same moment. Both must answer."""
    from concurrent.futures import ThreadPoolExecutor

    paths = ["/api/projects", f"/api/projects/{board['id']}"] * 20
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda path: client.get(path).status_code, paths))
    assert set(codes) == {200}


# ---------------------------------------------------------------------------
# Failures, each in the one envelope the panel reads
# ---------------------------------------------------------------------------


def error_of(answer):
    return answer.json()["error"]["message"]


def test_what_is_not_there_is_404(client, board):
    assert client.delete("/api/projects/999").status_code == 404
    assert client.post("/api/projects/999/tasks", json={"title": "x"}).status_code == 404
    missing = client.patch("/api/tasks/999", json={"title": "x"})
    assert missing.status_code == 404
    assert "999" in error_of(missing)


def test_what_cannot_be_written_is_400(client, board):
    blank = client.post(f"/api/projects/{board['id']}/tasks", json={"title": "   "})
    assert blank.status_code == 400
    assert error_of(blank) == "a task needs a title"

    card = client.post(f"/api/projects/{board['id']}/tasks", json={"title": "real"}).json()
    wrong = client.patch(f"/api/tasks/{card['id']}", json={"status": "someday"})
    assert wrong.status_code == 400
    assert "someday" in error_of(wrong)


def test_a_failure_detail_reads_as_one_sentence():
    from tasktracker.server.app import sentence

    assert sentence("plain") == "plain"
    assert sentence({"error": {"message": "wrapped"}}) == "wrapped"
    assert sentence({"msg": "pydantic"}) == "pydantic"
    assert sentence([
        {"loc": ["body", "done_hide_days"], "msg": "too small"},
        {"loc": ["body"], "type": "missing"},
        "not a dict",
    ]) == "done_hide_days: too small; missing; not a dict"
    assert sentence(42) == "42"


def test_a_missing_panel_directory_leaves_the_api_up(tmp_path, caplog):
    from fastapi import FastAPI

    from tasktracker.server import webui

    app = FastAPI()
    assert webui.mount(app, directory=tmp_path / "nowhere") is False
    assert "is missing" in caplog.text
