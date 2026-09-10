#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The `tasktracker` command: its three subcommands and how `serve` starts.

Nothing here starts a real server - uvicorn and the MCP server are replaced -
because what the command owns is the wiring: which arguments reach which call,
and what the environment changes about them.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest

from tasktracker import __version__, cli, config


def test_where_prints_the_database_path(home, capsys):
    assert cli.main(["where"]) == 0
    assert capsys.readouterr().out.strip() == str(config.db_path())


def test_version_names_the_package_version(capsys):
    with pytest.raises(SystemExit) as stopped:
        cli.main(["--version"])
    assert stopped.value.code == 0
    assert capsys.readouterr().out.strip() == f"tasktracker {__version__}"


def test_a_subcommand_is_required():
    with pytest.raises(SystemExit) as stopped:
        cli.main([])
    assert stopped.value.code == 2


def test_serve_takes_its_defaults_from_the_environment(monkeypatch):
    monkeypatch.setenv(config.HOST_ENV, "127.0.0.2")
    monkeypatch.setenv(config.PORT_ENV, "9123")
    args = cli.parser().parse_args(["serve"])
    assert (args.host, args.port, args.open_browser) == ("127.0.0.2", 9123, False)


def test_serve_hands_the_app_and_its_arguments_to_uvicorn(home, monkeypatch):
    import uvicorn

    started = {}
    opened = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: started.update(app=app, **options))
    monkeypatch.setattr(cli, "open_when_ready", lambda host, port: opened.append((host, port)))

    assert cli.main(["serve", "--port", "9001", "--log-level", "warning", "--open"]) == 0
    assert started["port"] == 9001
    assert started["log_level"] == "warning"
    assert started["host"] == config.default_host()
    assert started["app"].title == "TaskTracker"
    assert opened == [(config.default_host(), 9001)]


def test_serve_opens_no_browser_unless_asked(home, monkeypatch):
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda app, **options: None)
    monkeypatch.setattr(cli, "open_when_ready", lambda host, port: pytest.fail("opened"))
    assert cli.main(["serve"]) == 0


def test_mcp_runs_the_stdio_server(monkeypatch):
    from tasktracker import mcp_server

    ran = []
    monkeypatch.setattr(mcp_server, "main", lambda: ran.append(True) or 0)
    assert cli.main(["mcp"]) == 0
    assert ran == [True]


def test_the_browser_opens_once_the_port_answers(monkeypatch):
    """Not before: a browser pointed at a closed port shows its own error page."""
    import webbrowser

    opened = []
    monkeypatch.setattr(webbrowser, "open", opened.append)

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        # 0.0.0.0 is where the server binds, not somewhere a browser can go.
        cli.open_when_ready("0.0.0.0", port)
        deadline = time.time() + 5
        while not opened and time.time() < deadline:
            time.sleep(0.05)

    assert opened == [f"http://127.0.0.1:{port}/"]
    assert threading.active_count() >= 1
