"""LLM provider abstraction.

`LLMProvider.complete()` receives the conversation in Anthropic-style blocks and returns
either text or tool calls. The Copilot loop is provider-agnostic.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.core.config import Settings


class ProviderError(Exception):
    """The provider failed (network, auth, rate limit, malformed output)."""


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class ProviderResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(ABC):
    name: str
    mode: str  # "demo" | "llm"
    model: str | None = None

    @abstractmethod
    def complete(self, system: str, messages: list[dict], tools: list[dict]) -> ProviderResponse: ...


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    mode = "llm"

    def __init__(self, api_key: str, model: str, timeout: float = 45.0):
        import anthropic

        self._anthropic = anthropic
        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=1)

    def complete(self, system: str, messages: list[dict], tools: list[dict]) -> ProviderResponse:
        try:
            resp = self._client.messages.create(
                model=self.model, max_tokens=1800, system=system, messages=messages, tools=tools,
            )
        except self._anthropic.APIError as e:  # connection, auth, rate limit, 5xx...
            raise ProviderError(f"{type(e).__name__}: {getattr(e, 'message', str(e))}"[:300]) from e
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Unexpected provider failure: {type(e).__name__}") from e
        text, calls = [], []
        for block in resp.content:
            if block.type == "text":
                text.append(block.text)
            elif block.type == "tool_use":
                calls.append(ToolCall(block.id, block.name, dict(block.input or {})))
        return ProviderResponse("\n".join(text).strip(), calls)


def build_provider(settings: Settings, hints: dict | None = None) -> tuple[LLMProvider, str | None]:
    """Return (provider, configuration_warning)."""
    from app.agents.demo import DemoProvider

    choice = settings.ai_provider.lower()
    has_key = bool(settings.anthropic_api_key)
    if choice in ("auto", "anthropic") and has_key:
        return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model,
                                 timeout=min(settings.agent_timeout_seconds, 60)), None
    warning = "AI_PROVIDER=anthropic, but ANTHROPIC_API_KEY is not set; running in demo mode" if choice == "anthropic" else None
    return DemoProvider(hints or {}), warning
