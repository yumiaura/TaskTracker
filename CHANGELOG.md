# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## [0.0.1] - 2026-09-10

### Added

- pre-commit hooks in `.pre-commit-config.yaml`: ruff's lint (with fixes) and
  formatter, pinned to ruff 0.15.12, and the whole pytest suite on every
  commit. `pre-commit` joins the dev extras; the code is formatted with ruff
  format once as the baseline (`chore/pre-commit`).
- Test coverage: `pytest --cov` measures the package with branches, configured
  in pyproject.toml, with pytest-cov in the dev extras. Coverage goes from 84% to
  99% - the CLI, which only ever ran in a subprocess coverage cannot see, the
  API's 404 and 400 answers, the store's refusals and rollback, and the payloads
  the hook declines. One unused helper it turned up is removed
  (`test/coverage`).
- The README and its translations show the board through one real Claude Code
  session: the tasks landing in QUEUE, each moving to IN PROGRESS before Claude
  starts on it, all of them in DONE - three frames of a panel that was never
  reloaded (`docs/process-screenshot`).
- The board, the table view and the task dialog name the three states the same
  way - QUEUE, IN PROGRESS, DONE - and the projects table counts all three
  instead of the queue alone. A TODO backlog column was tried and taken out
  again: every new task lands in QUEUE (`feat/todo-column`,
  `feat/remove-todo-column`).
- A project appears on the board as soon as a Claude Code session starts (or
  resumes) in it, with empty columns, instead of only once Claude has created a
  task there. The plugin's hook also runs on `SessionStart`, where it registers
  the project and prints nothing (`feat/session-start-project`).

- The README and its translations gain a fourth step, checking the plugin from
  inside Claude Code: `/mcp` shows the server connected, `/tasktracker:tasks`
  reads the queue, and a todo list Claude writes appears on the panel
  (`docs/plugin-check`).
- Docker: a `Dockerfile` and `docker-compose.yml` that run the panel, its REST
  API and the MCP server in one container on `127.0.0.1:8787`. The board's
  database is shared with the host through a bind mount, the home directory is
  mounted read-only at the same path so project roots resolve as they do for
  the hook, and the entrypoint runs the server as the owner of that home rather
  than as root (`feat/docker`).
- The MCP tools over HTTP at `/mcp`, served by the same web app as the panel.
  Stateless JSON, and FastMCP's DNS-rebinding protection: only a Host of
  `127.0.0.1` or `localhost` is accepted (`feat/docker`).
- Documentation: a compact README with badges, screenshots of the board and the
  projects table, and a language switcher; Russian and Chinese translations
  under `docs/`; four tests that resolve every relative link, check each README
  links to the other two and not to itself, and assert the three carry the same
  sections (`docs/readme-translations`).
- The Claude Code plugin: the `PostToolUse` hook on `TodoWrite` that mirrors
  Claude's own todo list onto the board, the plugin and one-plugin marketplace
  manifests, the `.mcp.json` that connects the tracker's MCP server, and the
  `/tasktracker:tasks` and `/tasktracker:tasks-panel` commands. The hook is
  standard library only and finds the package through `CLAUDE_PLUGIN_ROOT`, so
  the mirror works before anything is pip-installed (`feat/plugin`).
- The MCP server: eight stdio tools (`tasks_queued`, `tasks_all`, `task_add`,
  `task_start`, `task_done`, `task_update`, `task_delete`, `projects_list`) and
  the `tasktracker mcp` command that runs them. Its instructions tell Claude
  not to re-file the todos the hook already mirrors (`feat/mcp`).
- The web panel: a projects table, a board of three columns per project with
  drag and drop between them, the same cards as a sortable table behind a view
  toggle, and a settings screen for how long a finished task stays drawn. Vue 2
  with no build step, the palette and control metrics taken from
  `wachawo/lmgateway`, every asset served from this host and a light and dark
  half of the palette (`feat/webui`).
