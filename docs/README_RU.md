[EN](../README.md) | RU | [CN](README_CN.md)

## TaskTracker: доска, которую Claude заполняет сам 🗂️

<p class="badges">
  <img src="https://img.shields.io/badge/Claude%20Code-plugin-D97757?logo=anthropic&logoColor=white" alt="Плагин Claude Code">
  <img src="https://img.shields.io/badge/MCP-HTTP%20server-111111" alt="MCP HTTP-сервер">
  <img src="https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white" alt="Docker Compose">
  <img src="https://img.shields.io/badge/storage-SQLite-003B57?logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="Лицензия MIT">
</p>

Claude Code ведёт список задач, пока работает, — и этот список умирает вместе с сессией.<br>
TaskTracker зеркалит его на доску проекта и даёт Claude MCP-инструменты, чтобы в следующий раз прочитать очередь обратно.<br>
Доска — это веб-панель: список проектов, а внутри три колонки — **в очереди**, **в работе**, **выполнено**.

<img src="board.png" width="800" alt="Доска одного проекта: три колонки, карточки перетаскиваются между ними">

<img src="projects.png" width="800" alt="Таблица проектов: название, дата обновления, сколько задач в очереди">

## 🚀 Быстрый старт

**1. Запусти доску** — панель и MCP-сервер в одном контейнере:

```bash
cd TaskTracker
docker compose up -d
```

Панель откроется на http://127.0.0.1:8787.

**2. Установи плагин** — один раз, из той же папки; он работает во всех проектах:

```bash
claude plugin marketplace add ./
claude plugin install tasktracker@tasktracker
```

**3. Перезапусти Claude Code.** С этого момента каждая задача, которую пишет Claude, попадает на доску.

**4. Проверь, что работает** — в Claude Code:

- `/mcp` — в списке есть `plugin:tasktracker:tasktracker` со статусом «подключён».
- `/tasktracker:tasks` — Claude показывает очередь текущего проекта (на новой доске она пустая).
- Попроси Claude *«составь todo-список из трёх шагов для …»* и открой http://127.0.0.1:8787 —
  там появится проект с тремя карточками с пометкой `TODO`.

**Обновление** — после получения изменений, из папки TaskTracker:

```bash
docker compose up -d --build
claude plugin marketplace update tasktracker
claude plugin update tasktracker@tasktracker
```

Потом перезапусти Claude Code.

### Лицензия

[MIT](../LICENSE). Montserrat — под [SIL Open Font License](../src/tasktracker/www/fonts/OFL.txt).
