EN | [RU](docs/README_RU.md) | [CN](docs/README_CN.md)

## TaskTracker: a board Claude fills in for itself 🗂️

<p class="badges">
  <img src="https://img.shields.io/badge/Claude%20Code-plugin-D97757?logo=anthropic&logoColor=white" alt="Claude Code plugin">
  <img src="https://img.shields.io/badge/MCP-HTTP%20server-111111" alt="MCP HTTP server">
  <img src="https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white" alt="Docker Compose">
  <img src="https://img.shields.io/badge/storage-SQLite-003B57?logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License">
</p>

Claude Code keeps a todo list while it works - and that list dies with the session.<br>
TaskTracker mirrors it onto a board per project, and gives Claude MCP tools to read the queue back next time.<br>
The board is a web panel: projects, then three columns - **queued**, **in progress**, **done**.

<img src="docs/board.png" width="800" alt="One project's board: three columns, drag and drop between them">

<img src="docs/projects.png" width="800" alt="The projects table: name, when it was last touched, how many are queued">

How it runs - a real Claude Code session, the panel never reloaded: Claude plans the work
and the tasks land in **QUEUE** (1), each one moves to **IN PROGRESS** before Claude starts on
it (2), and to **DONE** when it is finished (3).

<img src="docs/process.png" width="800" alt="Three moments of one session: three tasks in QUEUE, the first in IN PROGRESS, all three in DONE">

## 🚀 Quick start

**1. Start the board** - the panel and the MCP server, in one container:

```bash
cd TaskTracker
docker compose up -d
```

The panel is at http://127.0.0.1:8787. Where the cards come from - Claude's own tasks, or
every prompt you send - is set in `.env`; see [`.env.example`](.env.example).

**2. Install the plugin** - once, from the same directory; it works in every project:

```bash
claude plugin marketplace add ./
claude plugin install tasktracker@tasktracker
```

**3. Restart Claude Code.** From then on every todo Claude writes lands on the board.

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

### License

[MIT](LICENSE). Montserrat is under the [SIL Open Font License](src/tasktracker/www/fonts/OFL.txt).
