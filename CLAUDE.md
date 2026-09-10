# TaskTracker: instructions for Claude Code

## Bump the version with every plugin change

Claude Code installs this plugin as a copy, and `claude plugin update` decides
whether there is anything to update by the `version` in
`.claude-plugin/plugin.json` alone. If the version did not change, it reports
"already at the latest version" and keeps the old files - whatever else changed.

So every branch that touches what the installed copy contains bumps the version
once before it lands. It is one version, kept in three places that always carry
the same number - `tests/test_docs.py` fails when they differ:

- `version` in `.claude-plugin/plugin.json`;
- `version` in `pyproject.toml`;
- `__version__` in `src/tasktracker/__init__.py`.

What counts as touching the installed copy:

- `.claude-plugin/`, `hooks/`, `commands/`;
- `src/tasktracker/` - the hook imports the package from the plugin's own copy.

The patch number for fixes and small changes (0.0.1 -> 0.0.2), the minor number
for new features, as the CHANGELOG's Semantic Versioning line says. Users then
update with the commands in the README's **Updating** block.

Established 2026-09-10, after the `fix/plugin-config` fixes shipped under an
unchanged 0.1.0 and `claude plugin update` left the installed copy on the old
files.
