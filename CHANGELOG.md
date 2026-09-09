# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- `tasktracker.store`: the SQLite layer every process writes through - projects
  keyed on repository root, tasks in three columns with float positions, the
  settings row that controls how long a finished card is drawn, and the todo
  mirror that reconciles one session's cards against Claude's own todo list
  (`feat/store`).
- Repository scaffold: packaging metadata, licence, ignore rules and
  `tasktracker.config` - the one module that answers "which database file" and
  "which project is this directory" for every entry point (`chore/scaffold`).
