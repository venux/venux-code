# 架构设计文档

> Venux Code 的架构深度解析

---

## 目录

- [模块依赖图](#模块依赖图)
- [各模块职责](#各模块职责)
- [数据流](#数据流)
- [Agent 循环详解](#agent-循环详解)
- [Provider 抽象层](#provider-抽象层)
- [工具系统设计](#工具系统设计)
- [事件系统 (PubSub)](#事件系统-pubsub)

---

## 模块依赖图

```
                          ┌─────────────┐
                          │  cli/main   │
                          │  (Typer)    │
                          └──────┬──────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
             ┌──────────┐ ┌──────────┐ ┌──────────┐
             │ cli/app  │ │ tui/app  │ │ config/  │
             │ (引导)    │ │ (Textual)│ │ settings │
             └────┬─────┘ └────┬─────┘ └────┬─────┘
                  │            │             │
                  ▼            ▼             │
             ┌─────────────────────┐        │
             │   llm/agent/agent   │◀───────┘
             │   (VenuxAgent)      │
             │   (LangGraph)       │
             └────────┬────────────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
   ┌───────────┐ ┌──────────┐ ┌──────────┐
   │ providers/ │ │  tools/  │ │ message/ │
   │ registry  │ │ registry │ │ models   │
   └─────┬─────┘ └────┬─────┘ └──────────┘
         │            │
   ┌─────▼─────┐ ┌────▼─────┐
   │ providers/ │ │  tools/  │
   │ base +    │ │ base +   │
   │ impls     │ │ impls    │
   └───────────┘ └──────────┘

   ┌───────────┐ ┌──────────┐ ┌──────────┐
   │   pubsub/ │ │permission│ │   db/    │
   │  broker   │ │ service  │ │ engine   │
   └───────────┘ └──────────┘ └──────────┘
```

---

## 各模块职责

### `config/settings.py` — 配置管理

负责从多个来源加载和合并配置：

```python
# 配置加载优先级（高 → 低）：
# 1. 环境变量（VENUX_ 前缀）
# 2. 项目配置（.venux-code.json）
# 3. 用户配置（~/.venux-code/config.yaml）
# 4. 代码默认值

class Settings(BaseSettings):
    app_name: str = "venux-code"
    version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"
    llm: LLMProviderSettings = Field(default_factory=LLMProviderSettings)
    permission: PermissionSettings = Field(default_factory=PermissionSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
```

关键设计：
- 使用 `pydantic-settings` 实现类型安全的配置
- `@model_validator(mode="before")` 在验证前合并文件源
- 单例模式 `get_settings()` 确保全局一致

### `llm/agent/agent.py` — 智能体核心

基于 LangGraph 的有状态智能体，实现"思考-行动"循环：

```python
class VenuxAgent:
    def __init__(self, *, model, tools, system_prompt, max_iterations):
        self._model_with_tools = model.bind_tools(self._tools)
        self._graph = self._build_graph()  # 编译 StateGraph

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("call_llm", self._call_llm)
        graph.add_node("execute_tools", ToolNode(self._tools))
        graph.set_entry_point("call_llm")
        graph.add_conditional_edges("call_llm", self._should_continue, {
            "execute_tools": "execute_tools",
            "end": END,
        })
        graph.add_edge("execute_tools", "call_llm")
        return graph.compile()
```

### `llm/providers/` — LLM 提供商层

- **`base.py`**：抽象基类 `BaseLLMProvider`，定义 `chat()` 和 `stream_chat()` 接口
- **`registry.py`**：`ProviderRegistry` 通过懒加载映射创建提供商实例
- **具体实现**：`openai_provider.py`、`anthropic_provider.py` 等

```python
_PROVIDER_CLASSES = {
    "openai": "venux_code.llm.providers.openai_provider:OpenAIProvider",
    "anthropic": "venux_code.llm.providers.anthropic_provider:AnthropicProvider",
    "google": "venux_code.llm.providers.google_provider:GoogleProvider",
    # ...
}
```

### `llm/tools/` — 工具系统

- **`base.py`**：`BaseTool` 抽象基类 + `ToolResponse` 数据类
- **`registry.py`**：`ToolRegistry` 统一注册和管理工具
- **具体工具**：`BashTool`、`EditTool`、`ViewTool` 等

### `permission/service.py` — 权限服务

基于四元组 `(session_id, tool, action, path)` 的权限检查：

```python
class PermissionService:
    @staticmethod
    async def request(session_id, tool, action, path, auto_approve, ...):
        if auto_approve or tool in auto_approve_tools:
            return PermissionDecision(granted=True, auto_approved=True)
        if tool in denied_tools:
            return PermissionDecision(granted=False, denied=True)
        return PermissionDecision(granted=False, denied=False)  # pending
```

### `pubsub/broker.py` — 事件总线

轻量级异步发布/订阅代理：

```python
class AsyncBroker(Generic[T]):
    async def publish(self, message: T) -> int
    async def subscribe(self, maxsize=0) -> AsyncGenerator[Queue[T]]
```

### `db/` — 数据层

- **`engine.py`**：SQLAlchemy 异步引擎工厂
- **`models.py`**：数据库表模型（Session、Message、Permission 等）
- **`session/service.py`**：会话管理服务

### `message/models.py` — 消息模型

领域模型，与数据库模型分离：

```python
class Message(BaseModel):
    id: str
    session_id: str
    role: MessageRole  # user | assistant | tool | system
    content: Optional[str]
    tool_calls: list[ToolCall]
    tokens_in: int
    tokens_out: int
    cost: float
```

### `tui/` — 终端界面

基于 Textual 的全屏 TUI：

- **`app.py`**：`VenuxTUI` 主应用，管理布局和事件
- **`widgets/chat.py`**：`ChatDisplay` 聊天显示组件
- **`widgets/input.py`**：`ChatInput` 多行输入组件
- **`widgets/sidebar.py`**：`SessionSidebar` 会话列表
- **`widgets/status.py`**：`StatusBar` 状态栏
- **`themes.py`**：主题管理

---

## 数据流

### 完整请求流程

```
用户输入 "用 Python 实现快速排序"
         │
         ▼
┌──────────────────┐
│  CLI / TUI 层    │
│  捕获用户输入     │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  VenuxAgent.run() │
│  创建 HumanMessage │
│  构建初始 AgentState │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────────────┐
│          LangGraph StateGraph            │
│                                          │
│  ┌──────────┐     ┌──────────────────┐  │
│  │ call_llm │────▶│ should_continue  │  │
│  │          │     │                  │  │
│  │ 1. 添加   │     │ last message    │  │
│  │ system   │     │ 有 tool_calls?   │  │
│  │ prompt   │     │                  │  │
│  │ 2. 裁剪   │     │ 是 → execute_tools│
│  │ context  │     │ 否 → END         │  │
│  │ 3. 调用   │     └──────────────────┘  │
│  │ LLM      │              │             │
│  └──────────┘              │             │
│       ▲                    ▼             │
│       │         ┌──────────────────┐    │
│       │         │  execute_tools   │    │
│       │         │                  │    │
│       └─────────│  ToolNode 执行   │    │
│                 │  bash/edit/...   │    │
│                 │  返回 ToolMessage │    │
│                 └──────────────────┘    │
└──────────────────────────────────────────┘
         │
         ▼
┌──────────────────┐
│  AsyncIterator   │
│  of AgentEvent   │
│                  │
│  - LLM_TOKEN     │  → 流式显示
│  - TOOL_CALL_*   │  → 显示工具调用
│  - AGENT_DONE    │  → 完成
│  - ERROR         │  → 错误处理
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  UI 更新          │
│  渲染 Markdown    │
│  更新状态栏       │
└──────────────────┘
```

---

## Agent 循环详解

### LangGraph StateGraph

VenuxAgent 使用 LangGraph 的 `StateGraph` 定义有状态的工作流：

```python
# 状态定义
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], _merge_messages]  # 消息历史
    session_id: str                                           # 会话 ID
    tools_called: Annotated[list[str], _merge_messages]       # 已调用工具
    is_done: bool                                             # 完成标志
    iteration: int                                            # 迭代计数
```

### 循环流程

1. **`call_llm` 节点**：
   - 注入系统提示词（如果配置了）
   - 裁剪上下文到 `CONTEXT_CHAR_BUDGET`（120K 字符 ≈ 30K token）
   - 调用 LLM（`await self._model_with_tools.ainvoke(messages)`）
   - 返回 `AIMessage`（可能包含 `tool_calls`）

2. **`_should_continue` 决策函数**：
   - 检查迭代计数是否达到 `MAX_ITERATIONS`（50）
   - 检查最后一条消息是否包含 `tool_calls`
   - 返回 `"execute_tools"` 或 `"end"`

3. **`execute_tools` 节点**：
   - 使用 LangGraph 内置的 `ToolNode`
   - 并行执行所有工具调用
   - 返回 `ToolMessage` 结果

4. **循环回到 `call_llm`**：LLM 接收工具结果后继续推理

### 上下文裁剪策略

```python
@staticmethod
def _enforce_context_budget(messages, budget=120_000):
    # 1. 保留系统消息（如果有）
    # 2. 保留最后一条用户消息
    # 3. 从最旧的中间消息开始丢弃，直到总字符数 <= budget
    while total > budget:
        body.pop(0)  # 丢弃最旧的
```

---

## Provider 抽象层

### 接口定义

```python
class BaseLLMProvider(ABC):
    def __init__(self, *, api_key, model_name, max_tokens=4096,
                 temperature=0.7, base_url=None):

    @abstractmethod
    def _build_model(self, *, stream=False, tools=None) -> BaseChatModel:
        """返回配置好的 LangChain BaseChatModel 实例"""

    @abstractmethod
    def model_info(self) -> ModelInfo:
        """返回模型元数据"""

    async def chat(self, messages, *, tools=None, stream=False) -> ChatResponse:
        """发送消息并返回标准化响应"""

    async def stream_chat(self, messages, *, tools=None) -> AsyncIterator[str]:
        """流式返回增量文本"""
```

### 注册机制

```python
# 懒加载映射：只在实际使用时才导入
_PROVIDER_CLASSES = {
    "openai": "venux_code.llm.providers.openai_provider:OpenAIProvider",
    # ...
}

class ProviderRegistry:
    def register(self, name, dotted_path):
        """运行时注册新提供商"""

    def create(self, name=None, *, settings=None, **overrides) -> BaseLLMProvider:
        """实例化提供商，合并配置和覆盖参数"""

    def available(self) -> list[str]:
        """返回所有可用提供商名称"""
```

---

## 工具系统设计

### BaseTool 接口

```python
class BaseTool(ABC):
    name: str                              # LLM 使用的唯一标识
    description: str                       # 自然语言描述
    requires_permission: bool = False      # 是否需要用户授权
    parameters_schema: type[BaseModel]     # Pydantic 参数模型

    @abstractmethod
    async def execute(self, params: dict) -> ToolResponse:
        """执行工具并返回标准化响应"""

    def to_langchain_tool(self) -> StructuredTool:
        """转换为 LangChain StructuredTool 供 Agent 使用"""
```

### ToolResponse 格式

```python
@dataclass
class ToolResponse:
    success: bool                          # 是否成功
    output: str = ""                       # 可读输出
    error: str | None = None               # 错误信息
    metadata: dict[str, Any]               # 额外数据
    display_type: str = "text"             # UI 渲染提示
```

### 工具注册表

```python
class ToolRegistry:
    def __init__(self, *, include_defaults=True):
        # 默认注册 7 个工具
        _DEFAULT_TOOLS = [BashTool, EditTool, GlobTool, GrepTool,
                          LsTool, ViewTool, WriteTool]

    def register(self, tool: BaseTool)     # 注册工具
    def unregister(self, name: str)        # 移除工具
    def get(self, name) -> BaseTool        # 获取工具
    def as_langchain_tools(self) -> list   # 转换为 LangChain 工具
    def get_tools_requiring_permission()   # 获取需要权限的工具
```

---

## 事件系统 (PubSub)

### AsyncBroker

进程内的异步发布/订阅代理，用于解耦组件间通信：

```python
broker: AsyncBroker[AgentEvent] = AsyncBroker()

# 发布方（Agent）
await broker.publish(AgentEvent(
    type=AgentEventType.LLM_TOKEN,
    data={"token": "print"},
))

# 订阅方（UI）
async with broker.subscribe() as queue:
    event = await queue.get()
    # 处理事件...
```

### 事件类型

```python
class AgentEventType(str, Enum):
    LLM_TOKEN = "llm_token"                    # LLM 流式 token
    TOOL_CALL_START = "tool_call_start"         # 工具开始执行
    TOOL_CALL_RESULT = "tool_call_result"       # 工具执行结果
    TOOL_PERMISSION_NEEDED = "tool_permission_needed"  # 需要权限
    AGENT_DONE = "agent_done"                   # Agent 完成
    ERROR = "error"                             # 错误
```

### 使用场景

1. **TUI 流式更新**：UI 订阅 `LLM_TOKEN` 事件实时显示文本
2. **权限审批**：`TOOL_PERMISSION_NEEDED` 触发权限对话框
3. **日志记录**：订阅所有事件写入日志
4. **会话持久化**：监听事件保存消息到数据库

---

## 设计原则

1. **关注点分离**：每层只负责自己的职责
2. **依赖倒置**：通过抽象接口（BaseTool、BaseLLMProvider）解耦
3. **懒加载**：Provider 使用字符串路径延迟导入，避免未使用的依赖报错
4. **异步优先**：所有 I/O 操作都是 async，充分利用 asyncio
5. **类型安全**：Pydantic 模型 + mypy strict 模式
6. **可测试性**：单例可通过 `reset_settings()` 重置，方便测试