- The web server: a FastAPI application serving nine REST endpoints under
  `/api` and the panel's static files at `/`, plus the `tasktracker` console
  script (`serve`, `where`). Every failure leaves it in one envelope,
  `{"error": {"message": …}}`, including the static mount's 404s and the
  validation failures FastAPI would otherwise answer as a list of dictionaries
  (`feat/api`).
- `tasktracker.store`: the SQLite layer every process writes through - projects
  keyed on repository root, tasks in three columns with float positions, the
  settings row that controls how long a finished card is drawn, and the todo
  mirror that reconciles one session's cards against Claude's own todo list
  (`feat/store`).
- Repository scaffold: packaging metadata, licence, ignore rules and
  `tasktracker.config` - the one module that answers "which database file" and
  "which project is this directory" for every entry point (`chore/scaffold`).

### Changed

- A click on a task - a card on the board, a row in the table view - opens its
  dialog, where the title, the detail and the status are edited and a DELETE
  button removes it after the same confirmation as the trash icon. The table
  view shows the status as a word; it is changed in the dialog only
  (`feat/task-modal`).
- The first release: the plugin, the package and `__version__` are all 0.0.1,
  and stay there - changes go into 0.0.1 (`chore/release-0.0.1`,
  `docs/version-0.0.1`).
- The README and its translations gain an **Updating** block. With the version
  held at 0.0.1, `claude plugin update` reports "already at the latest version"
  and keeps the old files, so the block reinstalls the plugin instead, and a
  project `CLAUDE.md` records both (`chore/plugin-version`,
  `docs/version-0.0.1`).
- The README and its translations install the plugin with the `claude plugin`
  commands run from the checkout (`claude plugin marketplace add ./`) instead
  of `/plugin` with a path to fill in, and say it is installed once for every
  project. A bare `.` is rejected by Claude Code; `./` is stored as the
  absolute path (`docs/plugin-install-shell`).
- The plugin connects to the MCP server over HTTP, at the container, instead of
  starting it over stdio - so nothing has to be pip-installed on the host
  (`feat/docker`).
- Outside stdio, an MCP tool called with no `project` now answers with an error
  asking for one, instead of taking the server's working directory - which in
  the container is `/app`. The server's instructions and both plugin commands
  tell Claude to pass the path it is working in (`feat/docker`).
- The README and its translations are cut down to the three launch steps
  (`feat/docker`).

### Fixed

- The panel's API answered 500 on a share of its polls with "SQLite objects
  created in a thread can only be used in that same thread". FastAPI opens a
  request's connection on one pool thread and may run the handler on another;
  the request connection now opens with sqlite3's same-thread check off. It is
  still one connection per request, used by one thread at a time
  (`fix/sqlite-threads`).
- The board fills itself again on current Claude Code. The hook listened only
  to `TodoWrite`, which Claude Code 2.1 no longer calls - it keeps its task list
  with `TaskCreate` and `TaskUpdate` - so no card was ever mirrored. The hook now
  listens to all three: `TaskCreate` adds a queued card, `TaskUpdate` moves it
  between columns, rewrites its text, or removes it on `deleted`, one card per
  Claude task. Cards carry the Claude task number in a new `external_id`
  column; there is no migration, and a board created before this starts from a
  fresh `tasks.db` (`fix/task-tools-mirror`).
- The plugin's MCP server is declared in `.claude-plugin/plugin.json` instead of
  a `.mcp.json` at the root of the checkout. Claude Code also read that file as
  the project's own MCP config whenever it ran inside the checkout, and the
  plugin's format failed that parser: `claude mcp list` reported
  `mcpServers: Invalid input` (`fix/plugin-config`).
- `/tasktracker:tasks` pre-approves its tools as
  `mcp__plugin_tasktracker_tasktracker__…`, the names Claude Code gives a
  plugin's MCP tools. The old `mcp__tasktracker__…` names matched nothing, so
  the command asked for permission on every run (`fix/plugin-config`).
- `mcp` is bounded `>=1.29,<2`. The unbounded range installed mcp 2.x, which
  renamed FastMCP, and the server failed at import on any fresh install
  (`feat/docker`).

