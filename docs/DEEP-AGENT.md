# Deep Agent 模式

## 概述

Deep Agent 是 Venux Code 的高级代理模式，用于处理复杂的、多步骤的目标。它将任务分解为三个阶段：

1. **规划阶段 (PlanningPhase)**：分析目标，生成结构化执行计划
2. **执行阶段 (ExecutionPhase)**：按计划逐步执行，使用工具完成每个步骤
3. **审查阶段 (ReviewPhase)**：验证结果，检测失败，决定是否重试

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                     DeepAgent                           │
│                                                         │
│  ┌─────────┐    ┌──────────────┐    ┌──────────┐       │
│  │Planning │───▶│  Execution   │───▶│  Review  │       │
│  │ Phase   │    │    Phase     │    │  Phase   │       │
│  └─────────┘    └──────────────┘    └──────────┘       │
│       │               │                   │             │
│       ▼               ▼                   ▼             │
│  ┌─────────┐    ┌──────────────┐    ┌──────────┐       │
│  │  Plan   │    │   Step       │    │  Retry   │       │
│  │  JSON   │    │   Results    │    │  Loop    │       │
│  └─────────┘    └──────────────┘    └──────────┘       │
│                      │                                  │
│                      ▼                                  │
│              ┌──────────────┐                           │
│              │ Filesystem   │                           │
│              │ Middleware   │                           │
│              └──────────────┘                           │
└─────────────────────────────────────────────────────────┘
```

## 使用方法

### 基本用法

```python
from venux_code.llm.agent.deep_agent import DeepAgent
from venux_code.llm.providers.registry import create_provider
from venux_code.llm.tools.registry import ToolRegistry

# 初始化
provider = create_provider("openai")
model = provider._build_model()
registry = ToolRegistry()

# 创建 Deep Agent
agent = DeepAgent(
    model=model,
    tools=registry.as_langchain_tools(),
    system_prompt="你是一个专业的软件工程师。",
    max_retries=2,
    save_intermediate=True,
    session_id="my-session",
)

# 运行
async for event in agent.run("重构认证模块，提升安全性"):
    if event.event_type == "plan_created":
        print(f"计划已创建: {event.data['steps']} 个步骤")
    elif event.event_type == "step_done":
        print(f"步骤 {event.data['step_id']}: {event.data['status']}")
    elif event.event_type == "success":
        print(f"任务完成: {event.data['summary']}")
```

### 事件类型

Deep Agent 在执行过程中会发出以下事件：

| 阶段 | 事件类型 | 说明 |
|------|----------|------|
| Planning | `start` | 开始规划 |
| Planning | `plan_created` | 计划已创建 |
| Planning | `error` | 规划失败 |
| Execution | `execution_start` | 开始执行 |
| Execution | `step_done` | 单步完成 |
| Execution | `execution_done` | 执行阶段完成 |
| Review | `review_start` | 开始审查 |
| Review | `review_done` | 审查完成 |
| Done | `success` | 目标达成 |
| Done | `partial_success` | 部分完成 |
| Done | `failed` | 执行失败 |
| Done | `max_retries_exceeded` | 超过最大重试次数 |

### 事件数据

```python
# plan_created 事件
{
    "steps": 5,
    "complexity": "medium",
    "reasoning": "需要修改 3 个模块..."
}

# step_done 事件
{
    "step_id": 1,
    "status": "success",
    "result": "已创建新的认证中间件..."
}

# review_done 事件
{
    "goal_achieved": True,
    "confidence": 0.85,
    "issues": [],
    "summary": "认证模块已成功重构"
}
```

## 执行计划

PlanningPhase 会生成结构化的执行计划：

```json
{
  "goal": "重构认证模块",
  "reasoning": "当前认证模块存在安全问题...",
  "estimated_complexity": "high",
  "steps": [
    {
      "id": 1,
      "description": "分析现有认证代码",
      "tools_hint": ["view", "grep"],
      "depends_on": [],
      "status": "pending"
    },
    {
      "id": 2,
      "description": "设计新的认证架构",
      "tools_hint": ["write"],
      "depends_on": [1],
      "status": "pending"
    }
  ]
}
```

## 文件系统中间件

当 `save_intermediate=True` 时，Deep Agent 会将中间结果保存到：

```
.venux/deep/<session_id>/
├── plan.json          # 执行计划
├── step_1.json        # 步骤 1 结果
├── step_2.json        # 步骤 2 结果
├── ...
└── review.json        # 审查结果
```

这些文件可用于：
- **调试**：查看每步的执行详情
- **恢复**：从中断处继续执行
- **审计**：记录完整的执行历史

## 重试机制

当 ReviewPhase 检测到问题时：

1. 标记需要重试的步骤
2. 将这些步骤状态重置为 `pending`
3. 重新执行失败的步骤
4. 再次审查结果

最大重试次数由 `max_retries` 参数控制（默认 2 次）。

## 与普通 Agent 的区别

| 特性 | 普通 Agent | Deep Agent |
|------|-----------|------------|
| 处理方式 | 单轮对话 | 多阶段执行 |
| 规划 | 无 | 自动生成计划 |
| 重试 | 无 | 自动重试失败步骤 |
| 中间结果 | 不保存 | 持久化到磁盘 |
| 适用场景 | 简单任务 | 复杂、多步骤目标 |

## 最佳实践

### 1. 明确的目标描述

```python
# 好的目标
"重构 src/auth/ 模块，使用 JWT 替换 session 认证，确保所有测试通过"

# 不好的目标
"改进代码"
```

### 2. 合理的工具配置

```python
# 根据任务配置相关工具
agent = DeepAgent(
    model=model,
    tools=[
        *registry.as_langchain_tools(),  # 基础工具
        custom_tool,                      # 自定义工具
    ],
)
```

### 3. 监控执行过程

```python
async for event in agent.run(goal):
    # 记录所有事件用于调试
    logger.info(f"{event.phase}/{event.event_type}: {event.data}")

    # 处理错误
    if event.event_type == "error":
        notify_user(f"执行出错: {event.data['error']}")
```

### 4. 设置合理的超时

```python
import asyncio

try:
    async with asyncio.timeout(300):  # 5 分钟超时
        async for event in agent.run(goal):
            handle(event)
except asyncio.TimeoutError:
    print("任务执行超时")
```

## 限制

- **不支持并行步骤**：当前版本按顺序执行步骤
- **工具调用限制**：每步最多 15 次工具调用（可配置）
- **重试限制**：最多 2 次重试（可配置）
- **无状态恢复**：虽然保存中间结果，但不支持从断点恢复（计划中）
