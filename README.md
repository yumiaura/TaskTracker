EN | [RU](docs/README_RU.md) | [CN](docs/README_CN.md)

## TaskTracker: a board Claude fills in for itself 🗂️

<p class="badges">
  <img src="https://img.shields.io/badge/Claude%20Code-plugin-D97757?logo=anthropic&logoColor=white" alt="Claude Code plugin">
  <img src="https://img.shields.io/badge/MCP-stdio%20server-111111" alt="MCP stdio server">
  <img src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/storage-SQLite-003B57?logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License">
</p>

Claude Code already keeps a todo list while it works - and that list dies with the session.<br>
TaskTracker keeps it: every todo Claude writes is mirrored onto a board, per project.<br>
Next session it reads the queue back, and can put work on the board itself through MCP tools.<br>
You watch it happen in a local web panel: projects, then three columns - **queued**, **in progress**, **done**.

<img src="docs/board.png" width="800" alt="One project's board: three columns, drag and drop between them">

<img src="docs/projects.png" width="800" alt="The projects table: name, when it was last touched, how many are queued">

## 🚀 Quick start

```bash
pip install -e .
```

Then, in Claude Code:

```
/plugin marketplace add /path/to/TaskTracker
/plugin install tasktracker@tasktracker
```

Restart, and from then on every `TodoWrite` lands on the board, the `tasktracker` MCP
server is connected, `/tasktracker:tasks` reports the queue for the project you are in,
and `/tasktracker:tasks-panel` opens the panel.

By hand:

```bash
tasktracker serve --open      # http://127.0.0.1:8787/
tasktracker where             # where the database is
```

It binds to `127.0.0.1` and has no authentication, which is the reason it binds there.
`TASKTRACKER_HOST` and `TASKTRACKER_PORT` override the defaults.

## 🧩 How the board fills itself

1. **The hook.** A `PostToolUse` hook on `TodoWrite` mirrors Claude's own todo list onto
   the board of whatever project it is working in. Nothing to call, nothing to remember.
   Standard library only, so it works before anything is installed.
2. **The MCP tools.** For work that is *not* part of the current plan - a follow-up,
   something noticed in passing, something to pick up next session - and for reading the
   queue back when a session starts.
3. **The panel.** Type a card, drag it between columns, edit or delete it.

## 🛠 MCP tools

| Tool | What it does |
| --- | --- |
| `tasks_queued` | What is waiting and what is in flight. Call it when you start on a project. |
| `tasks_all` | Every card, finished ones included. |
| `task_add` | Put a task on the board. |
| `task_start` / `task_done` | Move it into the in-progress column / mark it finished. |
| `task_update` / `task_delete` | Edit the title, detail or column / remove a card. |
| `projects_list` | Every project the board knows, with its counts. |

Each resolves its project from the directory the session is running in, walked up to the
repository root - so a session in `~/src/app/web` files against `app`. Every tool also
takes an explicit `project`: a name, a path, or an id.

## ⚙️ Settings

One setting, on the settings screen: **how many days a finished task stays on the board**.
It is a filter on what the API sends, never a delete - raise the number and the cards come
back. `0` keeps every finished task for good.

The theme and the board/table choice live in the browser instead, because they are about
the screen you are sitting at.

## 💾 Where the data is

One SQLite file, `~/.claude/tasktracker/tasks.db`, shared by every project;
`TASKTRACKER_HOME` moves it. Three processes write to it - the panel, the MCP server and
the hook - so it runs in WAL mode with a busy timeout and takes its write lock up front.

<details>
<summary><b>HTTP API</b> - everything the panel does, it does through these</summary>

Every failure comes back as `{"error": {"message": "…"}}`.

| Method | Path | |
| --- | --- | --- |
| `GET` | `/api/health` | is it up, and which file is it on |
| `GET` | `/api/projects` | every project with its counts |
| `GET` | `/api/projects/{id}` | one project, its cards and the settings |
| `DELETE` | `/api/projects/{id}` | remove a project and its cards |
| `POST` | `/api/projects/{id}/tasks` | add a card |
| `PATCH` | `/api/tasks/{id}` | edit one; an omitted field is left alone |
| `POST` | `/api/tasks/{id}/move` | `{status, index}` - drop it into a column |
| `DELETE` | `/api/tasks/{id}` | delete a card |
| `GET` `PUT` | `/api/settings` | the hide-after-days setting |

</details>

## 🧪 Development

```bash
pip install -e '.[dev]'
python3 -m pytest tests -q
python3 -m ruff check src tests
```

The panel has no build step: `www/` is served as it is, `.vue` files are loaded in the
browser by `httpVueLoader`, and every library is vendored under `www/vendor`. Four tests
walk every path `index.html`, `main.css` and `app.js` name and assert the file is shipped,
because nothing else would notice a vendored library that went missing until a browser
fetched it.

The palette, the control metrics and the top bar come from
[`wachawo/lmgateway`](https://github.com/wachawo/lmgateway), so the two tools read as one
family.

### License

[MIT](LICENSE). Montserrat is under the SIL Open Font License - see
[`OFL.txt`](src/tasktracker/www/fonts/OFL.txt).
