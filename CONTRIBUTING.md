# 贡献指南

> 感谢你对 Venux Code 的关注！我们欢迎所有形式的贡献。

---

## 目录

- [如何贡献](#如何贡献)
- [开发环境搭建](#开发环境搭建)
- [代码规范](#代码规范)
- [提交规范](#提交规范)
- [添加新工具](#添加新工具)
- [添加新 LLM 提供商](#添加新-llm-提供商)
- [提交 Issue](#提交-issue)
- [提交 Pull Request](#提交-pull-request)

---

## 如何贡献

你可以通过以下方式为 Venux Code 做出贡献：

- 🐛 **报告 Bug** — 提交 Issue 描述问题
- 💡 **功能建议** — 在 Discussion 中提出新想法
- 📝 **文档改进** — 修正错误、补充说明
- 🔧 **代码贡献** — 修复 Bug、添加功能
- 🧪 **测试** — 补充测试用例
- 🌐 **翻译** — 帮助翻译文档

---

## 开发环境搭建

### 前置要求

- Python >= 3.11
- Git
- 推荐使用 `uv` 进行包管理

### 搭建步骤

```bash
# 1. Fork 并克隆仓库
git clone https://github.com/YOUR_USERNAME/venux-code.git
cd venux-code

# 2. 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate     # Windows

# 3. 安装开发依赖
pip install -e ".[dev]"

# 4. 安装 pre-commit hooks（可选）
pre-commit install

# 5. 运行测试确认环境正常
pytest

# 6. 运行健康检查
venux-code doctor
```

### 使用 uv（推荐）

```bash
# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 创建环境并安装
uv venv
uv pip install -e ".[dev]"
```

---

## 代码规范

### Python 代码风格

Venux Code 使用以下工具保证代码质量：

- **Ruff** — 代码格式化和 lint
- **mypy** — 静态类型检查（strict 模式）
- **pytest** — 测试框架

### 配置规则

```toml
# pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.mypy]
python_version = "3.11"
strict = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### 运行检查

```bash
# 代码格式化
ruff format src/ tests/

# Lint 检查
ruff check src/ tests/

# 类型检查
mypy src/venux_code/

# 运行测试
pytest

# 运行测试并生成覆盖率报告
pytest --cov=venux_code --cov-report=html
```

### 代码风格要点

```python
# ✅ 使用类型注解
async def process_message(message: str, *, timeout: int = 30) -> ToolResponse:
    ...

# ✅ 使用 dataclass 或 Pydantic 模型
@dataclass
class Config:
    name: str
    value: int

# ✅ 使用 f-string
greeting = f"Hello, {name}!"

# ✅ 使用现代 Python 语法
items: list[str] = []           # 而非 List[str]
result: dict[str, Any] = {}    # 而非 Dict[str, Any]
maybe: str | None = None       # 而非 Optional[str]

# ✅ 文档字符串使用 Google 风格
def fetch_data(url: str, *, retries: int = 3) -> dict:
    """从 URL 获取数据。

    Parameters
    ----------
    url:
        请求的 URL 地址。
    retries:
        最大重试次数，默认 3。

    Returns
    -------
    dict
        解析后的 JSON 数据。

    Raises
    ------
    httpx.HTTPError
        当请求失败时。
    """
```

---

## 提交规范

### Commit Message 格式

使用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/) 规范：

```
<类型>(<范围>): <描述>

[可选正文]

[可选脚注]
```

### 类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(tools): add web search tool` |
| `fix` | Bug 修复 | `fix(agent): handle empty tool response` |
| `docs` | 文档更新 | `docs(providers): add DeepSeek guide` |
| `style` | 代码格式 | `style: fix indentation in agent.py` |
| `refactor` | 重构 | `refactor(registry): use lazy loading` |
| `perf` | 性能优化 | `perf(context): optimize message pruning` |
| `test` | 测试 | `test(tools): add BashTool unit tests` |
| `chore` | 构建/工具 | `chore: update pyproject.toml deps` |
| `ci` | CI/CD | `ci: add GitHub Actions workflow` |

### 示例

```bash
# 简单提交
git commit -m "fix: handle None api_key gracefully"

# 带范围
git commit -m "feat(providers): add OpenRouter provider support"

# 带正文
git commit -m "refactor(agent): simplify context budget enforcement

The previous implementation used a complex while loop. This commit
replaces it with a cleaner recursive approach that's easier to test.

Closes #42"
```

---

## 添加新工具

1. 在 `src/venux_code/llm/tools/` 下创建新文件：

```python
# src/venux_code/llm/tools/my_tool.py
from pydantic import BaseModel, Field
from .base import BaseTool, ToolResponse

class MyToolParams(BaseModel):
    param1: str = Field(description="参数说明")

class MyTool(BaseTool):
    name = "my_tool"
    description = "工具描述"
    parameters_schema = MyToolParams
    requires_permission = False

    async def execute(self, params: dict) -> ToolResponse:
        validated = MyToolParams(**params)
        return ToolResponse(success=True, output="结果")
```

2. 在 `registry.py` 中注册：

```python
from .my_tool import MyTool

_DEFAULT_TOOLS = [
    # ... 原有工具
    MyTool,
]
```

3. 编写测试：

```python
# tests/tools/test_my_tool.py
import pytest
from venux_code.llm.tools.my_tool import MyTool

@pytest.mark.asyncio
async def test_my_tool():
    tool = MyTool()
    result = await tool.execute({"param1": "test"})
    assert result.success
```

4. 更新文档 `docs/TOOLS.md`

---

## 添加新 LLM 提供商

1. 在 `src/venux_code/llm/providers/` 下创建新文件：

```python
# src/venux_code/llm/providers/my_provider.py
from typing import Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from .base import BaseLLMProvider, ModelInfo

class MyProvider(BaseLLMProvider):
    def _build_model(self, *, stream=False, tools=None) -> BaseChatModel:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            api_key=self.api_key,
            model=self.model_name,
            base_url=self.base_url,
            streaming=stream,
        )

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            name=self.model_name,
            provider="my_provider",
            context_window=128_000,
            max_tokens=self.max_tokens,
        )
```

2. 在 `registry.py` 中注册：

```python
_PROVIDER_CLASSES = {
    # ... 原有提供商
    "my_provider": "venux_code.llm.providers.my_provider:MyProvider",
}
```

3. 编写测试并更新文档 `docs/PROVIDERS.md`

---

## 提交 Issue

### Bug 报告

请包含以下信息：

- **环境信息**：Python 版本、操作系统、Venux Code 版本
- **复现步骤**：详细的操作步骤
- **期望行为**：你期望发生什么
- **实际行为**：实际发生了什么
- **错误日志**：完整的错误堆栈

```markdown
**环境**
- Python: 3.11.5
- OS: macOS 14.0
- Venux Code: 0.1.0

**复现步骤**
1. 运行 `venux-code chat -q "hello"`
2. 看到错误...

**错误日志**
```
Traceback (most recent call last):
  ...
```
```

### 功能建议

```markdown
**问题描述**
简要描述你遇到的问题或需求

**建议方案**
描述你期望的解决方案

**替代方案**
考虑过的其他方案（如果有）
```

---

## 提交 Pull Request

### 流程

1. Fork 仓库
2. 创建功能分支：`git checkout -b feat/my-feature`
3. 提交更改（遵循提交规范）
4. 运行检查：`ruff check && mypy src/ && pytest`
5. 推送分支：`git push origin feat/my-feature`
6. 创建 Pull Request

### PR 标题

使用与 Commit Message 相同的格式：

```
feat(tools): add web search tool
fix(agent): handle timeout gracefully
docs: update contributing guide
```

### PR 描述模板

```markdown
## 变更说明
简要描述此 PR 的变更内容

## 变更类型
- [ ] 新功能
- [ ] Bug 修复
- [ ] 文档更新
- [ ] 重构
- [ ] 其他

## 测试
- [ ] 添加了新的测试用例
- [ ] 所有现有测试通过
- [ ] 手动测试通过

## 相关 Issue
Closes #123
```

---

## 行为准则

- 尊重所有参与者
- 接受建设性批评
- 专注于对社区最有利的事情
- 对他人表示同理心

---

## 许可证

贡献即表示你同意你的贡献将在 [MIT 许可证](LICENSE) 下授权。
