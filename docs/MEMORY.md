# Venux Code 记忆系统

## 概述

记忆系统让 Venux Code 能够在会话之间持久保存重要信息，包括用户偏好、项目知识、工具用法等。系统支持全文搜索、信任评分和实体解析（去重）。

## 架构

```
MemoryService          ← 高层 API（add/search/flush/nudge）
    │
    ├── BuiltinMemoryProvider   ← 轻量级：内存缓存 + SQLite
    │
    └── HolographicMemoryProvider  ← 高级：FTS5 全文搜索 + 实体解析 + 信任评分
```

## 记忆分类 (MemoryCategory)

| 分类          | 说明                       | 示例                          |
|---------------|----------------------------|-------------------------------|
| `user_pref`   | 用户偏好                   | "我喜欢用 dark mode"          |
| `project`     | 项目相关信息               | "本项目使用 FastAPI 框架"     |
| `tool`        | 工具/命令相关              | "部署脚本在 scripts/deploy.sh"|
| `general`     | 通用知识                   | "Python 3.12 支持 type alias" |

## 核心 API

### 添加记忆

```python
from venux_code.memory import MemoryService, MemoryCategory

service = MemoryService(provider)

entry = await service.add(
    content="用户偏好使用 TypeScript 而非 JavaScript",
    category=MemoryCategory.USER_PREF,
    tags=["typescript", "偏好"],
)
```

### 搜索记忆

```python
results = await service.search("TypeScript", limit=5, min_trust=0.3)
for entry in results:
    print(entry.content, entry.trust_score)
```

### 更新 / 删除

```python
await service.update(entry.id, "用户强烈偏好 TypeScript")
await service.remove(entry.id)
```

### 用户画像

```python
from venux_code.memory.models import UserProfile

profile = UserProfile(
    name="张三",
    role="全栈开发者",
    preferences={"language": "zh-CN", "editor": "vim"},
    environment={"os": "macOS", "shell": "zsh"},
)
await service.update_user_profile(profile)

current = await service.get_user_profile()
```

### 会话记忆 Nudge

Nudge 机制会在用户消息累积到阈值后提示 agent 考虑保存记忆：

```python
should_save = await service.nudge(session_id)
if should_save:
    # Agent 应考虑将当前对话中的重要信息存入记忆
    pass
```

### 批量刷新 (Flush)

从一段对话中自动提取并保存记忆：

```python
messages = [
    {"role": "user", "content": "我总是喜欢用 pytest 而不是 unittest"},
    {"role": "assistant", "content": "好的，我记住了。"},
]
saved = await service.flush_memories(session_id, messages)
# saved[0].content → "我总是喜欢用 pytest 而不是 unittest"
# saved[0].category → MemoryCategory.USER_PREF
```

## 提供者对比

### BuiltinMemoryProvider

- 内存缓存 + SQLite 持久化
- 简单关键词搜索
- 适合个人使用、轻量场景

### HolographicMemoryProvider

- **FTS5 全文搜索**：利用 SQLite FTS5 虚拟表实现高效全文检索
- **实体解析**：自动检测并合并相似记忆（Jaccard 相似度 > 0.6）
- **信任评分**：基于用户反馈（👍/👎）使用 Wilson 置信区间计算
- **语义关键词提取**：自动从内容中提取高频关键词

```python
from venux_code.memory.holographic_provider import HolographicMemoryProvider

provider = HolographicMemoryProvider()
service = MemoryService(provider)

# 记录反馈以调整信任分
await provider.record_feedback(entry.id, positive=True)
```

## 存储位置

| 提供者                      | 默认数据库路径                              |
|-----------------------------|---------------------------------------------|
| BuiltinMemoryProvider       | `~/.venux-code/memory.db`                   |
| HolographicMemoryProvider   | `~/.venux-code/holographic_memory.db`       |

## 配置

记忆系统通过 `Settings` 中的以下字段配置（环境变量前缀 `VENUX_`）：

- `VENUX_DATA_DIR` — 数据目录（默认 `~/.venux-code/data`）

## 提取规则

`flush_memories` 使用启发式规则从用户消息中提取记忆：

- 包含 "prefer/like/love/hate" 等词 → `user_pref`
- 包含 "framework/library/config" 等词 → `project`
- 包含 "tool/command/script" 等词 → `tool`
- 最少 15 字符的句子才会被提取
- 自动提取引号内容、文件扩展名、#标签 作为 tags
