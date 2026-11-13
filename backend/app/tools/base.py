"""Tool framework for the AI agent.

A tool is a typed, permissioned, audited backend function. The LLM never touches the
database: it can only request one of the registered tools with validated arguments.
"""
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.enums import ToolStatus, UserRole
from app.rules.engine import RuleConfig


@dataclass
class ToolContext:
    db: Session
    now: datetime
    cfg: RuleConfig
    actor: str
    role: UserRole
    confirmed: bool = False  # set ONLY by the confirmation endpoint, never by the LLM


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[ToolContext, Any], dict]
    mutates: bool = False

    def input_schema(self) -> dict:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        for p in schema.get("properties", {}).values():
            p.pop("title", None)
        return schema

    def to_anthropic(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema()}


@dataclass
class ToolRun:
    tool: str
    arguments: dict
    status: ToolStatus
    result: dict | None
    error: str | None
    duration_ms: int

    def as_dict(self) -> dict:
        return {"tool": self.tool, "arguments": self.arguments, "status": self.status.value,
                "result": self.result, "error": self.error, "duration_ms": self.duration_ms}


REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    REGISTRY[tool.name] = tool
    return tool


def execute_tool(name: str, raw_args: dict | None, ctx: ToolContext) -> ToolRun:
    """Validate arguments, check permissions and run a tool. Never raises for tool-level errors."""
    started = time.perf_counter()

    def done(status: ToolStatus, result=None, error=None, args=None) -> ToolRun:
        return ToolRun(name, args if args is not None else (raw_args or {}), status, result, error,
                       int((time.perf_counter() - started) * 1000))

    tool = REGISTRY.get(name)
    if tool is None:
        return done(ToolStatus.ERROR, error=f"Unknown tool '{name}'")
    try:
        args = tool.args_model.model_validate(raw_args or {})
    except ValidationError as e:
        msgs = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
        return done(ToolStatus.ERROR, error=f"Invalid arguments: {msgs}")
    clean_args = args.model_dump(mode="json", exclude_none=True)
    if tool.mutates and ctx.role == UserRole.VIEWER:
        return done(ToolStatus.ERROR, error="Permission denied: your role cannot change data", args=clean_args)
    if tool.mutates and not ctx.confirmed:
        return done(ToolStatus.PENDING_CONFIRMATION, args=clean_args, result={
            "requires_confirmation": True,
            "message": "Esta ação altera dados e precisa de confirmação explícita do usuário.",
            "proposal": clean_args,
        })
    try:
        result = tool.handler(ctx, args)
        ctx.db.flush()
        return done(ToolStatus.SUCCESS, result=result, args=clean_args)
    except AppError as e:  # handlers validate before writing, so nothing partial to undo
        return done(ToolStatus.ERROR, error=e.message, args=clean_args)
