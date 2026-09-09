---
description: Open the TaskTracker web panel in a browser.
allowed-tools: Bash(tasktracker serve:*), Bash(python3 -m tasktracker.cli serve:*), Bash(curl:*)
---

Open the board's web panel.

1. Check whether it is already listening:
   `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8787/api/health`
   A `200` means it is already up - just give the user the URL
   (http://127.0.0.1:8787/) and stop.
2. Otherwise start it in the background and open it:
   `tasktracker serve --open`
   If that command is not on PATH, use
   `PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/src" python3 -m tasktracker.cli serve --open`
   which needs fastapi and uvicorn installed in that interpreter.
3. Tell the user the URL. Do not wait on the process - it stays in the
   foreground of the shell you started it in and serves until it is stopped.

The panel binds to 127.0.0.1 only and has no authentication, which is the whole
reason it binds there. Do not offer to change the host.
