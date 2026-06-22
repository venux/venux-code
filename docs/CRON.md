# 定时任务系统 (Cron System)

## 概述

Venux Code 的定时任务系统允许用户创建、管理和执行定时任务。系统基于 APScheduler，支持多种调度方式，并可将执行结果投递到不同渠道。

## 架构

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  CronService │────▶│CronScheduler │────▶│  JobRunner   │
│  (管理 API)  │     │ (APScheduler)│     │ (执行引擎)   │
└──────────────┘     └──────────────┘     └──────────────┘
       │                                        │
       ▼                                        ▼
  JSON 持久化                              Agent / Script
```

### 核心组件

| 组件 | 文件 | 职责 |
|------|------|------|
| **CronJob** | `models.py` | 任务数据模型 |
| **CronScheduler** | `scheduler.py` | APScheduler 包装，管理触发器 |
| **CronService** | `service.py` | 高层 API，提供 CRUD 操作 |
| **JobRunner** | `runner.py` | 任务执行引擎 |

## 使用方法

### 通过 CronService 管理任务

```python
from venux_code.cron import CronService, CronJob, CronSchedule, ScheduleType

# 初始化服务
service = CronService()
await service.start()

# 创建定时任务
job = CronJob(
    name="每日代码审查",
    schedule=CronSchedule(
        type=ScheduleType.CRON,
        expression="0 9 * * 1-5",  # 工作日 9:00
        timezone="Asia/Shanghai",
    ),
    prompt="审查 src/ 目录下的代码变更，生成报告",
    skills=["code-review", "git"],
)
await service.add(job)

# 创建间隔任务
job = CronJob(
    name="健康检查",
    schedule=CronSchedule(
        type=ScheduleType.INTERVAL,
        minutes=30,
    ),
    prompt="检查服务健康状态",
)
await service.add(job)

# 创建一次性任务
from datetime import datetime, timedelta

job = CronJob(
    name="紧急修复",
    schedule=CronSchedule(
        type=ScheduleType.DATE,
        run_at=datetime.now() + timedelta(hours=1),
    ),
    prompt="执行紧急修复脚本",
    no_agent=True,
    script="python scripts/fix.py",
)
await service.add(job)
```

### 任务管理

```python
# 列出所有任务
jobs = service.list_jobs()
for job in jobs:
    print(f"{job.name} - {'启用' if job.enabled else '禁用'}")

# 暂停/恢复任务
await service.pause(job.id)
await service.resume(job.id)

# 立即执行任务
result = await service.run_now(job.id)
print(f"执行结果: {'成功' if result.success else '失败'}")

# 删除任务
await service.remove(job.id)

# 查看下次执行时间
next_runs = service.get_next_runs()
for job_id, next_time in next_runs.items():
    print(f"{job_id}: {next_time}")
```

## 调度类型

### Cron 表达式

标准 cron 格式：`分 时 日 月 周`

```python
CronSchedule(type=ScheduleType.CRON, expression="*/5 * * * *")   # 每 5 分钟
CronSchedule(type=ScheduleType.CRON, expression="0 9 * * 1-5")   # 工作日 9:00
CronSchedule(type=ScheduleType.CRON, expression="0 0 1 * *")     # 每月 1 号
```

### 间隔调度

```python
CronSchedule(type=ScheduleType.INTERVAL, minutes=30)  # 每 30 分钟
CronSchedule(type=ScheduleType.INTERVAL, hours=2)      # 每 2 小时
CronSchedule(type=ScheduleType.INTERVAL, days=1)       # 每天
```

### 定时执行

```python
from datetime import datetime

CronSchedule(
    type=ScheduleType.DATE,
    run_at=datetime(2025, 1, 15, 10, 0, 0),
)
```

## 执行模式

### Agent 模式（默认）

任务通过 prompt 触发 Agent 执行，支持 skills：

```python
CronJob(
    prompt="分析代码质量并生成报告",
    skills=["code-quality", "reporting"],
)
```

### Script 模式

直接执行 shell 脚本，不经过 Agent：

```python
CronJob(
    no_agent=True,
    script="cd /app && python manage.py clearsessions",
)
```

## 结果投递

```python
from venux_code.cron.models import DeliveryConfig, DeliveryMethod

# 不投递
DeliveryConfig(method=DeliveryMethod.NONE)

# 推送到聊天
DeliveryConfig(method=DeliveryMethod.CHAT)

# Webhook
DeliveryConfig(
    method=DeliveryMethod.WEBHOOK,
    target="https://hooks.example.com/notify",
)

# 邮件（计划中）
DeliveryConfig(
    method=DeliveryMethod.EMAIL,
    target="team@example.com",
)
```

## 持久化

任务自动持久化到 `<data_dir>/cron_jobs.json`，服务重启后自动加载。

## 在 Venux Code 中集成

```python
from venux_code.cron import CronService

# 在应用启动时
cron_service = CronService(agent_factory=my_agent_factory)
await cron_service.start()

# 在应用关闭时
await cron_service.shutdown()
```
