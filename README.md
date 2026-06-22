```
 ██╗   ██╗███████╗███╗   ██╗██╗   ██╗██╗  ██╗
 ██║   ██║██╔════╝████╗  ██║██║   ██║╚██╗██╔╝
 ██║   ██║█████╗  ██╔██╗ ██║██║   ██║ ╚███╔╝
 ╚██╗ ██╔╝██╔══╝  ██║╚██╗██║██║   ██║ ██╔██╗
  ╚████╔╝ ███████╗██║ ╚████║╚██████╔╝██╔╝ ██╗
   ╚═══╝  ╚══════╝╚═╝  ╚═══╝ ╚═════╝╚═╝  ╚═╝
                    C O D E
```

# Venux Code

> 🤖 下一代终端 AI 编程助手，支持记忆、技能和多平台 LLM 提供商

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## ✨ 功能特性

- 🧠 **LangGraph 智能体循环** — 基于有状态图的对话流，自动执行多步工具调用
- 🔧 **7 个内置工具** — Bash、文件编辑、搜索、查看、写入、Grep、Glob
- 🌐 **多提供商支持** — OpenAI、Anthropic、Google Gemini、DeepSeek、MiMo、Kimi、OpenRouter
- 🖥️ **精美 TUI** — 基于 Textual 的全屏终端界面，支持侧边栏和状态栏
- 💾 **会话持久化** — SQLAlchemy + Alembic 管理的会话历史
- 🔒 **权限系统** — 细粒度工具权限控制（自动批准 / 手动审批 / 拒绝）
- ⚙️ **分层配置** — 环境变量 > 项目配置 > 用户配置 > 默认值
- 📡 **事件流** — 异步 PubSub 事件总线，支持流式输出
- 🔌 **可扩展** — 简单的 BaseTool / BaseLLMProvider 接口，轻松添加自定义工具和提供商
- 🩺 **健康检查** — `venux-code doctor` 一键诊断配置、数据库和 LLM 连接

---

## 📦 快速安装

```bash
# 使用 pip 安装
pip install venux-code

# 或使用 uv（推荐，速度更快）
uv pip install venux-code
```

### 从源码安装

```bash
git clone https://github.com/venux/venux-code.git
cd venux-code
pip install -e .
```

### 系统要求

- Python >= 3.11
- 至少一个 LLM 提供商的 API Key

---

## 🚀 快速开始

### 1. 启动 TUI（推荐）

```bash
# 直接运行，默认启动全屏终端界面
venux-code

# 或使用简短别名
vc
```

### 2. 单次查询模式

```bash
# 快速提问
venux-code chat -q "用 Python 实现快速排序"

# 指定模型
venux-code chat -q "解释这段代码" -m gpt-4o

# 继续之前的会话
venux-code chat -q "继续优化" -s session_abc123

# 禁用流式输出
venux-code chat -q "总结项目" --no-stream
```

### 3. 配置 API Key

```bash
# 方式一：环境变量
export VENUX_LLM__API_KEY="sk-your-api-key"
export VENUX_LLM__PROVIDER="openai"
export VENUX_LLM__MODEL="gpt-4o"

# 方式二：用户配置文件 ~/.venux-code/config.yaml
mkdir -p ~/.venux-code
cat > ~/.venux-code/config.yaml << 'EOF'
llm:
  provider: openai
  model: gpt-4o
  api_key: sk-your-api-key
EOF
```

### 4. 运行健康检查

```bash
venux-code doctor
```

输出示例：
```
  ✓ Configuration: Loaded successfully
  ✓ Database: Connected
  ✓ LLM connectivity: Reachable
  ✓ Dependencies: textual & rich installed

All checks passed.
```

### 5. 查看配置

```bash
venux-code config
```

### 6. 管理会话

```bash
# 列出所有会话
venux-code sessions list

# 限制显示数量
venux-code sessions list -n 50
```

---

## 🏗️ 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                    CLI / TUI Layer                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Typer CLI   │  │  Textual TUI │  │   Rich 输出   │  │
│  │  (main.py)   │  │  (app.py)    │  │              │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘  │
│         │                  │                             │
├─────────┼──────────────────┼─────────────────────────────┤
│         ▼                  ▼                             │
│  ┌──────────────────────────────────────────────────┐   │
│  │              VenuxAgent (LangGraph)               │   │
│  │  ┌──────────┐    ┌──────────────┐    ┌────────┐  │   │
│  │  │ call_llm │───▶│should_continue│───▶│  END   │  │   │
│  │  └────┬─────┘    └──────────────┘    └────────┘  │   │
│  │       │                │                          │   │
│  │       │         ┌──────▼──────┐                   │   │
│  │       │         │execute_tools│                   │   │
│  │       │         └─────────────┘                   │   │
│  │       └───────────────────────────────────────────│   │
│  └──────────────────────────────────────────────────┘   │
│                          │                               │
├──────────────────────────┼───────────────────────────────┤
│         ┌────────────────┼────────────────┐              │
│         ▼                ▼                ▼              │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐      │
│  │ Provider │    │  Tools   │    │   PubSub     │      │
│  │ Registry │    │ Registry │    │   Broker     │      │
│  └────┬─────┘    └────┬─────┘    └──────────────┘      │
│       │               │                                  │
│  ┌────▼─────┐    ┌────▼─────┐    ┌──────────────┐      │
│  │ OpenAI   │    │  Bash    │    │  Permission  │      │
│  │ Anthropic│    │  Edit    │    │   Service    │      │
│  │ Gemini   │    │  View    │    │              │      │
│  │ DeepSeek │    │  Write   │    │              │      │
│  │ MiMo     │    │  Grep    │    │              │      │
│  │ Kimi     │    │  Glob    │    │              │      │
│  │ OpenRouter│   │  Ls      │    │              │      │
│  └──────────┘    └──────────┘    └──────────────┘      │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                    Data Layer                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  SQLAlchemy   │  │   Alembic    │  │   Sessions   │  │
│  │  (异步引擎)   │  │  (迁移管理)   │  │   (持久化)   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 🌐 支持的 LLM 提供商

