"""Agent-side safeguards: prompt-injection screening, data/instruction separation, rate limiting."""
import json
import re
import time
import unicodedata
from collections import defaultdict, deque

from app.core.errors import RateLimitError

MAX_STRING = 400

# Requests that try to leave the tool sandbox. Deliberately conservative: block, don't guess.
BLOCK_PATTERNS = [
    r"ignor(e|ar|a)\b.{0,30}(instruc|regra|prompt|anterior)",
    r"ignore (all |any )?(previous|prior|above)",
    r"(revele|mostre|exiba|imprima|reveal|show|print).{0,30}(system prompt|prompt do sistema|instrucoes do sistema|seu prompt)",
    r"(variavel|variaveis|variable)s? de ambiente|environment variable|\.env\b|api[_ -]?key|chave de api|secret[_ ]key|senha|password|token",
    r"\b(drop|delete|truncate|alter|insert|update)\s+(table|from|into)\b|\bselect\b.+\bfrom\b",
    r"execute (codigo|code|comando|command)|rode (um )?(script|comando)|os\.system|subprocess|eval\(",
    r"voce agora e|you are now|aja como|act as .{0,20}(dan|jailbreak)",
]
_BLOCK = [re.compile(p, re.I) for p in BLOCK_PATTERNS]


def _plain(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def detect_blocked_request(text: str) -> str | None:
    plain = _plain(text)
    for rx in _BLOCK:
        if rx.search(plain):
            return rx.pattern
    return None


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_value(value, depth: int = 0):
    """Truncate strings, drop control chars and neutralise our own delimiter inside tool output."""
    if isinstance(value, str):
        v = _CONTROL.sub("", value)[:MAX_STRING]
        return v.replace("<tool_data", "&lt;tool_data").replace("</tool_data", "&lt;/tool_data")
    if isinstance(value, dict):
        return {str(k)[:80]: sanitize_value(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_value(v, depth + 1) for v in value[:60]]
    return value


def wrap_tool_result(tool: str, payload: dict) -> str:
    """Tool results are delivered as quoted DATA, separated from instructions."""
    body = json.dumps(sanitize_value(payload), ensure_ascii=False, default=str)
    return f'<tool_data tool="{tool}">{body}</tool_data>'


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window: float = 60.0) -> None:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            raise RateLimitError(f"Limite de {limit} mensagens por minuto atingido. Aguarde um instante.")
        q.append(now)

    def reset(self) -> None:
        self._hits.clear()


rate_limiter = RateLimiter()
