# TaskTracker: instructions for Claude Code

## The version is 0.0.2 - only Olya changes it

The plugin, the package and the web app are version 0.0.2, and they stay at
0.0.2 until Olya says otherwise. Do not raise it for a fix or a feature; a
change goes into the current version, under Unreleased in the CHANGELOG. When
Olya names a new version, it is set in all three places below, Unreleased
becomes that version's section, and it gets a `v<version>` tag.

It is one version, kept in three places that always carry the same number -
`tests/test_docs.py` fails when they differ:

- `version` in `.claude-plugin/plugin.json`;
- `version` in `pyproject.toml`;
- `__version__` in `src/tasktracker/__init__.py`.

## Getting a change into an installed plugin

Claude Code installs the plugin as a copy, and `claude plugin update` acts only
when the `version` in `.claude-plugin/plugin.json` changes. With the version
held where it is it reports "already at the latest version" and keeps the old
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

Established 2026-09-10: Olya set the version to 0.0.1 and said to keep it there,
and raised it to 0.0.2 the same day rather than move the published v0.0.1 tag.
