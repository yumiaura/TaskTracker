# TaskTracker: instructions for Claude Code

## The version is 0.0.1 - do not bump it

The plugin, the package and the web app are version 0.0.1, and they stay at
0.0.1. Do not raise it for a fix or a feature; a change goes into 0.0.1. Only
Olya changes the version.

It is one version, kept in three places that always carry the same number -
`tests/test_docs.py` fails when they differ:

- `version` in `.claude-plugin/plugin.json`;
- `version` in `pyproject.toml`;
- `__version__` in `src/tasktracker/__init__.py`.

## Getting a change into an installed plugin

Claude Code installs the plugin as a copy, and `claude plugin update` acts only
when the `version` in `.claude-plugin/plugin.json` changes. With the version
held at 0.0.1 it reports "already at the latest version" and keeps the old
files, so a change reaches an installed copy by reinstalling it - the README's
**Updating** block:

```bash
claude plugin marketplace update tasktracker
claude plugin uninstall tasktracker@tasktracker
claude plugin install tasktracker@tasktracker
```

then a restart of Claude Code. That is needed after any change to what the
installed copy contains: `.claude-plugin/`, `hooks/`, `commands/`, or
`src/tasktracker/` - the hook imports the package from the plugin's own copy.

Established 2026-09-10: Olya set the version to 0.0.1 and said to keep it there.
