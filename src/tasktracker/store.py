#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The SQLite store: projects, tasks, settings, and the todo mirror.

Every process in this package reads and writes through this module and none of
them holds a connection open between calls. That is deliberate. Three writers
can be live at once - the web panel, the MCP server, and a PostToolUse hook
that runs on every TodoWrite - and they are separate processes with no way to
coordinate. A connection per call in WAL mode, with a busy timeout, is what
makes that safe without any of them knowing the others exist.

Timestamps are unix epoch floats throughout, on the wire as well as in the
table. One representation, formatted once in the browser, so no two screens can
disagree about what a date means.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from . import config

# The three columns of the board, in the order they are drawn, and the only
# values the `status` column accepts. The CHECK constraint in the schema names
# them again rather than deriving them: a status that reaches the table through
# a path that skipped validation is a card that renders in no column at all,
# and the database is the last place that can still say no.
QUEUED = "queued"
IN_PROGRESS = "in_progress"
DONE = "done"
STATUSES = (QUEUED, IN_PROGRESS, DONE)

# Where a task came from, which is the difference between "Claude planned this
# while working" and "somebody typed it".
#
# It matters for exactly one behaviour - the todo mirror is allowed to withdraw
# a queued card it created and never a card anybody else did - and it is on the
# card in the panel because a board that mixes the two without saying so is a
# board where a card nobody recognises looks like a bug.
SOURCE_TODO = "todo"
SOURCE_MCP = "mcp"
SOURCE_MANUAL = "manual"

# How far apart consecutive cards sit. Positions are floats and a card dropped
# between two others takes their midpoint, so a wide gap is what keeps that
# arithmetic away from the precision floor: at 1024 apart a column would have to
# be re-split about fifty times in the same place before two positions collide.
POSITION_GAP = 1024.0

# What Claude Code's own todo list calls the three states, mapped onto ours.
# Its spellings, not ours - they go over the hook's stdin and an invented one
# would silently mirror nothing.
TODO_STATUS = {
    "pending": QUEUED,
    "in_progress": IN_PROGRESS,
    "completed": DONE,
}

# The board read left to right, as one SQL sort key. The table view lists the
# same cards as the three columns do and in the same order, so switching views
# does not reshuffle work somebody was halfway through reading.
COLUMN_ORDER = (
    "CASE status WHEN 'queued' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END"
)

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id         INTEGER PRIMARY KEY,
  path       TEXT    NOT NULL UNIQUE,
  name       TEXT    NOT NULL,
  created_at REAL    NOT NULL,
  updated_at REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
  id           INTEGER PRIMARY KEY,
  project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title        TEXT    NOT NULL,
  detail       TEXT    NOT NULL DEFAULT '',
  status       TEXT    NOT NULL CHECK (status IN ('queued', 'in_progress', 'done')),
  position     REAL    NOT NULL,
  source       TEXT    NOT NULL DEFAULT 'manual',
  session_id   TEXT,
  created_at   REAL    NOT NULL,
  updated_at   REAL    NOT NULL,
  started_at   REAL,
  completed_at REAL
);

CREATE INDEX IF NOT EXISTS tasks_by_project ON tasks (project_id, status, position);
CREATE INDEX IF NOT EXISTS tasks_by_session ON tasks (project_id, session_id, source);

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


class NotFound(Exception):
    """A project or a task the caller named does not exist.

    Its own type rather than a None return, because every caller of `task` and
    `project` has to answer a 404 or an MCP error and none of them has anything
    useful to do with a missing row - a None threaded through four layers is how
    one of them ends up rendering "None" in a toast.
    """


