# TaskTracker: instructions for Codex

Read `CLAUDE.md` for the shared release policy. Keep the version at **0.0.4**
unless Olya explicitly requests a release; record changes under Unreleased in
`CHANGELOG.md`.

- The Python package is in `src/tasktracker`; tests are in `tests`.
- Keep lifecycle hooks standard-library-only so they work from a checkout
  without pip. Claude uses `hooks/todo-mirror.py`; Codex uses
  `hooks/codex-mirror.py`. Their payload adapters are separate.
- Keep the English, Russian and Chinese READMEs aligned when setup changes.
- Install development dependencies with `pip install -e '.[dev]'`.
- Before finishing a change, run the CI checks: `ruff check src tests hooks`,
  `ruff format --check src tests hooks`, and `pytest --cov`.

Codex integration setup and its supported events are documented in
`docs/CODEX.md`.
