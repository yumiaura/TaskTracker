# Codex integration

TaskTracker connects to local Codex through HTTP MCP and lifecycle hooks.
Claude Code and Codex can use the same board at the same time. The existing
database stays at `~/.claude/tasktracker/tasks.db`, including on machines that
only use Codex; Claude itself does not need to be installed.

## Install

Use a Codex CLI version that provides `/hooks` and `PostToolUse` for
`update_plan`, plus Python 3.11 or newer on the host. The hook installer below
targets Linux, macOS and WSL. Run from the TaskTracker checkout:

```bash
docker compose up -d --build
codex mcp add tasktracker --url http://127.0.0.1:8787/mcp
python3 hooks/install-codex.py
```

Restart Codex. Open `/hooks`, review the four TaskTracker handlers and trust
them. Codex requires this review before running newly installed or changed
hooks. Open `/mcp` to check that `tasktracker` is connected.

The installer merges its handlers into `~/.codex/hooks.json` (or into the
directory specified by `CODEX_HOME`). Existing hooks are retained; a changed
file is backed up beside it as `hooks.json.<unique suffix>.bak`. Running the
installer again updates TaskTracker's handlers without adding copies. It
leaves `config.toml`, agent instructions and hook trust decisions alone.

For a different profile or project-local configuration, use
`python3 hooks/install-codex.py --hooks-file /absolute/path/to/hooks.json`.
Configure the MCP server in that same Codex profile. Install at one scope,
because Codex runs matching hooks from every active scope.

The hook runs from the checkout using the Python interpreter that ran the
installer. Keep both paths available; rerun the installer after moving the
checkout or changing that interpreter. The hook needs no pip installation.
If you override `TASKTRACKER_HOME`, the server and host hook must use the same
directory. A remote Codex environment must have its own reachable board and
shared database; its `127.0.0.1` is not your laptop.

## Card modes

Set `TASKTRACKER_CARDS` in the `.env` beside `docker-compose.yml`, then run
`docker compose up -d --build` and restart Codex.

| Mode | Codex behavior |
| --- | --- |
| `claude` (default, retained for compatibility) | Every native `update_plan` step becomes a `CODEX` card. `pending` → QUEUE, `in_progress` → IN PROGRESS, `completed` → DONE. |
| `prompts` | A submitted prompt becomes a `PROMPT` card in IN PROGRESS; `Stop` moves it to DONE. Native plan steps are not mirrored. |

Session start registers the project, including when resuming or compacting a
session. In task mode, the session and prompt hooks remind Codex to maintain
its native plan. MCP tools read earlier tasks and save follow-ups; they should
not duplicate steps already mirrored by the hook. `tasks_queued` also returns
the active `cards_mode`.

Plan steps have no external task id, so their text identifies them within a
session and project. Keep that text stable when changing status. Removing a
queued step removes its card; started and completed work stays on the board.
Routine plan mirroring only updates cards from its own session and project.

The LLM can explicitly combine duplicate events across those sources through
[semantic reconciliation](RECONCILIATION.md). A merged card retains the original
hook identities, and its dialog shows the source texts and merge reason.

In prompts mode, slash commands and empty prompts make no card. If an answer
is interrupted, its card stays in progress until the next prompt closes it,
as in the Claude integration. A late Stop for an older turn cannot finish the
new turn's card. Repeated events for one turn reuse the same card.

Task mode records the plan Codex actually creates. A request that never calls
`update_plan` makes no automatic card; the Claude-specific transcript fallback
is not applied to Codex. Use prompts mode to record every request. The adapter
does not parse Codex transcripts or infer completed work from an answer ending.

## Check and update

Ask Codex to create a three-step plan with `update_plan`, move the first step
to `in_progress`, and pause. At <http://127.0.0.1:8787>, check that the project
has three `CODEX` cards and that the first is in IN PROGRESS. After the step is
completed, the same card should move to DONE.

After pulling changes:

```bash
docker compose up -d --build
python3 hooks/install-codex.py
```

Restart Codex and review any changed hooks in `/hooks`. No Claude plugin
installation is needed for Codex. To stop mirroring, disable the TaskTracker
handlers in `/hooks`; `codex mcp remove tasktracker` disconnects the MCP tools.

If your Codex version lacks these lifecycle hooks, the MCP connection still
works: ask Codex to use `tasks_queued`, `task_add`, `task_start` and `task_done`
directly. That mode depends on explicit MCP calls and does not automatically
mirror the native plan.

The integration follows the official documentation for
[Codex hooks](https://learn.chatgpt.com/docs/hooks) and
[MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