def connect(path: Path | None = None) -> sqlite3.Connection:
    """A connection with the schema in place, ready to write.

    WAL and the busy timeout are set on every connection rather than once at
    creation: they are per-connection settings in SQLite - WAL is the one
    exception, being a property of the file, but setting it again is free and
    means a database created by an older build is migrated by the first process
    that opens it rather than by a step somebody has to remember to run.

    Five seconds of busy timeout is far past anything this application does in a
    transaction. It is there for the pathological case - a hook, a panel poll
    and an MCP call landing in the same millisecond - where the alternative is
    an immediate "database is locked" and a lost task.
    """
    target = path or config.db_path()
    conn = sqlite3.connect(target, timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    # Off by default in SQLite, and the tasks table leans on it: deleting a
    # project has to take its cards with it, and without this the rows survive
    # their project and are unreachable from every screen.
    conn.execute("PRAGMA foreign_keys=ON")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Bring the file up to `SCHEMA_VERSION`.

    `user_version` rather than a migrations table: there is one number to read,
    it costs no query planning, and the whole history of this schema fits in the
    branch below. When a second version arrives it is one more `if`.
    """
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version >= SCHEMA_VERSION:
        return
    # Statement by statement rather than through `executescript`, which commits
    # whatever transaction is open before it runs its first line - so a schema
    # applied that way is applied outside the transaction meant to protect it,
    # and the COMMIT that follows fails on a connection with nothing to commit.
    with transaction(conn):
        for statement in filter(None, (part.strip() for part in SCHEMA.split(";"))):
            conn.execute(statement)
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")


class transaction:  # noqa: N801 - a context manager used as a statement, not a type
    """`BEGIN IMMEDIATE` … `COMMIT`, or `ROLLBACK` on the way out.

    The connections here run with `isolation_level=None`, which means sqlite3
    does not open transactions on the caller's behalf and every statement stands
    alone. That is what we want for a read; it is wrong for the multi-statement
    writes below, where a move that renumbered half a column and then failed
    would leave the column renumbered.

    IMMEDIATE rather than DEFERRED: a deferred transaction takes its write lock
    at the first write, which is after it has already read - so two processes
    can both read, both try to upgrade, and one of them gets SQLITE_BUSY with no
    timeout applied and no way to retry safely. Taking the lock up front is what
    the busy timeout can actually wait on.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, kind: Any, value: Any, trace: Any) -> bool:
        if kind is None:
            self.conn.execute("COMMIT")
        else:
            self.conn.execute("ROLLBACK")
        return False


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------


