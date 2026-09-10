#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Where the panel listens, and what counts as one project."""

from __future__ import annotations

import pytest

from tasktracker import config


def test_the_host_defaults_to_loopback(monkeypatch):
    monkeypatch.delenv(config.HOST_ENV, raising=False)
    assert config.default_host() == config.DEFAULT_HOST
    monkeypatch.setenv(config.HOST_ENV, "  ")
    assert config.default_host() == config.DEFAULT_HOST


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", config.DEFAULT_PORT),
        ("9000", 9000),
        # A typo in a shell profile is not a reason for a board that will not
        # open: the default is used instead.
        ("87 87", config.DEFAULT_PORT),
        ("0", config.DEFAULT_PORT),
        ("70000", config.DEFAULT_PORT),
    ],
)
def test_the_port_falls_back_rather_than_refusing(monkeypatch, raw, expected):
    monkeypatch.setenv(config.PORT_ENV, raw)
    assert config.default_port() == expected


def test_a_path_that_does_not_exist_is_its_own_project(tmp_path):
    gone = tmp_path / "never" / "made"
    assert config.project_root(gone) == gone


def test_a_file_belongs_to_the_repository_it_is_in(tmp_path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    source = root / "src" / "module.py"
    source.parent.mkdir()
    source.write_text("")
    assert config.project_root(source) == root.resolve()


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("claude", "claude"),
        ("prompts", "prompts"),
        (" Prompts ", "prompts"),
        ("", "claude"),
        # A typo falls back to the default rather than leaving the board empty.
        ("prompt", "claude"),
    ],
)
def test_the_card_mode_falls_back_to_claude(monkeypatch, raw, expected):
    monkeypatch.setenv(config.CARDS_ENV, raw)
    assert config.cards_mode() == expected
