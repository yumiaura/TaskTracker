# TaskTracker

A task board Claude fills in for itself.

Claude Code already keeps a todo list while it works, and that list dies with
the session. TaskTracker keeps it: every todo Claude writes is mirrored onto a
board, per project, and Claude can read the queue back at the start of the next
session and add to it through MCP tools of its own.

The board is a local web panel — a table of projects, and per project three
columns: **queued**, **in progress**, **done**.

```
PROJECTS                                   PROJECT / BOARD
┌──────────────┬───────────┬────────┐      ┌─────────┬─────────────┬────────┐
│ PROJECT      │ UPDATED   │ QUEUED │      │ QUEUED  │ IN PROGRESS │ DONE   │
├──────────────┼───────────┼────────┤      ├─────────┼─────────────┼────────┤
│ lmrelay      │ 3 min ago │      2 │  ->  │ ▸ card  │ ▸ card      │ ▸ card │
│ TaskTracker  │ 1 day ago │      5 │      │ ▸ card  │             │ ▸ card │
└──────────────┴───────────┴────────┘      └─────────┴─────────────┴────────┘
```

## How the board fills itself

Three ways in, and only the first needs no thought at all:

1. **The hook.** A `PostToolUse` hook on `TodoWrite` mirrors Claude's own todo
   list onto the board of whatever project it is working in. Nothing to call,
   nothing to remember.
2. **The MCP tools.** For work that is *not* part of the current plan — a
   follow-up, something noticed in passing, something to pick up next session —
   and for reading the queue back at the start of a session.
3. **The panel.** Type a card, drag it between columns, edit or delete it.

## Install

The repository is both the Python package and the Claude Code plugin.

```bash
# 1. The dependencies. The hook needs none of these - it is standard library
#    only - but the MCP server needs `mcp`, and the panel needs the other two.
pip install -e .

# 2. The plugin. This directory is its own one-plugin marketplace.
#    In Claude Code:
#      /plugin marketplace add /path/to/TaskTracker
#      /plugin install tasktracker@tasktracker
```

Restart Claude Code. From then on:

- every `TodoWrite` lands on the board,
- the `tasktracker` MCP server is connected,
- `/tasktracker:tasks` reports the queue for the project you are in,
- `/tasktracker:tasks-panel` opens the panel.

### The panel, by hand

```bash
tasktracker serve --open       # http://127.0.0.1:8787/
tasktracker where              # where the database is
```

It binds to `127.0.0.1` and has no authentication, which is the reason it binds
there. `TASKTRACKER_HOST` and `TASKTRACKER_PORT` override the defaults.

## The MCP tools

| Tool | What it does |
| --- | --- |
| `tasks_queued` | What is waiting and what is in flight. Call it when you start on a project. |
| `tasks_all` | Every card, finished ones included. |
| `task_add` | Put a task on the board. |
| `task_start` | Move a task into the in-progress column. |
| `task_done` | Mark a task finished. |
| `task_update` | Edit the title, the detail or the column. |
| `task_delete` | Remove a card that should never have been there. |
| `projects_list` | Every project the board knows, with its counts. |

Each resolves its project from the directory the session is running in, walked
up to the repository root — so a session in `~/src/app/web` files against
`app`. Every tool also takes an explicit `project`: a name, a path, or an id.

## Settings

One setting, on the settings screen: **how many days a finished task stays on
the board**. It is a filter on what the API sends, never a delete — raise the
number and the cards come back. `0` keeps every finished task for good.

Two more live in the browser rather than on the server, because they are about
the screen you are sitting at: the light/dark theme, and whether a project opens
as a board or as a table.

## Where the data is

One SQLite file, `~/.claude/tasktracker/tasks.db`, shared by every project.
`TASKTRACKER_HOME` moves it. Three processes write to it — the panel, the MCP
server and the hook — so it runs in WAL mode with a busy timeout and takes its
write lock up front.

## The HTTP API

Everything the panel does, it does through these. Every failure comes back as
`{"error": {"message": "…"}}`.

| Method | Path | |
| --- | --- | --- |
| `GET` | `/api/health` | is it up, and which file is it on |
| `GET` | `/api/projects` | every project with its counts |
| `GET` | `/api/projects/{id}` | one project, its cards and the settings |
| `DELETE` | `/api/projects/{id}` | remove a project and its cards |
| `POST` | `/api/projects/{id}/tasks` | add a card |
| `PATCH` | `/api/tasks/{id}` | edit one; an omitted field is left alone |
| `POST` | `/api/tasks/{id}/move` | `{status, index}` — drop it into a column |
| `DELETE` | `/api/tasks/{id}` | delete a card |
| `GET` `PUT` | `/api/settings` | the hide-after-days setting |

## Development

```bash
pip install -e '.[dev]'
python3 -m pytest tests -q
python3 -m ruff check src tests
```

The panel has no build step: `www/` is served as it is, `.vue` files are loaded
in the browser by `httpVueLoader`, and every library is vendored under
`www/vendor`. Four tests walk every path `index.html`, `main.css` and `app.js`
name and assert the file is shipped, because nothing else would notice a
vendored library that went missing until a browser fetched it.

The palette, the control metrics and the top bar are taken from
[`wachawo/lmgateway`](https://github.com/wachawo/lmgateway) so the two tools
read as one family.

## Licence

MIT. See `LICENSE`. Montserrat is under the SIL Open Font License — see
`src/tasktracker/www/fonts/OFL.txt`.
