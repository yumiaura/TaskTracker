#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`tasktracker` - what the plugin and the operator actually run.

Subcommands import what they need and nothing else. The hook runs on every
TodoWrite Claude performs, and it must not pay the cost of importing fastapi
and uvicorn to write one row.
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import __version__, config


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="tasktracker", description=__doc__.splitlines()[0])
    root.add_argument("--version", action="version", version=f"tasktracker {__version__}")
    subs = root.add_subparsers(dest="command", required=True)

    serve = subs.add_parser("serve", help="run the web panel")
    serve.add_argument("--host", default=config.default_host())
    serve.add_argument("--port", type=int, default=config.default_port())
    serve.add_argument(
        "--open",
        dest="open_browser",
        action="store_true",
        help="open the panel in a browser once it is listening",
    )
    serve.add_argument("--log-level", default="info")

    subs.add_parser("where", help="print the database path")
    return root


def serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .server.app import build

    if args.open_browser:
        open_when_ready(args.host, args.port)
    # `build()` rather than an import string: passing "tasktracker.server.app:app"
    # would have uvicorn import this package a second time in a reloader child,
    # and the panel has no reload mode to justify that.
    uvicorn.run(build(), host=args.host, port=args.port, log_level=args.log_level)
    return 0


def open_when_ready(host: str, port: int) -> None:
    """Open a browser once the port answers, from a thread.

    Not before: a browser pointed at a socket that is not listening yet shows
    its own connection-refused page and stays there, and the operator's first
    sight of the board is an error they have to reload past. The thread is a
    daemon, so a server that fails to bind at all takes it down with the process
    rather than leaving it polling a port nobody will ever open.
    """
    import socket
    import threading
    import time
    import webbrowser

    def wait() -> None:
        target = host if host != "0.0.0.0" else "127.0.0.1"  # noqa: S104 - not a bind
        deadline = time.time() + 15
        while time.time() < deadline:
            with socket.socket() as probe:
                probe.settimeout(0.25)
                if probe.connect_ex((target, port)) == 0:
                    webbrowser.open(f"http://{target}:{port}/")
                    return
            time.sleep(0.25)

    threading.Thread(target=wait, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    if args.command == "serve":
        return serve(args)
    if args.command == "where":
        print(config.db_path())
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
