[EN](../README.md) | [RU](README_RU.md) | CN

## TaskTracker：Claude 自己填写的任务看板 🗂️

<p class="badges">
  <img src="https://img.shields.io/badge/Claude%20Code-plugin-D97757?logo=anthropic&logoColor=white" alt="Claude Code 插件">
  <img src="https://img.shields.io/badge/MCP-stdio%20server-111111" alt="MCP stdio 服务器">
  <img src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/storage-SQLite-003B57?logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT 许可证">
</p>

Claude Code 工作时本来就会维护一份待办清单 —— 而这份清单会随会话一起消失。<br>
TaskTracker 把它留下来：Claude 写下的每一条待办，都会按项目镜像到看板上。<br>
下次会话它可以把队列读回来，也可以通过自己的 MCP 工具把新任务放上看板。<br>
你在本地网页面板里看着这一切：先是项目列表，再是三列 —— **排队中**、**进行中**、**已完成**。

<img src="board.png" width="800" alt="单个项目的看板：三列，卡片可在列之间拖动">

<img src="projects.png" width="800" alt="项目表：名称、最后更新时间、排队中的任务数">

## 🚀 快速开始

```bash
pip install -e .
```

然后在 Claude Code 里：

```
/plugin marketplace add /TaskTracker/所在路径
/plugin install tasktracker@tasktracker
```

重启之后，每一次 `TodoWrite` 都会落到看板上，`tasktracker` MCP 服务器已连接，
`/tasktracker:tasks` 会报告当前项目的队列，`/tasktracker:tasks-panel` 会打开面板。

手动运行：

```bash
tasktracker serve --open      # http://127.0.0.1:8787/
tasktracker where             # 数据库在哪里
```

面板只监听 `127.0.0.1` 且没有任何鉴权 —— 正因为没有鉴权，它才只监听在那里。
`TASKTRACKER_HOST` 和 `TASKTRACKER_PORT` 可以覆盖默认值。

## 🧩 看板如何自己填满

1. **钩子。** 一个作用于 `TodoWrite` 的 `PostToolUse` 钩子，会把 Claude 自己的待办清单
   镜像到它当前所在项目的看板上。无需调用，无需记住。只依赖标准库，所以在安装任何依赖
   之前就能工作。
2. **MCP 工具。** 用于**不属于**当前计划的工作 —— 后续事项、顺手发现的问题、留到下次
   再做的事 —— 以及在会话开始时把队列读回来。
3. **面板。** 手动新建卡片、在列之间拖动、编辑或删除。

## 🛠 MCP 工具

| 工具 | 作用 |
| --- | --- |
| `tasks_queued` | 有什么在等、有什么在做。开始做一个项目时调用它。 |
| `tasks_all` | 所有卡片，包括已完成的。 |
| `task_add` | 把一个任务放上看板。 |
| `task_start` / `task_done` | 移入进行中 / 标记为已完成。 |
| `task_update` / `task_delete` | 修改标题、详情或所在列 / 删除一张卡片。 |
| `projects_list` | 看板已知的全部项目及其计数。 |

每个工具都会从会话所在目录出发、向上找到仓库根目录来确定项目 —— 所以在
`~/src/app/web` 里的会话会记到 `app` 名下。每个工具也都接受显式的 `project`：
名称、路径或 id。

## ⚙️ 设置

设置页上只有一项：**已完成的任务在看板上保留多少天**。它是对 API 返回内容的过滤，
而不是删除 —— 把数字调大，卡片就回来了。`0` 表示已完成的任务永远保留在看板上。

主题和「看板 / 表格」的选择则保存在浏览器里，因为它们关乎你正坐在哪块屏幕前。

## 💾 数据在哪里

一个 SQLite 文件 `~/.claude/tasktracker/tasks.db`，所有项目共用；`TASKTRACKER_HOME`
可以把它挪走。有三个进程会写它 —— 面板、MCP 服务器和钩子 —— 因此它以 WAL 模式运行、
带 busy timeout，并且一开始就取得写锁。

<details>
<summary><b>HTTP API</b> —— 面板所做的一切都经由它</summary>

任何失败都以 `{"error": {"message": "…"}}` 的形式返回。

| 方法 | 路径 | |
| --- | --- | --- |
| `GET` | `/api/health` | 是否在运行，打开的是哪个文件 |
| `GET` | `/api/projects` | 全部项目及其计数 |
| `GET` | `/api/projects/{id}` | 一个项目、它的卡片和设置 |
| `DELETE` | `/api/projects/{id}` | 移除一个项目及其卡片 |
| `POST` | `/api/projects/{id}/tasks` | 新增一张卡片 |
| `PATCH` | `/api/tasks/{id}` | 编辑；未传的字段保持不变 |
| `POST` | `/api/tasks/{id}/move` | `{status, index}` —— 放进某一列 |
| `DELETE` | `/api/tasks/{id}` | 删除一张卡片 |
| `GET` `PUT` | `/api/settings` | 「N 天后隐藏」这一设置 |

</details>

## 🧪 开发

```bash
pip install -e '.[dev]'
python3 -m pytest tests -q
python3 -m ruff check src tests
```

面板没有构建步骤：`www/` 原样提供，`.vue` 文件由 `httpVueLoader` 在浏览器中加载，
所有第三方库都放在 `www/vendor` 下。有四个测试会遍历 `index.html`、`main.css` 和
`app.js` 中出现的每一个路径，断言对应文件确实随包发布 —— 否则一个丢失的第三方库，
要等到浏览器去请求它时才会有人发现。

调色板、控件尺寸和顶栏取自
[`wachawo/lmgateway`](https://github.com/wachawo/lmgateway)，让两个工具看起来像一家人。

### 许可证

[MIT](../LICENSE)。Montserrat 采用 SIL Open Font License，见
[`OFL.txt`](../src/tasktracker/www/fonts/OFL.txt)。
