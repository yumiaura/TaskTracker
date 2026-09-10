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

## 🚀 Quick start

**1. Start the board** - the panel and the MCP server, in one container:

```bash
cd TaskTracker
docker compose up -d
```

The panel is at http://127.0.0.1:8787.

**2. Install the plugin** - once, from the same directory; it works in every project:

```bash
claude plugin marketplace add ./
claude plugin install tasktracker@tasktracker
```

**3. Restart Claude Code.** From then on every todo Claude writes lands on the board.

### License

[MIT](LICENSE). Montserrat is under the [SIL Open Font License](src/tasktracker/www/fonts/OFL.txt).
