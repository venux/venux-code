# 配置参考手册

> Venux Code 的所有配置选项详解

---

## 目录

- [配置加载机制](#配置加载机制)
- [完整配置选项](#完整配置选项)
- [.venux-code.json 格式](#venux-codejson-格式)
- [环境变量参考](#环境变量参考)
- [提供商特定配置](#提供商特定配置)

---

## 配置加载机制

Venux Code 使用分层配置系统，优先级从高到低：

```
┌─────────────────────────────────┐
│  1. 环境变量 (VENUX_ 前缀)      │  ← 最高优先级
├─────────────────────────────────┤
│  2. .venux-code.json (项目级)    │
├─────────────────────────────────┤
│  3. ~/.venux-code/config.yaml   │
├─────────────────────────────────┤
│  4. 代码默认值                   │  ← 最低优先级
└─────────────────────────────────┘
```

配置加载代码位于 `src/venux_code/config/settings.py`：

```python
@model_validator(mode="before")
@classmethod
def _merge_config_sources(cls, values: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}

    # Layer 1: 用户配置 YAML
    if _USER_CONFIG_PATH.is_file():
        merged.update(_load_yaml(_USER_CONFIG_PATH))

    # Layer 2: 项目配置 JSON
    project_cfg = _find_project_config()
    if project_cfg is not None:
        merged.update(_load_json(project_cfg))

    # Layer 3: 环境变量 / 显式参数
    merged.update(values)

    return merged
```

### 项目配置文件查找

系统从当前工作目录向上逐级查找 `.venux-code.json`：

```
/home/user/projects/myapp/
  ├── .venux-code.json  ← 找到！
  └── src/
      └── main.py       ← 从这里开始查找
```

---

## 完整配置选项

### 通用设置

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `app_name` | `str` | `"venux-code"` | 应用名称 |
| `version` | `str` | `"0.1.0"` | 版本号 |
| `debug` | `bool` | `False` | 调试模式 |
| `log_level` | `str` | `"INFO"` | 日志级别（DEBUG/INFO/WARNING/ERROR） |
| `data_dir` | `Path` | `~/.venux-code/data` | 数据存储目录 |
| `session_dir` | `Path` | `~/.venux-code/sessions` | 会话存储目录 |

### LLM 设置 (`llm.*`)

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `llm.provider` | `str` | `"openai"` | LLM 提供商名称 |
| `llm.model` | `str` | `"gpt-4o"` | 模型名称 |
| `llm.api_key` | `str?` | `None` | API Key（建议用环境变量） |
| `llm.base_url` | `str?` | `None` | 自定义 API 地址 |
| `llm.max_tokens` | `int` | `4096` | 最大输出 token 数 |
| `llm.temperature` | `float` | `0.7` | 温度参数（0.0-2.0） |

### 权限设置 (`permission.*`)

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `permission.auto_approve` | `bool` | `False` | 全局自动批准所有工具 |
| `permission.auto_approve_tools` | `list[str]` | `[]` | 自动批准的工具名列表 |
| `permission.denied_tools` | `list[str]` | `[]` | 禁止使用的工具名列表 |

### 数据库设置 (`database.*`)

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `database.url` | `str` | `sqlite+aiosqlite:///./venux-code.db` | 数据库连接 URL |
| `database.echo` | `bool` | `False` | 是否输出 SQL 日志 |

---

## .venux-code.json 格式

项目级配置文件，放在项目根目录：

```json
{
  "llm": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "api_key": null,
    "base_url": null,
    "max_tokens": 8192,
    "temperature": 0.3
  },
  "permission": {
    "auto_approve": false,
    "auto_approve_tools": ["view", "grep", "glob", "ls"],
    "denied_tools": []
  },
  "database": {
    "url": "sqlite+aiosqlite:///./.venux-code.db",
    "echo": false
  },
  "debug": false,
  "log_level": "INFO"
}
```

### 最小配置

```json
{
  "llm": {
    "provider": "openai",
    "model": "gpt-4o"
  }
}
```

### 多环境配置

可以通过不同目录的 `.venux-code.json` 实现多环境配置：

```
project/
├── .venux-code.json              # 开发环境
├── tests/
│   └── .venux-code.json          # 测试环境（更小的模型）
└── production/
    └── .venux-code.json          # 生产环境
```

---

## 环境变量参考

所有配置都可以通过环境变量覆盖。格式为 `VENUX_` 前缀 + 配置路径，嵌套用 `__` 分隔：

### 通用环境变量

```bash
# 调试模式
export VENUX_DEBUG=true

# 日志级别
export VENUX_LOG_LEVEL=DEBUG

# 数据目录
export VENUX_DATA_DIR=/custom/data/path
```

### LLM 环境变量

```bash
# 提供商
export VENUX_LLM__PROVIDER=openai

# 模型
export VENUX_LLM__MODEL=gpt-4o

# API Key（推荐使用此方式，避免明文写入配置文件）
export VENUX_LLM__API_KEY=*** VENUX_LLM__BASE_URL=https://api.example.com/v1

# 生成参数
export VENUX_LLM__MAX_TOKENS=8192
export VENUX_LLM__TEMPERATURE=0.5
```

### 权限环境变量

```bash
# 全局自动批准
export VENUX_PERMISSION__AUTO_APPROVE=true

# 自动批准的工具（JSON 数组格式）
export VENUX_PERMISSION__AUTO_APPROVE_TOOLS='["view","grep","glob"]'

# 禁止的工具
export VENUX_PERMISSION__DENIED_TOOLS='["bash"]'
```

### 数据库环境变量

```bash
export VENUX_DATABASE__URL=postgresql+asyncpg://user:pass@localhost/venux
export VENUX_DATABASE__ECHO=true
```

### 各提供商 API Key 环境变量

```bash
export OPENAI_API_KEY=*** export ANTHROPIC_API_KEY=*** export GOOGLE_API_KEY=*** export DEEPSEEK_API_KEY=*** export MIMO_API_KEY=*** export KIMI_API_KEY=*** export OPENROUTER_API_KEY=*** ```

---

## 提供商特定配置

### OpenAI

```yaml
# ~/.venux-code/config.yaml
llm:
  provider: openai
  model: gpt-4o            # 可选: gpt-4o-mini, o1, o1-mini
  api_key: sk-xxx
  # base_url: https://api.openai.com/v1  # 默认值，可省略
  max_tokens: 4096
  temperature: 0.7
```

### Anthropic

```yaml
llm:
  provider: anthropic
  model: claude-sonnet-4-20250514  # 可选: claude-3.5-haiku
  api_key: sk-ant-xxx
  max_tokens: 8192
  temperature: 0.3
```

### Google Gemini

```yaml
llm:
  provider: google          # 或 gemini
  model: gemini-2.0-flash   # 可选: gemini-1.5-pro
  api_key: AIza-xxx
  max_tokens: 4096
  temperature: 0.7
```

### DeepSeek

```yaml
llm:
  provider: deepseek
  model: deepseek-chat      # 或 deepseek-coder
  api_key: sk-xxx
  base_url: https://api.deepseek.com
  max_tokens: 4096
  temperature: 0.7
```

### MiMo

```yaml
llm:
  provider: mimo
  model: MiMo-7B
  api_key: xxx
  base_url: https://api.mimo.example.com
  max_tokens: 4096
  temperature: 0.7
```

### Kimi / Moonshot

```yaml
llm:
  provider: kimi            # 或 moonshot
  model: moonshot-v1-128k   # 可选: moonshot-v1-8k, moonshot-v1-32k
  api_key: sk-xxx
  base_url: https://api.moonshot.cn/v1
  max_tokens: 4096
  temperature: 0.7
```

### OpenRouter

```yaml
llm:
  provider: openrouter
  model: anthropic/claude-3.5-sonnet  # 使用 provider/model 格式
  api_key: sk-or-xxx
  base_url: https://openrouter.ai/api/v1
  max_tokens: 4096
  temperature: 0.7
```

### 自定义 / 兼容 OpenAI API 的服务

```yaml
llm:
  provider: openai          # 使用 openai 提供商
  model: custom-model
  api_key: xxx
  base_url: https://your-api.example.com/v1  # 自定义地址
  max_tokens: 4096
  temperature: 0.7
```

---

## 权限配置示例

### 完全自动化（适合 CI/CD）

```json
{
  "permission": {
    "auto_approve": true,
    "denied_tools": []
  }
}
```

### 保守模式（只读自动批准）

```json
{
  "permission": {
    "auto_approve": false,
    "auto_approve_tools": ["view", "grep", "glob", "ls"],
    "denied_tools": ["bash"]
  }
}
```

### 安全模式（全部手动审批）

```json
{
  "permission": {
    "auto_approve": false,
    "auto_approve_tools": [],
    "denied_tools": []
  }
}
```

---

## 配置验证

运行 `venux-code doctor` 可以验证当前配置是否正确：

```bash
$ venux-code doctor
  ✓ Configuration: Loaded successfully
  ✓ Database: Connected
  ✓ LLM connectivity: Reachable
  ✓ Dependencies: textual & rich installed

All checks passed.
```

查看当前生效的配置：

```bash
$ venux-code config
```
