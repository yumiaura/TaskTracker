[EN](../README.md) | [RU](README_RU.md) | CN

## TaskTracker：Claude Code 和 Codex 自己填写的任务看板 🗂️

<p class="badges">
  <img src="https://img.shields.io/badge/Claude%20Code-plugin-D97757?logo=anthropic&logoColor=white" alt="Claude Code 插件">
  <img src="https://img.shields.io/badge/MCP-HTTP%20server-111111" alt="MCP HTTP 服务器">
  <img src="https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white" alt="Docker Compose">
  <img src="https://img.shields.io/badge/storage-SQLite-003B57?logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT 许可证">
</p>

Claude Code 工作时会维护一份任务清单 —— 而这份清单会随会话一起消失。<br>
TaskTracker 把它按项目镜像到看板上，并为 Claude 提供 MCP 工具，下次可以把队列读回来。<br>
看板是一个网页面板：先是项目列表，再是三列 —— **QUEUE**、**IN PROGRESS**、**DONE**。<br>
在某个项目里启动 Claude 的那一刻，这个项目就会出现；面板会自动刷新。

**也支持 Codex：**通过生命周期钩子镜像其原生计划，并通过同一个 MCP 服务器读取队列。
参见 [Codex 配置](#-codex)。

<img src="board.png" width="800" alt="单个项目的看板：三列，卡片可在列之间拖动">

<img src="projects.png" width="800" alt="项目表：每个项目的 QUEUE、IN PROGRESS 和 DONE 计数">

实际效果 —— 一次真实的 Claude Code 会话，面板从未刷新页面：Claude 规划工作，任务进入
**QUEUE**（1）；每个任务在 Claude 开始处理之前移到 **IN PROGRESS**（2），完成后移到 **DONE**（3）。

<img src="process.png" width="800" alt="同一会话的三个时刻：三个任务在 QUEUE，第一个在 IN PROGRESS，三个都在 DONE">

点击一个任务 —— 看板上的卡片或表格中的一行 —— 即可打开它：修改标题和详情、更改状态，
或删除它。卡片也可以在列之间拖动。

<img src="dialog.png" width="560" alt="任务对话框：标题、详情、状态，以及 DELETE、CANCEL 和 SAVE">

## 🚀 快速开始

**1. 启动看板** —— 面板和 MCP 服务器在同一个容器里：

```bash
cd TaskTracker
docker compose up -d
```

面板地址是 http://127.0.0.1:8787。卡片的来源在 `.env` 中设置 —— 见[下文](#-卡片从哪里来)。

**2. 安装 Claude Code 插件** —— 在同一目录下执行一次即可，所有项目都会生效。
Codex 用户请使用[单独的配置步骤](#-codex)：

```bash
claude plugin marketplace add ./
claude plugin install tasktracker@tasktracker
```

**3. 重启 Claude Code。** 从此你在其中打开 Claude 的每个项目都会出现在看板上，
它的卡片随 Claude 的工作而变化。

**4. 检查是否正常工作** —— 在 Claude Code 里：

- `/mcp` —— 列表中有 `plugin:tasktracker:tasktracker`，状态为已连接。
- `/tasktracker:tasks` —— Claude 会报告当前项目的队列（新看板上为空）。
- 让 Claude *「为 … 列一个三步的待办清单」*，然后打开 http://127.0.0.1:8787 ——
  会出现这个项目，以及三张标着 `TODO` 的卡片。

**更新** —— 拉取新版本后，在 TaskTracker 目录下执行：

```bash
docker compose up -d --build
claude plugin marketplace update tasktracker
claude plugin uninstall tasktracker@tasktracker
claude plugin install tasktracker@tasktracker
```

然后重启 Claude Code。

## 🤖 Codex

启动看板后，在项目目录运行以下命令（主机需要 Python 3.11+；
支持 Linux、macOS 和 WSL）：

```bash
codex mcp add tasktracker --url http://127.0.0.1:8787/mcp
python3 hooks/install-codex.py
```

重启 Codex，打开 `/hooks`，检查并信任 TaskTracker 的钩子；Codex 要求先完成此检查，
才会运行它们。在 `/mcp` 中确认连接。安装程序保留其他钩子，并备份修改前的 `hooks.json`。

`TASKTRACKER_CARDS=claude` 保留原有默认值，供两个客户端共同使用：Codex 的
`update_plan` 步骤显示为 `CODEX` 卡片，状态随计划更新。设置为 `prompts` 时，
请求在 Codex 回答期间处于 IN PROGRESS，回答停止后进入 DONE。
Claude 和 Codex 共用看板，但各自的会话不会修改对方的卡片。

更新后，重新构建容器、运行钩子安装程序并重启 Codex。
[完整配置、验证和限制](CODEX.md)。

## 🃏 卡片从哪里来

只有一个设置：`docker-compose.yml` 旁边 `.env` 中的 `TASKTRACKER_CARDS`
（复制 [`.env.example`](../.env.example)）。修改后重新构建并重启 Claude Code。

```bash
TASKTRACKER_CARDS=claude    # 默认
TASKTRACKER_CARDS=prompts
```

- **`claude`** —— 卡片就是 Claude 自己的任务。插件会在每次会话开始时、并在每条请求中
  再次告诉 Claude：凡是不止一步的工作都拆成任务并及时更新状态；每个任务是一张标着 `TODO`
  的卡片，随 Claude 的工作移动。如果 Claude 仍然做了工作（Bash、Edit、Write）却没有建任何
  任务，这条请求本身会以 `PROMPT` 标记进入 **DONE**。只靠阅读回答的问题不会生成卡片。
- **`prompts`** —— 你发出的每一条请求都是一张标着 `PROMPT` 的卡片：第一行是标题，
  完整内容是详情。Claude 回答期间它在 **IN PROGRESS**，回答结束后移到 **DONE**。
  斜杠命令不会生成卡片，Claude 自己的任务也不会显示。

<img src="prompts.png" width="800" alt="prompts 模式：三条请求作为卡片，一张在 IN PROGRESS，两张在 DONE">

## 🔗 合并重复卡片

Claude/Codex 通过 `tasks_review` 按语义比较卡片，再用 `tasks_reconcile` 应用决定。
例如，要求发布 0.0.2 的提示和记录该版本发布的 MCP 任务可以合成一张卡片。
不同的子任务、版本和不确定的匹配保持独立。

工作结束后，如果不同来源的卡片发生变化，Stop 钩子会请求一次检查，包括 DONE 卡片。
合并后的卡片显示所有来源标签；在对话框的 **MERGED CARDS** 中可查看原始内容和合并原因。
重复钩子仍然指向同一张卡片。提示的回答结束，不代表对应的任务已经完成。

处理已有重复卡片时，在 Claude Code 中运行 `/tasktracker:reconcile`，或让 Codex
检查并合并当前项目的 TaskTracker 重复卡片。请先更新容器和已安装的钩子。
[LLM 检查机制](RECONCILIATION.md)。

## 🧪 开发

```bash
pip install -e '.[dev]'
pre-commit install              # 每次提交前运行 ruff 和测试
pytest --cov                    # 运行测试，附带覆盖率和未覆盖的行
```

`ruff check` 和 `ruff format` 负责代码风格；配置在 `pyproject.toml` 中。
GitHub Actions（`.github/workflows/ci.yml`）会在每个 pull request 和每次推送到 `main` 时，
在 Python 3.11 和 3.12 上运行 ruff 和 `pytest --cov`。

面板没有构建步骤：`src/tasktracker/www` 原样提供，所有第三方库都放在其中。
在下次发布之前版本保持为 **0.0.3** —— 原因以及改动如何进入已安装的插件，见 [`CLAUDE.md`](../CLAUDE.md)。

### 许可证

[MIT](../LICENSE)。Montserrat 采用 [SIL Open Font License](../src/tasktracker/www/fonts/OFL.txt)。
