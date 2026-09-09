#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixtures shared by the suite.

Every test runs against a database in a temporary directory, pointed at through
the same environment variable an operator would use to run a second board. The
alternative - passing a path into every call - would leave `config.db_path()`
itself untested, which is the one function whose default reaches the operator's
real tasks.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tasktracker import config, store  # noqa: E402


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """A board of its own, for one test."""
    monkeypatch.setenv(config.HOME_ENV, str(tmp_path / "board"))
    return tmp_path / "board"


@pytest.fixture()
def conn(home):
    connection = store.connect()
    yield connection
    connection.close()


@pytest.fixture()
def project(conn, tmp_path):
    """One project, rooted at a directory that looks like a repository."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    return store.ensure_project(conn, root)
