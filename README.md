EN | [RU](docs/README_RU.md) | [CN](docs/README_CN.md)

## TaskTracker: a board Claude fills in for itself 🗂️

<p class="badges">
  <img src="https://img.shields.io/badge/Claude%20Code-plugin-D97757?logo=anthropic&logoColor=white" alt="Claude Code plugin">
  <img src="https://img.shields.io/badge/MCP-HTTP%20server-111111" alt="MCP HTTP server">
  <img src="https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white" alt="Docker Compose">
  <img src="https://img.shields.io/badge/storage-SQLite-003B57?logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License">
</p>

Claude Code keeps a task list while it works - and that list dies with the session.<br>
TaskTracker mirrors it onto a board per project, and gives Claude MCP tools to read the queue back next time.<br>
The board is a web panel: projects, then three columns - **QUEUE**, **IN PROGRESS**, **DONE**.<br>
A project appears the moment you start Claude in it; the panel refreshes itself.

<img src="docs/board.png" width="800" alt="One project's board: three columns, drag and drop between them">

<img src="docs/projects.png" width="800" alt="The projects table: each project with its QUEUE, IN PROGRESS and DONE counts">

How it runs - a real Claude Code session, the panel never reloaded: Claude plans the work
and the tasks land in **QUEUE** (1), each one moves to **IN PROGRESS** before Claude starts on
it (2), and to **DONE** when it is finished (3).

<img src="docs/process.png" width="800" alt="Three moments of one session: three tasks in QUEUE, the first in IN PROGRESS, all three in DONE">

Click a task - a card on the board or a row in the table - to open it: edit the title and the
detail, change the status, or delete it. Cards can also be dragged between columns.

<img src="docs/dialog.png" width="560" alt="The task dialog: title, detail, status, and DELETE, CANCEL and SAVE">

## 🚀 Quick start

**1. Start the board** - the panel and the MCP server, in one container:

```bash
cd TaskTracker
docker compose up -d
```

The panel is at http://127.0.0.1:8787. Where the cards come from is set in `.env` - see
[below](#-where-the-cards-come-from).

**2. Install the plugin** - once, from the same directory; it works in every project:

```bash
claude plugin marketplace add ./
claude plugin install tasktracker@tasktracker
```

**3. Restart Claude Code.** From then on every project you open Claude in is on the board,
and its cards follow Claude's work.

**4. Check it works** - in Claude Code:

- `/mcp` - `plugin:tasktracker:tasktracker` is listed as connected.
- `/tasktracker:tasks` - Claude reports this project's queue (empty on a new board).
- Ask Claude to *"make a todo list of three steps for …"*, then open http://127.0.0.1:8787 -
  the project is there, with the three cards marked `TODO`.

**Updating** - after pulling changes, from the checkout:

```bash
docker compose up -d --build
claude plugin marketplace update tasktracker
claude plugin uninstall tasktracker@tasktracker
claude plugin install tasktracker@tasktracker
```

Then restart Claude Code.

## 🃏 Where the cards come from

One setting, `TASKTRACKER_CARDS` in `.env` beside `docker-compose.yml`
(copy [`.env.example`](.env.example)). After changing it, rebuild and restart Claude Code.

```bash
TASKTRACKER_CARDS=claude    # the default
TASKTRACKER_CARDS=prompts
```

- **`claude`** - the cards are Claude's own tasks. The plugin tells Claude, at the start of
  every session and again with every prompt, to plan any work of more than one step as tasks
  and keep their status current; each task is a card, marked `TODO`, that moves as Claude
  works. If Claude still does work - Bash, Edit, Write - without a single task, the prompt
  itself lands in **DONE**, marked `PROMPT`. A question answered by reading makes no card.
- **`prompts`** - every prompt you send is a card, marked `PROMPT`: its first line is the
  title, the whole prompt the detail. It is in **IN PROGRESS** while Claude answers and in
  **DONE** when it stops. Slash commands make no card, and Claude's own tasks are not shown.

<img src="docs/prompts.png" width="800" alt="Prompts mode: three prompts as cards, one in IN PROGRESS and two in DONE">

## 🧪 Development

```bash
pip install -e '.[dev]'
pre-commit install              # ruff and the test suite before every commit
pytest --cov                    # the suite, with coverage and the lines it missed
```

`ruff check` and `ruff format` keep the style; the settings are in `pyproject.toml`.
GitHub Actions (`.github/workflows/ci.yml`) runs ruff and `pytest --cov` on Python 3.11 and
3.12 for every pull request and every push to `main`.

The panel has no build step: `src/tasktracker/www` is served as it is, and every library is
vendored there. The version stays **0.0.1** - see [`CLAUDE.md`](CLAUDE.md) for why, and for
how a change reaches an installed plugin.

### License

[MIT](LICENSE). Montserrat is under the [SIL Open Font License](src/tasktracker/www/fonts/OFL.txt).
