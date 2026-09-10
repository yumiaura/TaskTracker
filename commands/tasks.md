---
description: Show this project's TaskTracker board - what is queued and what is in flight.
allowed-tools: mcp__tasktracker__tasks_queued, mcp__tasktracker__projects_list
---

Read this project's board and report it.

1. Call `tasks_queued` with `project` set to the absolute path of the directory
   this session is working in. The board runs in a container and cannot see that
   directory on its own.
2. Report what comes back as two short lists - IN PROGRESS first, then QUEUED -
   with each task's id in front of its title, so the user can name one back to
   you.
3. If both lists are empty, say so in one line. Do not offer to add anything
   unless the user asks.

If the tool cannot be reached, the board's container is not running: tell the
user to run `docker compose up -d` in their TaskTracker checkout, and stop.

Do not start any of the work. This command answers a question; it does not pick
up the queue.
