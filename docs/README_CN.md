[EN](../README.md) | [RU](README_RU.md) | CN

## TaskTracker：Claude 自己填写的任务看板 🗂️

<p class="badges">
  <img src="https://img.shields.io/badge/Claude%20Code-plugin-D97757?logo=anthropic&logoColor=white" alt="Claude Code 插件">
  <img src="https://img.shields.io/badge/MCP-HTTP%20server-111111" alt="MCP HTTP 服务器">
  <img src="https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white" alt="Docker Compose">
  <img src="https://img.shields.io/badge/storage-SQLite-003B57?logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT 许可证">
</p>

Claude Code 工作时会维护一份待办清单 —— 而这份清单会随会话一起消失。<br>
TaskTracker 把它按项目镜像到看板上，并为 Claude 提供 MCP 工具，下次可以把队列读回来。<br>
看板是一个网页面板：先是项目列表，再是三列 —— **排队中**、**进行中**、**已完成**。

<img src="board.png" width="800" alt="单个项目的看板：三列，卡片可在列之间拖动">

<img src="projects.png" width="800" alt="项目表：名称、最后更新时间、排队中的任务数">

## 🚀 快速开始

**1. 启动看板** —— 面板和 MCP 服务器在同一个容器里：

```bash
cd TaskTracker
docker compose up -d
```

面板地址是 http://127.0.0.1:8787。

**2. 安装插件** —— 在同一目录下执行一次即可，所有项目都会生效：

```bash
claude plugin marketplace add ./
claude plugin install tasktracker@tasktracker
```

**3. 重启 Claude Code。** 从此 Claude 写下的每一条待办都会出现在看板上。

### 许可证

[MIT](../LICENSE)。Montserrat 采用 [SIL Open Font License](../src/tasktracker/www/fonts/OFL.txt)。
