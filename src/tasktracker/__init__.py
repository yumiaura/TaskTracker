#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TaskTracker - a task board Claude fills in for itself.

The package has four entry points and one store between them:

  * `tasktracker.mcp_server` - the MCP stdio server Claude calls to queue,
    start, finish and read tasks.
  * `tasktracker.hook` - the PostToolUse hook that mirrors Claude Code's own
    todo list onto the board, so the common case needs no tool call at all.
  * `tasktracker.server` - FastAPI, serving the panel and the REST API it
    reads.
  * `tasktracker.cli` - what the plugin and the operator actually run.

Nothing here imports fastapi or mcp at module scope. The hook runs on every
TodoWrite and must not pay for a web framework it never touches.
"""

__version__ = "0.0.1"
