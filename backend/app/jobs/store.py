"""Persistência da fila em SQLite. Toda mudança de estado passa por aqui (e sobrevive a reinícios)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Sequence
from typing import Any

from ..db import Database
from ..logging_setup import mascarar
from .models import ATIVOS, FINAIS, Job, JobLog, JobStatus, agora_iso

_COLUNAS_BOOL = ("heavy", "cancel_requested", "pause_requested")


def _para_job(row: sqlite3.Row) -> Job:
    dados: dict[str, Any] = dict(row)
    dados["params"] = json.loads(dados["params"] or "{}")
    dados["result"] = json.loads(dados["result"]) if dados["result"] else None
    for coluna in _COLUNAS_BOOL:
        dados[coluna] = bool(dados[coluna])
    return Job.model_validate(dados)


class JobStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    # --- criação e consulta -------------------------------------------------------------
    def criar(
        self, kind: str, title: str, params: dict[str, Any] | None = None, *, priority: int = 0, heavy: bool = True
    ) -> Job:
        job_id = uuid.uuid4().hex
        agora = agora_iso()
        with self._db.transaction(imediata=True) as c:
            posicao = c.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM jobs").fetchone()[0]
            c.execute(
                "INSERT INTO jobs (id, kind, title, params, status, priority, position, heavy, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?)",
                (
                    job_id,
                    kind,
                    title,
                    json.dumps(params or {}, ensure_ascii=False),
                    priority,
                    posicao,
                    int(heavy),
                    agora,
                    agora,
                ),
            )
        criado = self.obter(job_id)
        assert criado is not None
        return criado

    def obter(self, job_id: str) -> Job | None:
        with self._db.transaction() as c:
            row = c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _para_job(row) if row else None

    def listar(self, statuses: Sequence[JobStatus] | None = None, limite: int = 200) -> list[Job]:
        """Ativos primeiro (executando, depois a ordem da fila), depois os finalizados do mais novo ao mais antigo."""
        with self._db.transaction() as c:
            ativos = c.execute(
                "SELECT * FROM jobs WHERE status IN ('running', 'paused', 'queued')"
                " ORDER BY CASE status WHEN 'running' THEN 0 ELSE 1 END, priority DESC, position ASC, created_at ASC"
            ).fetchall()
            finais = c.execute(
                "SELECT * FROM jobs WHERE status IN ('done', 'failed', 'canceled')"
                " ORDER BY finished_at DESC, created_at DESC LIMIT ?",
                (limite,),
            ).fetchall()
        jobs = [_para_job(r) for r in [*ativos, *finais]]
        if statuses:
            jobs = [j for j in jobs if j.status in statuses]
        return jobs[: max(limite, len(ativos))]

    def contagens(self) -> dict[str, int]:
        with self._db.transaction() as c:
            rows = c.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status").fetchall()
        return {r["status"]: int(r["n"]) for r in rows}

    # --- transições do worker -----------------------------------------------------------
    def reservar_proximo(self) -> Job | None:
        """Pega o próximo job da fila (prioridade, depois posição) e o marca como executando."""
        agora = agora_iso()
        with self._db.transaction(imediata=True) as c:
            row = c.execute(
                "SELECT id FROM jobs WHERE status = 'queued' ORDER BY priority DESC, position ASC, created_at ASC LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            c.execute(
                "UPDATE jobs SET status = 'running', started_at = ?, updated_at = ?, attempts = attempts + 1,"
                " progress = 0, eta_seconds = NULL, error = NULL, finished_at = NULL WHERE id = ?",
                (agora, agora, row["id"]),
            )
        return self.obter(row["id"])

    def atualizar_progresso(self, job_id: str, progresso: float, mensagem: str | None, eta: float | None) -> Job | None:
        agora = agora_iso()
        with self._db.transaction(imediata=True) as c:
            c.execute(
                "UPDATE jobs SET progress = ?, message = COALESCE(?, message), eta_seconds = ?, updated_at = ?"
                " WHERE id = ? AND status IN ('running', 'paused')",
                (max(0.0, min(1.0, progresso)), mensagem, eta, agora, job_id),
            )
        return self.obter(job_id)

    def marcar_pausado(self, job_id: str) -> Job | None:
        with self._db.transaction(imediata=True) as c:
            c.execute(
                "UPDATE jobs SET status = 'paused', updated_at = ? WHERE id = ? AND status = 'running'",
                (agora_iso(), job_id),
            )
        return self.obter(job_id)

    def marcar_executando(self, job_id: str) -> Job | None:
        with self._db.transaction(imediata=True) as c:
            c.execute(
                "UPDATE jobs SET status = 'running', updated_at = ? WHERE id = ? AND status = 'paused'",
                (agora_iso(), job_id),
            )
        return self.obter(job_id)

    def finalizar(
        self,
        job_id: str,
        status: JobStatus,
        *,
        resultado: dict[str, Any] | None = None,
        erro: str | None = None,
        mensagem: str | None = None,
    ) -> Job | None:
        assert status in FINAIS
        agora = agora_iso()
        with self._db.transaction(imediata=True) as c:
            c.execute(
                "UPDATE jobs SET status = ?, result = ?, error = ?, message = COALESCE(?, message), finished_at = ?,"
                " updated_at = ?, eta_seconds = NULL, progress = CASE WHEN ? = 'done' THEN 1 ELSE progress END,"
                " pause_requested = 0 WHERE id = ?",
                (
                    status.value,
                    json.dumps(resultado, ensure_ascii=False) if resultado is not None else None,
                    mascarar(erro) if erro else None,
                    mensagem,
                    agora,
                    agora,
                    status.value,
                    job_id,
                ),
            )
        return self.obter(job_id)

    # --- ações do usuário -----------------------------------------------------------------
    def cancelar(self, job_id: str) -> Job | None:
        """Na fila: cancela na hora. Em execução (ou segurado pelo worker): pede e o worker encerra no próximo checkpoint."""
        job = self.obter(job_id)
        if job is None or job.status in FINAIS:
            return job
        agora = agora_iso()
        with self._db.transaction(imediata=True) as c:
            if job.status == JobStatus.RUNNING or job.retido_pelo_worker:
                c.execute("UPDATE jobs SET cancel_requested = 1, updated_at = ? WHERE id = ?", (agora, job_id))
            else:
                c.execute(
                    "UPDATE jobs SET status = 'canceled', finished_at = ?, updated_at = ?, message = 'Cancelado' WHERE id = ?",
                    (agora, agora, job_id),
                )
        return self.obter(job_id)

    def pausar(self, job_id: str) -> Job | None:
        job = self.obter(job_id)
        if job is None or job.status in FINAIS or job.status == JobStatus.PAUSED:
            return job
        agora = agora_iso()
        with self._db.transaction(imediata=True) as c:
            if job.status == JobStatus.RUNNING:
                c.execute("UPDATE jobs SET pause_requested = 1, updated_at = ? WHERE id = ?", (agora, job_id))
            else:  # ainda na fila: segura sem iniciar
                c.execute("UPDATE jobs SET status = 'paused', updated_at = ? WHERE id = ?", (agora, job_id))
        return self.obter(job_id)

    def retomar(self, job_id: str) -> Job | None:
        job = self.obter(job_id)
        if job is None:
            return None
        agora = agora_iso()
        with self._db.transaction(imediata=True) as c:
            # pedido de pausa ainda não atendido, ou job já segurado pelo worker: só limpa o pedido
            if (job.status == JobStatus.RUNNING and job.pause_requested) or job.retido_pelo_worker:
                c.execute("UPDATE jobs SET pause_requested = 0, updated_at = ? WHERE id = ?", (agora, job_id))
            elif job.status == JobStatus.PAUSED:
                c.execute("UPDATE jobs SET status = 'queued', updated_at = ? WHERE id = ?", (agora, job_id))
        return self.obter(job_id)

    def reordenar(self, ids: Sequence[str]) -> list[Job]:
        """Define a nova ordem dos jobs que ainda estão na fila (ou pausados nela)."""
        agora = agora_iso()
        with self._db.transaction(imediata=True) as c:
            posicao = 0
            for job_id in ids:
                row = c.execute("SELECT status, pause_requested FROM jobs WHERE id = ?", (job_id,)).fetchone()
                if row is None or row["status"] not in ("queued", "paused") or row["pause_requested"]:
                    continue
                posicao += 1
                c.execute(
                    "UPDATE jobs SET position = ?, priority = 0, updated_at = ? WHERE id = ?", (posicao, agora, job_id)
                )
        return self.listar(ATIVOS)

    def limpar_finalizados(self) -> int:
        with self._db.transaction(imediata=True) as c:
            cur = c.execute("DELETE FROM jobs WHERE status IN ('done', 'failed', 'canceled')")
            return int(cur.rowcount)

    def recuperar_interrompidos(self) -> int:
        """Depois de um reinício: o que estava executando volta para a fila; o que o usuário pausou continua pausado."""
        agora = agora_iso()
        with self._db.transaction(imediata=True) as c:
            n = c.execute(
                "UPDATE jobs SET status = 'queued', message = 'Retomado após reinício do app', progress = 0,"
                " eta_seconds = NULL, pause_requested = 0, updated_at = ? WHERE status = 'running'",
                (agora,),
            ).rowcount
            c.execute("UPDATE jobs SET pause_requested = 0, updated_at = ? WHERE status = 'paused'", (agora,))
        return int(n)

    # --- logs do job ----------------------------------------------------------------------
    def registrar_log(self, job_id: str, nivel: str, mensagem: str) -> None:
        with self._db.transaction() as c:
            c.execute(
                "INSERT INTO job_logs (job_id, ts, level, message) VALUES (?, ?, ?, ?)",
                (job_id, agora_iso(), nivel.upper(), mascarar(mensagem)),
            )

    def logs(self, job_id: str, limite: int = 500) -> list[JobLog]:
        with self._db.transaction() as c:
            rows = c.execute(
                "SELECT * FROM (SELECT * FROM job_logs WHERE job_id = ? ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
                (job_id, limite),
            ).fetchall()
        return [JobLog.model_validate(dict(r)) for r in rows]
