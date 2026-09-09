---
description: Show this project's TaskTracker board - what is queued and what is in flight.
allowed-tools: mcp__tasktracker__tasks_queued, mcp__tasktracker__projects_list
---

Read this project's board and report it.

1. Call `tasks_queued` with no arguments. It resolves the project from the
   directory this session is running in.
2. Report what comes back as two short lists - IN PROGRESS first, then QUEUED -
   with each task's id in front of its title, so the user can name one back to
   you.
3. If both lists are empty, say so in one line. Do not offer to add anything
   unless the user asks.

Do not start any of the work. This command answers a question; it does not pick
up the queue.
