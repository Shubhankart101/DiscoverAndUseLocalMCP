from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


REQUIRED_RESOURCE = "equipment://catalog"
REQUIRED_TOOL = "check_availability"
REQUIRED_PROMPT = "maintenance_prompt"


class MissingCapabilityError(ValueError):
    pass


class PrimitiveType(str, Enum):
    RESOURCE = "resource"
    TOOL = "tool"
    PROMPT = "prompt"


@dataclass(frozen=True)
class CapabilitySet:
    resources: tuple[str, ...]
    tools: tuple[str, ...]
    prompts: tuple[str, ...]


@dataclass(frozen=True)
class MCPRequest:
    primitive: PrimitiveType | str
    identifier: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class MCPResult:
    ok: bool
    primitive: PrimitiveType | str
    identifier: str
    content: tuple[str, ...]
    error: str | None
