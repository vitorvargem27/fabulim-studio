"""Modelos da fila de jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"


ATIVOS = (JobStatus.RUNNING, JobStatus.PAUSED, JobStatus.QUEUED)
FINAIS = (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELED)


def agora_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class Job(BaseModel):
    id: str
    kind: str
    title: str
    params: dict[str, Any] = Field(default_factory=dict)
    status: JobStatus
    priority: int = 0
    position: float = 0
    progress: float = 0.0
    message: str = ""
    eta_seconds: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    heavy: bool = True
    attempts: int = 0
    cancel_requested: bool = False
    pause_requested: bool = False
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str

    @property
    def retido_pelo_worker(self) -> bool:
        """Pausado enquanto o worker o segura (diferente de pausado ainda na fila)."""
        return self.status == JobStatus.PAUSED and self.pause_requested


class JobCreate(BaseModel):
    kind: str = Field(min_length=1, max_length=80)
    title: str | None = Field(default=None, max_length=200)
    params: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=0, ge=-10, le=10)


class JobLog(BaseModel):
    id: int
    job_id: str
    ts: str
    level: str
    message: str


class ReordenarPedido(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)