def setting(conn: sqlite3.Connection, key: str, fallback: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else fallback


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


def done_hide_days(conn: sqlite3.Connection) -> int:
    """How many days a finished task stays on the board. Zero means forever.

    Anything unreadable falls back to the default rather than raising. The value
    is one row in a table anybody can edit with the sqlite3 shell, and a board
    that refuses to render because somebody typed "seven" is worse than a board
    that hides finished cards a week later than they meant.
    """
    raw = setting(conn, "done_hide_days", str(config.DEFAULT_DONE_HIDE_DAYS))
    try:
        days = int(float(raw))
    except (TypeError, ValueError):
        return config.DEFAULT_DONE_HIDE_DAYS
    return days if days >= 0 else config.DEFAULT_DONE_HIDE_DAYS


def settings(conn: sqlite3.Connection) -> dict[str, Any]:
    """Every setting the panel knows about, with its defaults filled in."""
    return {"done_hide_days": done_hide_days(conn)}


# --------------------------------------------------------------------------
# Projects
# --------------------------------------------------------------------------


def touch_project(conn: sqlite3.Connection, project_id: int, when: float | None = None) -> None:
    """Stamp a project as changed.

    Called by every write that touches one of its tasks, because the projects
    table's whole job on the first screen is to answer "what have I been working
    on lately", and a column that only moved when a project was created would
    sort that screen by nothing anybody cares about.
    """
    conn.execute(
        "UPDATE projects SET updated_at = ? WHERE id = ?",
        (when if when is not None else time.time(), project_id),
    )


def ensure_project(conn: sqlite3.Connection, path: str | Path) -> dict[str, Any]:
    """The project for a directory, created on first sight.

    Keyed on the resolved repository root, so `~/src/app`, `~/src/app/web` and a
    symlink to either all land on one board. The name is refreshed on every
    call: a directory that was renamed is the same project, and a board still
    labelled with the old name is a row the operator scrolls past looking for
    the new one.
    """
    root = str(config.project_root(path))
    name = config.project_name(root)
    now = time.time()
    conn.execute(
        "INSERT INTO projects (path, name, created_at, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (path) DO UPDATE SET name = excluded.name",
        (root, name, now, now),
    )
    row = conn.execute("SELECT * FROM projects WHERE path = ?", (root,)).fetchone()
    return dict(row)


def project(conn: sqlite3.Connection, project_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise NotFound(f"no project {project_id}")
    return dict(row)


def find_project(conn: sqlite3.Connection, wanted: str) -> dict[str, Any]:
    """A project named on the wire: by id, by path, or by name.

    Three spellings because three callers need different ones. The panel has the
    id. The hook has an absolute path. Claude, asked to file something against
    another project, has whatever the operator called it in the sentence - and
    the name is the only one of the three a person ever says out loud.

    A name that matches more than one project is refused rather than resolved to
    the first hit: two checkouts called `api` in different directories are
    exactly the case where guessing files the task against the wrong one, and
    nothing on the board would say it had happened.
    """
    text = str(wanted).strip()
    if not text:
        raise NotFound("no project named")
    if text.isdigit():
        return project(conn, int(text))
    if "/" in text:
        root = str(config.project_root(text))
        row = conn.execute("SELECT * FROM projects WHERE path = ?", (root,)).fetchone()
        if row is None:
            raise NotFound(f"no project at {root}")
        return dict(row)
    rows = conn.execute(
        "SELECT * FROM projects WHERE name = ? ORDER BY updated_at DESC", (text,)
    ).fetchall()
    if not rows:
        raise NotFound(f"no project named {text!r}")
    if len(rows) > 1:
        paths = ", ".join(row["path"] for row in rows)
        raise NotFound(f"{text!r} names {len(rows)} projects - use a path: {paths}")
    return dict(rows[0])


def delete_project(conn: sqlite3.Connection, project_id: int) -> None:
    with transaction(conn):
        cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    if cursor.rowcount == 0:
        raise NotFound(f"no project {project_id}")


def projects(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every project, with the three counts the first screen prints.

    Counted in the same query that lists them rather than in a loop over the
    rows: a board with forty projects would otherwise be forty-one round trips
    to answer one screen that polls every few seconds.

    The done count is the VISIBLE done count - what the board would draw - so
    the number on the projects row and the number of cards in the right-hand
    column are the same number. A row saying 90 done above a column showing 3 is
    a row that teaches the operator to distrust the screen.
    """
    cutoff = done_cutoff(done_hide_days(conn))
    rows = conn.execute(
        """
        SELECT p.*,
               COALESCE(SUM(t.status = 'queued'), 0)      AS queued,
               COALESCE(SUM(t.status = 'in_progress'), 0) AS in_progress,
               COALESCE(SUM(t.status = 'done'
                            AND (? IS NULL
                                 OR COALESCE(t.completed_at, t.updated_at) >= ?)), 0) AS done
          FROM projects p
          LEFT JOIN tasks t ON t.project_id = p.id
         GROUP BY p.id
         ORDER BY p.updated_at DESC
        """,
        (cutoff, cutoff),
    ).fetchall()
    return [dict(row) for row in rows]


# --------------------------------------------------------------------------
# Tasks
# --------------------------------------------------------------------------


def done_cutoff(days: int) -> float | None:
    """The instant before which a finished task is no longer drawn.

    None when the setting is zero, which every query below reads as "no cutoff"
    rather than as "hide everything" - the difference between a board that keeps
    its history and a board that looks empty the moment somebody types 0.
    """
    return None if days <= 0 else time.time() - days * 86400.0


def task(conn: sqlite3.Connection, task_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise NotFound(f"no task {task_id}")
    return dict(row)


def tasks(
    conn: sqlite3.Connection,
    project_id: int,
    statuses: Sequence[str] | None = None,
    hide_done: bool = True,
) -> list[dict[str, Any]]:
    """One project's cards, in the order the columns draw them.

    `hide_done` is what the settings screen controls, and it is a filter on the
    read and never a delete: the task stays in the table, the age at which it
    stops being drawn can be changed back, and the card returns. Nothing in this
    application removes a finished task except somebody pressing delete on it.

    Falling back to `updated_at` where `completed_at` is null covers the rows a
    future import - or a hand-edited database - could leave without one. Without
    the fallback those cards would compare as older than any cutoff and vanish
    the day the setting was first turned on.
    """
    where = ["project_id = ?"]
    args: list[Any] = [project_id]
    if statuses:
        where.append("status IN ({})".format(",".join("?" * len(statuses))))
        args.extend(statuses)
    cutoff = done_cutoff(done_hide_days(conn)) if hide_done else None
    if cutoff is not None:
        where.append("(status != 'done' OR COALESCE(completed_at, updated_at) >= ?)")
        args.append(cutoff)
    clauses = " AND ".join(where)
    rows = conn.execute(
        f"SELECT * FROM tasks WHERE {clauses} ORDER BY {COLUMN_ORDER}, position, id", args
    ).fetchall()
    return [dict(row) for row in rows]


def next_position(conn: sqlite3.Connection, project_id: int, status: str) -> float:
    """One gap past the last card in a column - where a new card lands.

    The bottom rather than the top. A queue is read downwards, the card you just
    added is the one you know about, and an arrival that pushes everything down
    moves the card somebody was about to click.
    """
    row = conn.execute(
        "SELECT MAX(position) AS edge FROM tasks WHERE project_id = ? AND status = ?",
        (project_id, status),
    ).fetchone()
    edge = row["edge"]
    return POSITION_GAP if edge is None else float(edge) + POSITION_GAP


def create_task(
    conn: sqlite3.Connection,
    project_id: int,
    title: str,
    detail: str = "",
    status: str = QUEUED,
    source: str = SOURCE_MANUAL,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Add one card, and refuse an empty one.

    A blank title is refused here rather than defaulted to "Untitled": a card
    with no words on it is one nobody can act on, and the way it arrives is a
    caller passing a field it never filled in - which is a bug worth hearing
    about at the point it happens.
    """
    clean = config.clean_title(title)
    if not clean:
        raise ValueError("a task needs a title")
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")
    now = time.time()
    with transaction(conn):
        position = next_position(conn, project_id, status)
        cursor = conn.execute(
            """
            INSERT INTO tasks (project_id, title, detail, status, position, source,
                               session_id, created_at, updated_at, started_at, completed_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                clean,
                str(detail or "")[: config.DETAIL_MAX],
                status,
                position,
                source,
                session_id,
                now,
                now,
                now if status == IN_PROGRESS else None,
                now if status == DONE else None,
            ),
        )
        touch_project(conn, project_id, now)
    return task(conn, int(cursor.lastrowid))


def update_task(
    conn: sqlite3.Connection,
    task_id: int,
    title: str | None = None,
    detail: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Edit a card in place, moving it to the foot of its new column if it moved.

    A status change is a move, and a move needs a position: without one the card
    would keep the position it held in its old column and land in the middle of
    the new one, at whatever height it happened to have. The foot is where a card
    dropped by a button rather than by hand belongs - it is the newest thing in
    that column.
    """
    current = task(conn, task_id)
    now = time.time()
    fields: dict[str, Any] = {"updated_at": now}

    if title is not None:
        clean = config.clean_title(title)
        if not clean:
            raise ValueError("a task needs a title")
        fields["title"] = clean
    if detail is not None:
        fields["detail"] = str(detail)[: config.DETAIL_MAX]
    if status is not None and status != current["status"]:
        if status not in STATUSES:
            raise ValueError(f"unknown status {status!r}")
        fields["status"] = status
        fields.update(stamps(current, status, now))

    with transaction(conn):
        if "status" in fields:
            fields["position"] = next_position(conn, current["project_id"], status)
        assignments = ", ".join(f"{name} = ?" for name in fields)
        conn.execute(
            f"UPDATE tasks SET {assignments} WHERE id = ?", (*fields.values(), task_id)
        )
        touch_project(conn, current["project_id"], now)
    return task(conn, task_id)


def stamps(current: dict[str, Any], status: str, now: float) -> dict[str, Any]:
    """When a card entered progress and when it was finished.

    Set on the first transition into each state and then left alone, so a card
    dragged out of done and back again keeps the moment it was actually
    finished rather than the moment somebody last touched it. Moving a card
    back OUT of done clears the completion stamp, because a task that is in the
    queue and also carries a completion date is a row that reads as finished to
    every query that asks by date - including the one that decides whether to
    hide it.
    """
    fields: dict[str, Any] = {}
    if status == IN_PROGRESS and current["started_at"] is None:
        fields["started_at"] = now
    if status == DONE:
        fields["completed_at"] = current["completed_at"] or now
        if current["started_at"] is None:
            fields["started_at"] = now
    else:
        fields["completed_at"] = None
    return fields


def move_task(conn: sqlite3.Connection, task_id: int, status: str, index: int) -> dict[str, Any]:
    """Drop a card into a column at a given index.

    The index is where the card ends up among the cards that will be in that
    column AFTER the move, counted from the top, and the server works the
    position out rather than the browser. Two reasons: the browser would have to
    know the neighbours' float positions to take a midpoint, which means shipping
    them to every client and trusting what comes back; and two people dragging in
    the same column at once would each compute against a list the other has
    already changed.

    Positions are renumbered across the column on every move. It is one small
    UPDATE per card in one column of one project - a board where that is
    expensive is a board with a column nobody could read anyway - and it buys a
    guarantee no midpoint scheme has: the positions after any move are exactly
    the gaps this module started with, so they cannot converge.
    """
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")
    current = task(conn, task_id)
    now = time.time()
    with transaction(conn):
        column = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM tasks WHERE project_id = ? AND status = ? AND id != ? "
                "ORDER BY position, id",
                (current["project_id"], status, task_id),
            ).fetchall()
        ]
        where = max(0, min(int(index), len(column)))
        column.insert(where, task_id)
        for slot, member in enumerate(column):
            conn.execute(
                "UPDATE tasks SET position = ? WHERE id = ?", ((slot + 1) * POSITION_GAP, member)
            )
        fields: dict[str, Any] = {"updated_at": now}
        if status != current["status"]:
            fields["status"] = status
            fields.update(stamps(current, status, now))
        assignments = ", ".join(f"{name} = ?" for name in fields)
        conn.execute(f"UPDATE tasks SET {assignments} WHERE id = ?", (*fields.values(), task_id))
        touch_project(conn, current["project_id"], now)
    return task(conn, task_id)


def delete_task(conn: sqlite3.Connection, task_id: int) -> None:
    current = task(conn, task_id)
    with transaction(conn):
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        touch_project(conn, current["project_id"])


# --------------------------------------------------------------------------
# The todo mirror
# --------------------------------------------------------------------------


def mirror_todos(
    conn: sqlite3.Connection,
    project_id: int,
    session_id: str,
    todos: Iterable[dict[str, Any]],
) -> dict[str, int]:
    """Bring one session's mirrored cards in line with Claude's own todo list.

    TodoWrite sends the WHOLE list every time and its entries carry no stable
    id, so the title is the identity - matched within this project and this
    session, never across either. Two sessions working the same repository keep
    their own cards, and a title reused a week later in another session is a new
    card rather than a resurrection of an old one.

    An entry that has disappeared from the list is withdrawn only if it is still
    queued, and only if the mirror is what created it. A queued card that Claude
    has dropped from its plan was never started and holding onto it leaves the
    board accumulating work nobody intends to do; a card that reached progress or
    done is a thing that happened, and the board is the only place it is written
    down. Anything a person typed or an MCP call filed is never touched here at
    all, whatever its title.
    """
    now = time.time()
    live: dict[str, str] = {}
    for entry in todos:
        title = config.clean_title(entry.get("content", ""))
        status = TODO_STATUS.get(str(entry.get("status", "")), QUEUED)
        # First spelling wins. A list with the same title twice is a list Claude
        # wrote, not an error worth refusing, and the alternative - the later
        # entry overwriting the earlier - would flicker the card's column
        # between two states on every write.
        if title and title not in live:
            live[title] = status

    counts = {"added": 0, "updated": 0, "withdrawn": 0}
    with transaction(conn):
        existing = {
            row["title"]: row
            for row in conn.execute(
                "SELECT * FROM tasks WHERE project_id = ? AND session_id = ? AND source = ? "
                "ORDER BY position, id",
                (project_id, session_id, SOURCE_TODO),
            ).fetchall()
        }

        for title, status in live.items():
            row = existing.get(title)
            if row is None:
                position = next_position(conn, project_id, status)
                conn.execute(
                    """
                    INSERT INTO tasks (project_id, title, detail, status, position, source,
                                       session_id, created_at, updated_at,
                                       started_at, completed_at)
                         VALUES (?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        title,
                        status,
                        position,
                        SOURCE_TODO,
                        session_id,
                        now,
                        now,
                        now if status in (IN_PROGRESS, DONE) else None,
                        now if status == DONE else None,
                    ),
                )
                counts["added"] += 1
                continue
            if row["status"] == status:
                continue
            fields: dict[str, Any] = {
                "status": status,
                "updated_at": now,
                "position": next_position(conn, project_id, status),
            }
            fields.update(stamps(dict(row), status, now))
            assignments = ", ".join(f"{name} = ?" for name in fields)
            conn.execute(
                f"UPDATE tasks SET {assignments} WHERE id = ?", (*fields.values(), row["id"])
            )
            counts["updated"] += 1

        gone = [
            row["id"]
            for title, row in existing.items()
            if title not in live and row["status"] == QUEUED
        ]
        if gone:
            slots = ",".join("?" * len(gone))
            conn.execute(f"DELETE FROM tasks WHERE id IN ({slots})", gone)
            counts["withdrawn"] = len(gone)

        if counts["added"] or counts["updated"] or counts["withdrawn"]:
            touch_project(conn, project_id, now)
    return counts
