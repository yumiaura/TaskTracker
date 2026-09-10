---
description: Open the TaskTracker web panel in a browser.
allowed-tools: Bash(curl:*), Bash(xdg-open:*), Bash(open:*)
---

Open the board's web panel.

1. Check whether it is up:
   `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8787/api/health`
2. A `200` means it is running. Open http://127.0.0.1:8787/ in the browser with
   `xdg-open` (Linux) or `open` (macOS), and give the user the URL.
3. Anything else means the board's container is not running. Tell the user to
   run `docker compose up -d` in their TaskTracker checkout, then open
   http://127.0.0.1:8787/. Do not start it yourself: the container is built from
   that checkout, and a second copy started from somewhere else would fight the
   first one for the port.
