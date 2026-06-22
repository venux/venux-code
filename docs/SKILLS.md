# Venux Code 技能系统

## 概述

技能系统管理可复用的操作流程和指令集。技能以 Markdown 格式存储，可以从本地目录、项目目录或远程 Hub 加载，也可以从对话中自动提取。

## 架构

```
SkillService       ← 高层 API（list/get/install/create/auto_create）
    │
    └── SkillLoader    ← 文件发现与远程加载
            │
            ├── ~/.venux-code/skills/     ← 用户级技能
            ├── .venux-code/skills/       ← 项目级技能
            └── https://hub.venux-code.dev/ ← 远程技能 Hub
```

## 技能来源 (SkillSource)

| 来源       | 说明                           |
|------------|--------------------------------|
| `local`    | 用户创建于 `~/.venux-code/skills/` |
| `project`  | 项目级 `.venux-code/skills/`       |
| `hub`      | 从远程 Hub 或 URL 安装             |
| `auto`     | 从对话中自动提取                   |

## SKILL.md 文件格式

每个技能是一个 Markdown 文件，支持 YAML frontmatter：

```markdown
---
name: deploy-checklist
description: 部署前检查清单
category: devops
tags: deploy, ci, production
version: 1.0.0
---

# 部署检查清单

## 步骤

1. 运行测试套件：`pytest --cov`
2. 检查代码风格：`ruff check .`
3. 构建 Docker 镜像
4. 推送到 registry
5. 更新 K8s 部署
```

### 目录结构

```
~/.venux-code/skills/
├── deploy-checklist/
│   └── SKILL.md          # 子目录形式
├── code-review.md         # 或直接放 .md 文件
└── ...

.venux-code/skills/        # 项目级（同结构）
├── project-build/
│   └── SKILL.md
└── ...
```

## 核心 API

### 列出技能

```python
from venux_code.skills import SkillService

service = SkillService()

all_skills = await service.list_skills()
devops_skills = await service.list_skills(category="devops")
```

### 获取技能

```python
skill = await service.get("deploy-checklist")
if skill:
    print(skill.content)
```

### 加载技能内容（注入 LLM 上下文）

```python
content = await service.load_skill("deploy-checklist")
if content:
    # 将 content 注入到 system prompt 或 context 中
    pass
```

### 创建技能

```python
skill = await service.create(
    name="git-workflow",
    content="# Git 工作流\n\n1. 创建 feature 分支\n2. 提交 PR\n...",
    category="git",
    description="标准 Git 工作流",
    tags=["git", "workflow"],
)
```

### 从远程安装

```python
# 从 Hub 安装
skill = await service.install("code-review")

# 从 URL 安装
skill = await service.install("https://example.com/my-skill.md")
```

### 卸载技能

```python
removed = await service.uninstall("old-skill")
```

### 自动创建

从一段对话中自动提取可复用的操作流程：

```python
conversation = [
    {"role": "user", "content": "帮我设置 CI/CD 流水线"},
    {"role": "assistant", "content": "我来使用 tool_call: setup_pipeline"},
    {"role": "assistant", "content": "接下来 tool_call: configure_webhook"},
    {"role": "assistant", "content": "完成！流水线已配置好。"},
]

skill = await service.auto_create(session_id, conversation)
if skill:
    print(f"自动创建了技能: {skill.name}")
```

自动创建条件：
- 对话中至少包含 2 次工具调用
- 有用户提出的目标/需求
- 提取的内容会包含步骤列表和注意事项

## 存储

技能数据存储在 `~/.venux-code/skills.db`（SQLite），同时文件系统中的 SKILL.md 会被同步加载。

优先级：数据库中的版本 > 文件系统版本。

## 与记忆系统的协作

技能和记忆是互补的：

- **记忆**：存储零散的知识片段（偏好、事实、环境信息）
- **技能**：存储结构化的操作流程（步骤、检查清单、模板）

在会话中，agent 可以同时加载相关记忆和技能来获得完整的上下文。

## 最佳实践

1. **命名清晰**：技能名应反映其用途，如 `deploy-checklist` 而非 `skill1`
2. **添加描述**：frontmatter 中的 `description` 帮助 agent 选择合适的技能
3. **使用标签**：`tags` 方便按主题筛选
4. **版本管理**：更新技能时递增 `version` 字段
5. **项目技能优先**：项目级技能应放在 `.venux-code/skills/` 中以跟随版本控制
