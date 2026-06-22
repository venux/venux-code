# 更新日志

> Venux Code 的所有重要变更记录

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范。

---

## [0.1.0] - 2026-06-23

### 🎉 首次发布

Venux Code 的首个正式版本！一个基于 LangGraph 的下一代终端 AI 编程助手。

### ✨ 新功能

#### 智能体核心
- 基于 LangGraph `StateGraph` 的有状态智能体循环
- 自动多步工具调用（最多 50 轮迭代）
- 上下文裁剪策略（120K 字符预算，约 30K token）
- 流式事件输出（`AgentEvent` 异步迭代器）

#### LLM 提供商
- **OpenAI** — 支持 GPT-4o、GPT-4o-mini、o1 系列
- **Anthropic** — 支持 Claude Sonnet 4、Claude 3.5 Haiku
- **Google Gemini** — 支持 Gemini 2.0 Flash、Gemini 1.5 Pro
- **DeepSeek** — 支持 DeepSeek Chat、DeepSeek Coder
- **MiMo** — 支持 MiMo-7B
- **Kimi / Moonshot** — 支持 Moonshot v1 系列
- **OpenRouter** — 支持通过 OpenRouter 访问各类开源模型

#### 内置工具
- `bash` — Shell 命令执行（需要权限）
- `edit` — 文件编辑（查找替换，需要权限）
- `view` — 文件查看（支持行号和分页）
- `write` — 文件写入（需要权限）
- `grep` — 正则搜索（ripgrep 后端）
- `glob` — 文件名模式匹配
- `ls` — 目录列表

#### 终端界面 (TUI)
- 基于 Textual 的全屏终端界面
- 聊天显示组件（支持 Markdown 渲染）
- 多行输入框（支持 Shift+Enter 换行）
- 会话侧边栏
- 状态栏（模型、会话、token 计数）
- 快捷键支持（Ctrl+C/L/N/O/B）

#### CLI 命令
- `venux-code` — 启动 TUI
- `venux-code chat -q "..."` — 单次查询
- `venux-code config` — 查看配置
- `venux-code sessions list` — 列出会话
- `venux-code doctor` — 健康检查

#### 数据层
- SQLAlchemy 异步引擎（支持 SQLite/PostgreSQL）
- Alembic 数据库迁移
- 会话和消息持久化

#### 权限系统
- 四元组权限模型 `(session_id, tool, action, path)`
- 全局自动批准模式
- 按工具名自动批准/拒绝
- 手动审批流程

#### 事件系统
- 异步 PubSub 事件总线（`AsyncBroker`）
- 支持 `LLM_TOKEN`、`TOOL_CALL_START`、`TOOL_CALL_RESULT`、`AGENT_DONE`、`ERROR` 事件

#### 配置系统
- 分层配置（环境变量 > 项目配置 > 用户配置 > 默认值）
- Pydantic 类型安全验证
- `.venux-code.json` 项目级配置
- `~/.venux-code/config.yaml` 用户级配置
- `VENUX_` 前缀环境变量

### 📦 依赖

- Python >= 3.11
- LangChain >= 0.3.0
- LangGraph >= 0.2.0
- Textual >= 0.80.0
- Rich >= 13.0.0
- Typer >= 0.12.0
- Pydantic >= 2.0.0
- SQLAlchemy >= 2.0.0
- httpx >= 0.27.0

#### 记忆系统
- 内置记忆提供者（SQLite + 内存缓存）
- Holographic 记忆提供者（FTS5 全文搜索 + 实体消重 + 信任评分）
- 用户画像持久化
- 自动记忆提取（从对话中提取偏好/项目/工具信息）
- 记忆 Nudge 机制（定期提醒 Agent 保存记忆）

#### 技能系统
- SKILL.md 格式技能定义（YAML frontmatter + Markdown 内容）
- 用户技能 + 项目技能 + Hub 远程技能
- 技能自动创建（从复杂任务中提取可复用流程）
- 技能加载器（自动扫描目录和远程 URL）

#### 定时任务
- 基于 APScheduler 的异步调度器
- Cron / Interval / Date 三种触发模式
- Agent 模式（LLM 执行）+ 脚本模式（Shell 执行）
- 任务持久化（JSON 文件）

#### Deep Agent 模式
- 三阶段执行：规划 → 执行 → 审查
- LangGraph 子图编排
- 文件系统中间件（保存中间结果）
- 自动重试机制

#### LSP 集成
- 异步 LSP 客户端（stdin/stdout JSON-RPC）
- 自动语言服务器检测
- 代码诊断工具

#### MCP 集成
- MCP 适配器（stdio / SSE / Streamable HTTP 三种传输）
- MCP 连接管理器（多服务器支持）
- MCP 工具自动转换为 LangChain StructuredTool

#### 更多工具
- `fetch` — HTTP 请求（httpx）
- `web_search` — 网页搜索（DuckDuckGo / SearXNG）
- `patch` — 统一补丁应用
- `delegate` — 子 Agent 委派
- `diagnostics` — LSP 代码诊断

#### 系统提示词
- 模板引擎（string.Template + Jinja2）
- Coder / Task / Summarizer / Title 四种提示词
- 上下文文件自动加载（CLAUDE.md / .cursorrules 等）
- 记忆和技能注入

### 🧪 测试

- 223 个测试全部通过
- 覆盖：配置、数据库、Session、Message、工具、记忆、权限、PubSub
- pytest + pytest-asyncio

### 📚 文档

- README.md — 项目总览（12KB）
- docs/ARCHITECTURE.md — 架构深度解析（16KB）
- docs/CONFIGURATION.md — 配置参考（9KB）
- docs/TOOLS.md — 工具开发指南（10KB）
- docs/PROVIDERS.md — Provider 配置指南（9KB）
- docs/MEMORY.md — 记忆系统文档
- docs/SKILLS.md — 技能系统文档
- docs/CRON.md — 定时任务文档
- docs/DEEP-AGENT.md — Deep Agent 模式文档
- CONTRIBUTING.md — 贡献指南（8KB）

### 🏗️ 项目结构

```
src/venux_code/
├── app.py             # 中央应用类（VenuxApp）
├── config/            # 配置管理（Pydantic Settings）
├── cli/               # CLI 和 TUI 引导（Typer）
├── tui/               # Textual TUI 组件
│   └── widgets/       # 聊天/输入/状态栏/侧栏
├── llm/
│   ├── agent/         # LangGraph Agent + Deep Agent
│   ├── providers/     # 9 种 LLM Provider
│   ├── tools/         # 11 个内置工具 + MCP 适配器
│   └── prompts/       # 系统提示词模板
├── lsp/               # LSP 客户端集成
├── memory/            # 记忆系统（内置 + Holographic）
├── skills/            # 技能系统
├── cron/              # 定时任务调度
├── db/                # 数据库引擎和模型（SQLAlchemy）
├── session/           # 会话管理
├── message/           # 消息模型
├── permission/        # 权限服务
└── pubsub/            # 异步事件总线
```
