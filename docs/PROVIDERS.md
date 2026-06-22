# LLM 提供商设置指南

> 如何配置和使用各个 LLM 提供商

---

## 目录

- [提供商注册机制](#提供商注册机制)
- [OpenAI](#openai)
- [Anthropic](#anthropic)
- [Google Gemini](#google-gemini)
- [DeepSeek](#deepseek)
- [MiMo](#mimo)
- [Kimi / Moonshot](#kimi--moonshot)
- [OpenRouter](#openrouter)
- [创建自定义提供商](#创建自定义提供商)

---

## 提供商注册机制

Venux Code 使用懒加载注册表管理提供商，位于 `src/venux_code/llm/providers/registry.py`：

```python
_PROVIDER_CLASSES = {
    "openai": "venux_code.llm.providers.openai_provider:OpenAIProvider",
    "anthropic": "venux_code.llm.providers.anthropic_provider:AnthropicProvider",
    "google": "venux_code.llm.providers.google_provider:GoogleProvider",
    "gemini": "venux_code.llm.providers.google_provider:GoogleProvider",  # 别名
    "deepseek": "venux_code.llm.providers.deepseek_provider:DeepSeekProvider",
    "mimo": "venux_code.llm.providers.mimo_provider:MiMoProvider",
    "kimi": "venux_code.llm.providers.kimi_provider:KimiProvider",
    "moonshot": "venux_code.llm.providers.kimi_provider:KimiProvider",  # 别名
    "openrouter": "venux_code.llm.providers.openrouter_provider:OpenRouterProvider",
}

class ProviderRegistry:
    def register(self, name, dotted_path):
        """运行时注册新提供商"""
        self._classes[name.lower()] = dotted_path

    def create(self, name=None, *, settings=None, **overrides):
        """实例化提供商"""
        provider_name = (name or settings.llm.provider).lower()
        cls = _import_class(self._classes[provider_name])
        return cls(
            api_key=settings.llm.api_key,
            model_name=settings.llm.model,
            max_tokens=settings.llm.max_tokens,
            temperature=settings.llm.temperature,
            base_url=settings.llm.base_url,
            **overrides
        )

    def available(self) -> list[str]:
        """返回所有可用提供商名称"""
        return sorted(self._classes)
```

### 快速创建提供商

```python
from venux_code.llm.providers.registry import create_provider

# 使用默认配置
provider = create_provider()

# 指定提供商
provider = create_provider("anthropic")

# 覆盖参数
provider = create_provider("openai", model_name="gpt-4o-mini")
```

---

## OpenAI

### API Key 获取

1. 访问 [platform.openai.com](https://platform.openai.com)
2. 注册/登录 → API Keys → Create new secret key
3. 复制 `sk-...` 格式的 Key

### 配置方式

```bash
# 环境变量
export OPENAI_API_KEY=*** export VENUX_LLM__PROVIDER=openai
export VENUX_LLM__MODEL=gpt-4o
```

```yaml
# ~/.venux-code/config.yaml
llm:
  provider: openai
  model: gpt-4o
  api_key: sk-xxx
```

### 可用模型

| 模型 | 说明 | 上下文窗口 |
|------|------|-----------|
| `gpt-4o` | 最新旗舰模型 | 128K |
| `gpt-4o-mini` | 轻量快速 | 128K |
| `o1` | 推理增强 | 128K |
| `o1-mini` | 轻量推理 | 128K |

### 自定义 API 地址

```yaml
llm:
  provider: openai
  base_url: https://your-proxy.example.com/v1
  api_key: your-key
```

---

## Anthropic

### API Key 获取

1. 访问 [console.anthropic.com](https://console.anthropic.com)
2. 注册/登录 → API Keys → Create Key
3. 复制 `sk-ant-...` 格式的 Key

### 配置方式

```bash
export ANTHROPIC_API_KEY=*** export VENUX_LLM__PROVIDER=anthropic
export VENUX_LLM__MODEL=claude-sonnet-4-20250514
```

```yaml
llm:
  provider: anthropic
  model: claude-sonnet-4-20250514
  api_key: sk-ant-xxx
```

### 可用模型

| 模型 | 说明 | 上下文窗口 |
|------|------|-----------|
| `claude-sonnet-4-20250514` | 最新旗舰 | 200K |
| `claude-3.5-haiku` | 快速轻量 | 200K |

---

## Google Gemini

### API Key 获取

1. 访问 [aistudio.google.com](https://aistudio.google.com)
2. 登录 → Get API Key → Create API Key
3. 复制 `AIza...` 格式的 Key

### 配置方式

```bash
export GOOGLE_API_KEY=AIza*** export VENUX_LLM__PROVIDER=google
export VENUX_LLM__MODEL=gemini-2.0-flash
```

```yaml
llm:
  provider: google
  model: gemini-2.0-flash
  api_key: AIza-xxx
```

### 可用模型

| 模型 | 说明 | 上下文窗口 |
|------|------|-----------|
| `gemini-2.0-flash` | 最新快速 | 1M |
| `gemini-1.5-pro` | 专业版 | 2M |
| `gemini-1.5-flash` | 轻量快速 | 1M |

---

## DeepSeek

### API Key 获取

1. 访问 [platform.deepseek.com](https://platform.deepseek.com)
2. 注册/登录 → API Keys → 创建
3. 复制 Key

### 配置方式

```bash
export DEEPSEEK_API_KEY=sk-*** export VENUX_LLM__PROVIDER=deepseek
export VENUX_LLM__MODEL=deepseek-chat
```

```yaml
llm:
  provider: deepseek
  model: deepseek-chat
  api_key: sk-xxx
  base_url: https://api.deepseek.com
```

### 可用模型

| 模型 | 说明 | 上下文窗口 |
|------|------|-----------|
| `deepseek-chat` | 通用对话 | 128K |
| `deepseek-coder` | 代码专用 | 128K |

---

## MiMo

### 配置方式

```bash
export MIMO_API_KEY=*** export VENUX_LLM__PROVIDER=mimo
export VENUX_LLM__MODEL=MiMo-7B
```

```yaml
llm:
  provider: mimo
  model: MiMo-7B
  api_key: xxx
  base_url: https://api.mimo.example.com
```

---

## Kimi / Moonshot

### API Key 获取

1. 访问 [platform.moonshot.cn](https://platform.moonshot.cn)
2. 注册/登录 → API Key 管理 → 创建
3. 复制 `sk-...` 格式的 Key

### 配置方式

```bash
export KIMI_API_KEY=sk-*** export VENUX_LLM__PROVIDER=kimi
export VENUX_LLM__MODEL=moonshot-v1-128k
```

```yaml
llm:
  provider: kimi
  model: moonshot-v1-128k
  api_key: sk-xxx
  base_url: https://api.moonshot.cn/v1
```

### 可用模型

| 模型 | 说明 | 上下文窗口 |
|------|------|-----------|
| `moonshot-v1-8k` | 短上下文 | 8K |
| `moonshot-v1-32k` | 中等上下文 | 32K |
| `moonshot-v1-128k` | 长上下文 | 128K |

---

## OpenRouter

### API Key 获取

1. 访问 [openrouter.ai](https://openrouter.ai)
2. 注册/登录 → Keys → Create Key
3. 复制 `sk-or-...` 格式的 Key

### 配置方式

```bash
export OPENROUTER_API_KEY=sk-or-*** export VENUX_LLM__PROVIDER=openrouter
export VENUX_LLM__MODEL=anthropic/claude-3.5-sonnet
```

```yaml
llm:
  provider: openrouter
  model: anthropic/claude-3.5-sonnet
  api_key: sk-or-xxx
  base_url: https://openrouter.ai/api/v1
```

### 使用第三方模型

OpenRouter 使用 `provider/model` 格式：

```yaml
llm:
  provider: openrouter
  model: meta-llama/llama-3.1-405b-instruct
```

---

## 创建自定义提供商

### 第一步：实现提供商类

```python
# src/venux_code/llm/providers/custom_provider.py

from typing import Any, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from .base import BaseLLMProvider, ModelInfo, ChatResponse


class CustomProvider(BaseLLMProvider):
    """自定义 LLM 提供商示例。"""

    def _build_model(
        self, *, stream: bool = False, tools: Optional[list[BaseTool]] = None
    ) -> BaseChatModel:
        """返回配置好的 LangChain 模型实例。"""
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            api_key=self.api_key,
            model=self.model_name,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            base_url=self.base_url,
            streaming=stream,
        )

    def model_info(self) -> ModelInfo:
        """返回模型元数据。"""
        return ModelInfo(
            name=self.model_name,
            provider="custom",
            context_window=128_000,
            max_tokens=self.max_tokens,
            cost_per_1m_in=0.0,
            cost_per_1m_out=0.0,
        )
```

### 第二步：注册提供商

```python
from venux_code.llm.providers.registry import ProviderRegistry

registry = ProviderRegistry()

# 运行时注册
registry.register(
    "custom",
    "venux_code.llm.providers.custom_provider:CustomProvider"
)

# 使用
provider = registry.create("custom", api_key="xxx", model_name="my-model")
```

### 第三步：添加到默认注册表

修改 `src/venux_code/llm/providers/registry.py`：

```python
_PROVIDER_CLASSES = {
    # ... 原有提供商
    "custom": "venux_code.llm.providers.custom_provider:CustomProvider",
}
```

### BaseLLMProvider 接口

```python
class BaseLLMProvider(ABC):
    def __init__(self, *, api_key, model_name, max_tokens=4096,
                 temperature=0.7, base_url=None):

    @abstractmethod
    def _build_model(self, *, stream=False, tools=None) -> BaseChatModel:
        """必须实现：返回 LangChain BaseChatModel"""

    @abstractmethod
    def model_info(self) -> ModelInfo:
        """必须实现：返回模型元数据"""

    async def chat(self, messages, *, tools=None, stream=False) -> ChatResponse:
        """可选覆盖：自定义非流式调用逻辑"""

    async def stream_chat(self, messages, *, tools=None) -> AsyncIterator[str]:
        """可选覆盖：自定义流式调用逻辑"""
```

### ModelInfo 数据结构

```python
@dataclass(frozen=True, slots=True)
class ModelInfo:
    name: str                    # 模型名称
    provider: str                # 提供商名称
    context_window: int = 128_000  # 上下文窗口大小
    max_tokens: int = 4_096      # 最大输出 token
    cost_per_1m_in: float = 0.0  # 每百万输入 token 成本（USD）
    cost_per_1m_out: float = 0.0 # 每百万输出 token 成本（USD）
```
