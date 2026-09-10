#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Where the tracker keeps its data, and how a directory becomes a project.

Nothing in this module reads the database or the network. It answers two
questions the rest of the package keeps asking - "which file" and "which
project" - and it answers them the same way from the MCP server, from the hook
and from the web server, which are three processes that never see each other
and must still agree.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# The whole of the tracker's state, in one directory beside Claude's own.
#
# Under ~/.claude rather than in a checkout, because the panel's entire point is
# that it spans projects: a database inside one repository can only ever hold
# that repository's tasks, and the first screen of this application is the list
# of all of them.
#
# The environment variable exists for the tests, which must not write into the
# operator's real board, and for anybody running two boards on purpose. It is
# read on every call rather than captured at import: the tests set it per case,
# and a value frozen at import would leak the first case's directory into all
# the rest.
HOME_ENV = "TASKTRACKER_HOME"
DEFAULT_HOME = Path.home() / ".claude" / "tasktracker"

# Loopback, and not configurable to anything else by accident.
#
# The panel has no authentication at all - it is a board of your own task
# titles, on your own machine - and the reason that is acceptable is this bind.
# A default of 0.0.0.0 would put an unauthenticated write API on the office
# network, so the host is an explicit choice made by whoever passes --host and
# never a default anybody backs into.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
HOST_ENV = "TASKTRACKER_HOST"
PORT_ENV = "TASKTRACKER_PORT"

# Where the board's cards come from, chosen in the .env beside docker-compose.yml.
#
#   claude  - Claude is told to plan its work as tasks, and the cards are
#             Claude's own tasks (TaskCreate/TaskUpdate, or TodoWrite).
#   prompts - every prompt sent to Claude is a card: IN PROGRESS while Claude
#             works on it, DONE when it stops. Claude's tasks are not mirrored.
CARDS_ENV = "TASKTRACKER_CARDS"
CARDS_CLAUDE = "claude"
CARDS_PROMPTS = "prompts"
CARDS_MODES = (CARDS_CLAUDE, CARDS_PROMPTS)
# The settings row the server writes the mode into, for the hooks on the host -
# which run outside the container and never see its environment.
CARDS_SETTING = "cards"

# What claude mode tells Claude at the start of every session: keep a task list
# at all. Without it Claude keeps one only when it judges the work big enough,
# and a session of questions and small edits leaves its project on the board
# with no cards.
PLAN_INSTRUCTIONS = """
TaskTracker is mirroring this session's task list onto the user's task board.
Before you start anything that takes more than one step, create one task per
step with TaskCreate. Set each to in_progress with TaskUpdate when you start it
and to completed when it is done. Do this even for work you could finish
without a list - the list is what the user reads to follow along.
""".strip()

# How long a finished task stays on the board, in days, before the panel stops
# drawing it. Zero means never hide. The task itself is not deleted by this and
# never has been - see `store.visible_tasks`.
DEFAULT_DONE_HIDE_DAYS = 7

# What marks the top of a project. Checked in this order and the first hit
# wins, so a repository with a `.hg` directory left over from a conversion is
# still rooted at its `.git`.
ROOT_MARKERS = (".git", ".hg", ".svn")


def home() -> Path:
    """The directory holding the database, created if it is not there yet."""
    raw = os.environ.get(HOME_ENV, "").strip()
    directory = Path(raw).expanduser() if raw else DEFAULT_HOME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def db_path() -> Path:
    """The one SQLite file every entry point opens."""
    return home() / "tasks.db"


def default_host() -> str:
    value = os.environ.get(HOST_ENV, "").strip()
    return value or DEFAULT_HOST


def default_port() -> int:
    """The port the panel listens on, falling back rather than refusing to start.

    A misspelled `TASKTRACKER_PORT=87 87` is a typo in a shell profile, not a
    reason for a board that will not open - and the failure would be reported
    where nobody is looking, because this is started in the background by a
    plugin. The default is used and the process comes up.
    """
    raw = os.environ.get(PORT_ENV, "").strip()
    if not raw:
        return DEFAULT_PORT
    try:
        port = int(raw)
    except ValueError:
        return DEFAULT_PORT
    return port if 1 <= port <= 65535 else DEFAULT_PORT


def cards_mode(raw: str | None = None) -> str:
    """The card mode, falling back to `claude` for anything it does not know.

    As with the port: a typo in .env is not a reason for a board that stops
    filling. The default is the mode the board was built around.
    """
    value = (os.environ.get(CARDS_ENV, "") if raw is None else raw).strip().lower()
    return value if value in CARDS_MODES else CARDS_CLAUDE


def project_root(start: str | os.PathLike[str] | None = None) -> Path:
    """The project a directory belongs to: its repository root, or itself.

    Walking up for a marker rather than taking the working directory verbatim is
    what keeps one repository from becoming four projects. Claude is routinely
    launched in a subdirectory - `src/`, `web/`, wherever the work is - and a
    tracker that keyed on the working directory would open a new board for each
    of them, all of them named after a folder nobody thinks of as the project.

    A directory under no version control at all is its own project. That is the
    honest answer: there is nothing above it that says otherwise, and refusing
    to track a scratch directory would mean the queue quietly loses tasks for
    exactly the kind of work most likely to be forgotten.
    """
    here = Path(start).expanduser() if start else Path.cwd()
    try:
        here = here.resolve()
    except OSError:
        # A path that no longer exists, or one the process cannot stat. There is
        # nothing above it to walk, so it is its own project.
        return Path(here)
    if here.is_file():
        here = here.parent
    for candidate in (here, *here.parents):
        for marker in ROOT_MARKERS:
            if (candidate / marker).exists():
                return candidate
    return here


def project_name(path: str | os.PathLike[str]) -> str:
    """What the board calls a project: the name of its directory.

    Not the git remote. A remote is a URL, half the projects on a machine have
    none, and two checkouts of the same repository - a worktree and its origin -
    would collapse into one board while being two working trees. The directory
    name is what the operator already calls the project in every other window
    they have open.

    The filesystem root has no name of its own, so it falls back to the path,
    which is at least unambiguous on the projects screen.
    """
    root = Path(path)
    return root.name or str(root)


# A title is a line on a card, and a card is one line tall.
#
# The cap is not about storage: it is about a board where one pasted stack trace
# makes a column unreadable and pushes every other card off the screen. What
# does not fit the title belongs in the detail, which the card does not draw.
TITLE_MAX = 200
DETAIL_MAX = 20000

# Collapse anything that would break a card into one line into a single space.
# `\s` covers the newline, the tab and the vertical whitespace a paste brings
# with it; the detail field is left exactly as it was typed.
TITLE_WHITESPACE = re.compile(r"\s+")


def clean_title(raw: str) -> str:
    """One line, trimmed, capped - or an empty string, which callers refuse."""
    text = TITLE_WHITESPACE.sub(" ", str(raw or "")).strip()
    return text[:TITLE_MAX]