| 提供商 | 模型示例 | 环境变量 | 备注 |
|--------|----------|----------|------|
| **OpenAI** | `gpt-4o`, `gpt-4o-mini`, `o1` | `OPENAI_API_KEY` | 默认提供商 |
| **Anthropic** | `claude-sonnet-4-20250514`, `claude-3.5-haiku` | `ANTHROPIC_API_KEY` | Claude 系列 |
| **Google Gemini** | `gemini-2.0-flash`, `gemini-1.5-pro` | `GOOGLE_API_KEY` | Gemini 系列 |
| **DeepSeek** | `deepseek-chat`, `deepseek-coder` | `DEEPSEEK_API_KEY` | 代码专用 |
| **MiMo** | `MiMo-7B` | `MIMO_API_KEY` | 轻量级模型 |
| **Kimi / Moonshot** | `moonshot-v1-8k`, `moonshot-v1-128k` | `KIMI_API_KEY` | 长上下文 |
| **OpenRouter** | 各类开源模型 | `OPENROUTER_API_KEY` | 多模型聚合 |

---

## 🔧 内置工具

| 工具名 | 功能描述 | 需要权限 |
|--------|----------|----------|
| `bash` | 执行 Shell 命令（构建、测试、Git 等） | ✅ |
| `edit` | 编辑文件（查找替换、行级修改） | ✅ |
| `view` | 查看文件内容（支持行号、分页） | ❌ |
| `write` | 写入新文件或覆盖现有文件 | ✅ |
| `grep` | 在文件中搜索正则表达式 | ❌ |
| `glob` | 按文件名模式搜索文件 | ❌ |
| `ls` | 列出目录内容 | ❌ |

---

## ⌨️ 键盘快捷键

| 快捷键 | 功能 | 说明 |
|--------|------|------|
| `Ctrl+C` | 退出 | 关闭应用 |
| `Ctrl+L` | 清屏 | 清空当前聊天显示 |
| `Ctrl+N` | 新建会话 | 开始一个新的对话 |
| `Ctrl+O` | 模型选择 | 打开模型选择器 |
| `Ctrl+B` | 切换侧边栏 | 显示/隐藏会话列表 |
| `Ctrl+/` | 聚焦输入 | 将焦点移到输入框 |
| `Enter` | 发送消息 | 提交当前输入 |
| `Shift+Enter` | 换行 | 在输入框中换行 |

---

## ⚙️ 配置指南

Venux Code 采用分层配置系统，优先级从高到低：

1. **环境变量**（`VENUX_` 前缀）
2. **项目配置**（`.venux-code.json`，自动向上查找）
3. **用户配置**（`~/.venux-code/config.yaml`）
4. **代码默认值**

### 用户配置文件 `~/.venux-code/config.yaml`

```yaml
llm:
  provider: openai          # 提供商名称
  model: gpt-4o             # 模型名称
  api_key: sk-xxx           # API Key
  base_url: null            # 自定义 API 地址（可选）
  max_tokens: 4096          # 最大输出 token 数
  temperature: 0.7          # 温度参数

permission:
  auto_approve: false       # 全局自动批准
  auto_approve_tools:       # 自动批准的工具列表
    - view
    - grep
    - glob
    - ls
  denied_tools:             # 禁止使用的工具列表
    - bash

database:
  url: sqlite+aiosqlite:///./venux-code.db  # 数据库 URL
  echo: false               # SQL 日志

debug: false
log_level: INFO
```

### 项目配置文件 `.venux-code.json`

在项目根目录创建此文件，会覆盖用户配置：

```json
{
  "llm": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514"
  },
  "permission": {
    "auto_approve": true,
    "denied_tools": []
  }
}
```

### 环境变量

所有配置都可以通过环境变量覆盖，使用 `VENUX_` 前缀和 `__` 分隔嵌套：

```bash
export VENUX_LLM__PROVIDER=openai
export VENUX_LLM__MODEL=gpt-4o
export VENUX_LLM__API_KEY=sk-xxx
export VENUX_LLM__TEMPERATURE=0.5
export VENUX_DEBUG=true
export VENUX_LOG_LEVEL=DEBUG
```

---

## 🤝 参与贡献

我们欢迎所有形式的贡献！请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解：

- 如何提交 Issue 和 Pull Request
- 代码规范和提交信息格式
- 如何添加新的工具或 LLM 提供商
- 开发环境搭建指南

---

## 📄 许可证

本项目基于 [MIT 许可证](LICENSE) 开源。

---

<p align="center">
  Made with ❤️ by <a href="https://venux.io">Venux</a>
</p>
