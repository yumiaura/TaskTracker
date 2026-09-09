# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

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
