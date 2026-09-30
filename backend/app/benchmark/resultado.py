"""O resultado de uma medição do benchmark de calibração."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResultadoBench:
    task: str
    status: str  # ok | skipped | error
    model: str | None = None
    seconds: float | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    detail: str | None = None
