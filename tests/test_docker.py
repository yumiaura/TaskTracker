#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The container files: what they publish, mount and copy.

Read as text rather than run. Building an image in the test suite would make it
need Docker and a network; these are the properties that are checkable without
either and expensive to get wrong - above all, that the port is published on
127.0.0.1 and nowhere else.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tasktracker.server.app import MCP_PATH

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = (ROOT / "docker-compose.yml").read_text()
DOCKERFILE = (ROOT / "Dockerfile").read_text()
ENTRYPOINT = (ROOT / "docker" / "entrypoint.sh").read_text()


def test_the_port_is_published_on_loopback_only():
    block = COMPOSE.split("ports:")[1].split("environment:")[0]
    published = re.findall(r'^\s*-\s*"([^"]+)"\s*$', block, re.MULTILINE)
    assert published == ["127.0.0.1:8787:8787"]


def test_the_plugin_points_at_the_port_and_path_the_container_serves():
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    servers = manifest["mcpServers"]
    assert servers["tasktracker"]["url"] == f"http://127.0.0.1:8787{MCP_PATH}"
    assert "--port 8787" in ENTRYPOINT


def test_the_home_is_mounted_read_only_and_only_the_board_is_writable():
    assert "- ${HOME}:${HOME}:ro" in COMPOSE
    assert "- ${HOME}/.claude/tasktracker:${HOME}/.claude/tasktracker" in COMPOSE
    assert "TASKTRACKER_HOME: ${HOME}/.claude/tasktracker" in COMPOSE


def test_the_server_runs_as_the_owner_of_the_home_not_as_root():
    """A root-owned tasks.db is one the hook on the host can no longer write.

    And the hook swallows that failure by design - so the board would stop
    filling with nothing anywhere saying why.
    """
    assert "exec setpriv --reuid=" in ENTRYPOINT
    assert 'stat -c %u "$TASKTRACKER_OWNER"' in ENTRYPOINT


def test_everything_the_dockerfile_copies_is_let_through_the_ignore_file():
    ignored = (ROOT / ".dockerignore").read_text()
    copied = re.findall(r"^COPY\s+(.+?)\s+\S+$", DOCKERFILE, re.MULTILINE)
    sources = {part for line in copied for part in line.split()}
    assert sources == {"pyproject.toml", "README.md", "LICENSE", "src", "docker/entrypoint.sh"}
    for source in sources:
        top = source.split("/")[0]
        assert f"!{top}" in ignored, f"{source} is copied but ignored"


def test_the_card_mode_reaches_the_container_from_env():
    assert "TASKTRACKER_CARDS: ${TASKTRACKER_CARDS:-claude}" in COMPOSE
    example = (ROOT / ".env.example").read_text()
    assert "TASKTRACKER_CARDS=claude" in example
    assert "prompts" in example
    # The real .env is local; the example is the one in the history.
    assert ".env" in (ROOT / ".gitignore").read_text().splitlines()
