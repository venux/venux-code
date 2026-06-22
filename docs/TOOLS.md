# 工具开发指南

> 如何为 Venux Code 创建自定义工具

---

## 目录

- [BaseTool 接口](#basetool-接口)
- [ToolResponse 格式](#toolresponse-格式)
- [权限系统](#权限系统)
- [完整示例：创建一个新工具](#完整示例创建一个新工具)
- [注册自定义工具](#注册自定义工具)
- [内置工具参考](#内置工具参考)

---

## BaseTool 接口

所有工具都继承 `BaseTool` 抽象基类，位于 `src/venux_code/llm/tools/base.py`：

```python
from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel

class BaseTool(ABC):
    """所有工具的抽象基类。

    子类必须设置：
    - name: LLM 在 tool_calls 中使用的唯一标识
    - description: 自然语言描述，告诉 LLM 何时使用此工具
    - parameters_schema: Pydantic BaseModel 子类，定义参数结构

    可选设置：
    - requires_permission: 是否需要用户授权（默认 False）
    """

    name: str
    description: str
    requires_permission: bool = False
    parameters_schema: type[BaseModel]

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> ToolResponse:
        """执行工具并返回标准化响应。"""
        ...

    def to_langchain_tool(self) -> Any:
        """转换为 LangChain StructuredTool 供 Agent 使用。"""
        from langchain_core.tools import StructuredTool

        schema = self.parameters_schema

        async def _run(**kwargs):
            resp = await self.execute(kwargs)
            return str(resp)

        return StructuredTool.from_function(
            coroutine=_run,
            name=self.name,
            description=self.description,
            args_schema=schema,
        )
```

---

## ToolResponse 格式

工具执行后返回 `ToolResponse` 数据类：

```python
@dataclass
class ToolResponse:
    success: bool                          # 是否成功执行
    output: str = ""                       # 输出文本（成功时显示）
    error: str | None = None               # 错误信息（失败时显示）
    metadata: dict[str, Any] = field(default_factory=dict)  # 额外数据
    display_type: str = "text"             # UI 渲染提示

    # display_type 可选值：
    # - "text":     普通文本（默认）
    # - "code":     代码块（带语法高亮）
    # - "diff":     差异对比
    # - "image":    图片
    # - "markdown": Markdown 渲染
```

### 返回成功结果

```python
return ToolResponse(
    success=True,
    output="文件已成功写入",
    metadata={"path": "/tmp/test.py", "bytes": 1234},
)
```

### 返回错误结果

```python
return ToolResponse(
    success=False,
    error="文件不存在: /tmp/not_found.py",
    metadata={"path": "/tmp/not_found.py"},
)
```

---

## 权限系统

### 设置权限

在工具类中设置 `requires_permission = True`：

```python
class BashTool(BaseTool):
    name = "bash"
    description = "执行 Shell 命令"
    requires_permission = True  # ← 需要用户授权
```

### 权限检查流程

```
Agent 请求调用 bash(command="rm -rf /tmp/test")
         │
         ▼
PermissionService.request(
    session_id="...",
    tool="bash",
    action="execute",
    path="/tmp/test"
)
         │
    ┌────┼────┐
    ▼    │    │
auto_approve=True?  │    │
    │    │    │
    是 → 直接批准   │    │
    │    │    │
    否 → tool in denied_tools?  │
         │    │
         是 → 直接拒绝
         │
         否 → 创建 pending 记录
              等待用户批准/拒绝
```

### 配置权限

在配置文件中控制权限行为：

```json
{
  "permission": {
    "auto_approve": false,
    "auto_approve_tools": ["view", "grep", "glob", "ls"],
    "denied_tools": []
  }
}
```

---

## 完整示例：创建一个新工具

下面以一个 `WebSearchTool` 为例，展示完整的工具开发流程：

### 第一步：定义参数模型

```python
# src/venux_code/llm/tools/web_search_tool.py

from typing import Any, Optional
from pydantic import BaseModel, Field
from .base import BaseTool, ToolResponse


class WebSearchParams(BaseModel):
    """Web 搜索工具的参数定义。"""

    query: str = Field(
        description="搜索查询关键词"
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=20,
        description="最大返回结果数（默认 5，最大 20）"
    )
    language: Optional[str] = Field(
        default=None,
        description="搜索语言（如 zh-CN, en-US），默认自动检测"
    )
```

### 第二步：实现工具类

```python
class WebSearchTool(BaseTool):
    """在互联网上搜索信息。"""

    name = "web_search"
    description = (
        "Search the web for information. "
        "Use this when you need to find current information, "
        "documentation, or answers that are not in the local codebase."
    )
    parameters_schema = WebSearchParams
    requires_permission = False  # 只读操作，不需要权限

    async def execute(self, params: dict[str, Any]) -> ToolResponse:
        """执行搜索。"""
        validated = WebSearchParams(**params)

        try:
            # 实际搜索逻辑
            results = await self._do_search(
                query=validated.query,
                max_results=validated.max_results,
                language=validated.language,
            )

            # 格式化输出
            output_lines = []
            for i, result in enumerate(results, 1):
                output_lines.append(f"### {i}. {result['title']}")
                output_lines.append(f"URL: {result['url']}")
                output_lines.append(f"{result['snippet']}")
                output_lines.append("")

            return ToolResponse(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "query": validated.query,
                    "result_count": len(results),
                },
                display_type="markdown",
            )

        except Exception as exc:
            return ToolResponse(
                success=False,
                error=f"搜索失败: {exc}",
                metadata={"query": validated.query},
            )

    async def _do_search(self, query, max_results, language):
        """调用搜索 API（示例实现）。"""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.search.example.com/search",
                params={"q": query, "limit": max_results, "lang": language},
            )
            response.raise_for_status()
            return response.json()["results"]
```

### 第三步：注册工具

```python
# 在工具注册表中添加
# src/venux_code/llm/tools/registry.py

from .web_search_tool import WebSearchTool

_DEFAULT_TOOLS = [
    BashTool,
    EditTool,
    GlobTool,
    GrepTool,
    LsTool,
    ViewTool,
    WriteTool,
    WebSearchTool,  # ← 新增
]
```

### 第四步：运行时动态注册

```python
from venux_code.llm.tools.registry import ToolRegistry
from venux_code.llm.tools.web_search_tool import WebSearchTool

# 创建注册表（包含默认工具）
registry = ToolRegistry()

# 动态注册新工具
registry.register(WebSearchTool())

# 验证注册
assert "web_search" in registry
print(registry.list_names())  # [..., 'web_search']
```

---

## 注册自定义工具

### 方式一：修改源码

直接修改 `registry.py` 的 `_DEFAULT_TOOLS` 列表。

### 方式二：运行时注册

```python
from venux_code.llm.tools.registry import ToolRegistry

registry = ToolRegistry()

# 注册单个工具
registry.register(MyCustomTool())

# 批量注册
for tool_cls in [ToolA, ToolB, ToolC]:
    registry.register(tool_cls())

# 获取 LangChain 工具列表（用于 Agent）
langchain_tools = registry.as_langchain_tools()
```

### 方式三：插件方式（推荐）

创建独立的 Python 包，在入口点注册：

```python
# my_plugin/__init__.py
from venux_code.llm.tools.registry import ToolRegistry

def register_tools(registry: ToolRegistry):
    registry.register(MyTool1())
    registry.register(MyTool2())
```

---

## 内置工具参考

### BashTool

```python
class BashParams(BaseModel):
    command: str              # Shell 命令
    timeout: int = 30         # 超时秒数（1-300）
    working_directory: str?   # 工作目录

# 示例调用
{"command": "python -m pytest tests/", "timeout": 60}
```

### EditTool

```python
# 查找替换
{"path": "src/main.py", "old_string": "def foo", "new_string": "def bar"}

# 指定模式
{"path": "src/main.py", "old_string": "...", "new_string": "...", "mode": "replace"}
```

### ViewTool

```python
{"path": "src/main.py"}                    # 查看整个文件
{"path": "src/main.py", "offset": 10, "limit": 50}  # 查看第 10-60 行
```

### WriteTool

```python
{"path": "src/new_file.py", "content": "print('hello')"}
```

### GrepTool

```python
{"pattern": "def.*async", "path": "src/"}  # 搜索异步函数
{"pattern": "TODO|FIXME", "file_glob": "*.py"}  # 在 Python 文件中搜索
```

### GlobTool

```python
{"pattern": "*.py"}                        # 所有 Python 文件
{"pattern": "src/**/*.py"}                 # src 下的 Python 文件
```

### LsTool

```python
{"path": "."}                              # 列出当前目录
{"path": "src/", "show_hidden": true}      # 包含隐藏文件
```
