"""Worker único: um job por vez (lock global de jobs pesados, briefing 2.6), com pausa e cancelamento cooperativos."""

from __future__ import annotations

import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..erros import ErroParaOUsuario
from ..logging_setup import logger_do_servico, mascarar
from .events import EventBus
from .models import Job, JobStatus
from .store import JobStore

if TYPE_CHECKING:
    from ..container import Servicos

Handler = Callable[["JobContext", dict[str, Any]], dict[str, Any] | None]


class JobCanceled(Exception):
    """Lançada no ponto de controle quando o usuário cancela o job."""


class JobContext:
    """O que o handler de um job enxerga: progresso, logs, pausa/cancelamento e subprocessos."""

    def __init__(self, job: Job, store: JobStore, bus: EventBus, servicos: Servicos) -> None:
        self.job_id = job.id
        self.kind = job.kind
        self.servicos = servicos
        self._store = store
        self._bus = bus
        self._inicio = time.monotonic()
        self._ultimo_envio = 0.0
        self._ultima_mensagem: str | None = None
        self._log = logger_do_servico(f"job.{job.kind}")

    def _publicar(self, job: Job | None) -> None:
        if job is not None:
            self._bus.publicar("job.updated", job.model_dump(mode="json"))

    def progresso(self, fracao: float, mensagem: str | None = None) -> None:
        """Atualiza a barra (0 a 1) e a mensagem; calcula o ETA a partir do ritmo até agora."""
        agora = time.monotonic()
        if fracao < 1 and mensagem == self._ultima_mensagem and agora - self._ultimo_envio < 0.1:
            return  # evita inundar o banco e a tela com atualizações idênticas
        decorrido = agora - self._inicio
        eta = decorrido * (1 - fracao) / fracao if fracao >= 0.02 and decorrido >= 1 else None
        self._ultimo_envio = agora
        self._ultima_mensagem = mensagem
        self._publicar(self._store.atualizar_progresso(self.job_id, fracao, mensagem, eta))

    def log(self, mensagem: str, nivel: str = "INFO") -> None:
        self._store.registrar_log(self.job_id, nivel, mensagem)
        registro = {"service": f"job.{self.kind}", "job_id": self.job_id}
        self._log.log({"ERROR": 40, "WARNING": 30}.get(nivel.upper(), 20), mascarar(mensagem), extra=registro)

    def ponto_de_controle(self) -> None:
        """Chame entre etapas: cancela se pedido e fica parado enquanto o job estiver pausado."""
        while True:
            job = self._store.obter(self.job_id)
            if job is None or job.cancel_requested:
                raise JobCanceled
            if job.pause_requested:
                if job.status == JobStatus.RUNNING:
                    self._publicar(self._store.marcar_pausado(self.job_id))
                time.sleep(0.25)
                continue
            if job.status == JobStatus.PAUSED:
                self._publicar(self._store.marcar_executando(self.job_id))
            return

    def executar_processo(
        self,
        comando: Sequence[str],
        *,
        timeout: float,
        ao_tick: Callable[[float], None] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Roda um programa externo (lista de argumentos, nunca shell) sem travar o cancelamento."""
        with tempfile.TemporaryFile() as saida:
            proc = subprocess.Popen(list(comando), stdout=saida, stderr=subprocess.STDOUT, cwd=cwd)
            inicio = time.monotonic()
            try:
                while proc.poll() is None:
                    if time.monotonic() - inicio > timeout:
                        raise TimeoutError(f"o processo passou de {timeout:.0f} s e foi encerrado")
                    self.ponto_de_controle()
                    if ao_tick:
                        ao_tick(time.monotonic() - inicio)
                    time.sleep(0.25)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
            saida.seek(0)
            texto = saida.read().decode("utf-8", errors="replace")
        return subprocess.CompletedProcess(list(comando), proc.returncode, texto, "")


class JobWorker:
    def __init__(
        self,
        store: JobStore,
        bus: EventBus,
        servicos: Servicos,
        registro: Mapping[str, Handler],
        intervalo: float = 0.25,
    ) -> None:
        self._store = store
        self._bus = bus
        self._servicos = servicos
        self._registro = registro
        self._intervalo = intervalo
        self._parar = threading.Event()
        self._acordar = threading.Event()
        self._thread: threading.Thread | None = None
        self._atual: str | None = None
        self._log = logger_do_servico("fila")

    # --- ciclo de vida --------------------------------------------------------------------
    def iniciar(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._parar.clear()
        self._thread = threading.Thread(target=self._laco, name="fabulim-worker", daemon=True)
        self._thread.start()

    def parar(self, timeout: float = 5.0) -> None:
        self._parar.set()
        self._acordar.set()
        if self._thread:
            self._thread.join(timeout)

    def acordar(self) -> None:
        self._acordar.set()

    @property
    def vivo(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def job_atual(self) -> str | None:
        return self._atual

    # --- execução -------------------------------------------------------------------------
    def _laco(self) -> None:
        while not self._parar.is_set():
            try:
                job = self._store.reservar_proximo()
                if job is None:
                    self._acordar.wait(self._intervalo)
                    self._acordar.clear()
                    continue
                self._executar(job)
            except Exception:  # o worker nunca morre por um job (nem por um erro de banco passageiro)
                self._log.exception("erro inesperado no laço da fila")
                time.sleep(1.0)

    def _executar(self, job: Job) -> None:
        ctx = JobContext(job, self._store, self._bus, self._servicos)
        self._atual = job.id
        self._bus.publicar("job.updated", job.model_dump(mode="json"))
        final: Job | None
        try:
            handler = self._registro.get(job.kind)
            if handler is None:
                raise LookupError(f"tipo de job desconhecido: {job.kind}")
            ctx.log(f"Iniciado (tentativa {job.attempts})")
            resultado = handler(ctx, job.params)
            ctx.log("Concluído")  # o log vem antes do estado final: quem vê "done" já encontra o log completo
            final = self._store.finalizar(job.id, JobStatus.DONE, resultado=resultado or {}, mensagem="Concluído")
        except JobCanceled:
            ctx.log("Cancelado pelo usuário", "WARNING")
            final = self._store.finalizar(job.id, JobStatus.CANCELED, mensagem="Cancelado")
        except Exception as exc:
            self._log.exception("job %s falhou", job.id)
            ctx.log(f"Falhou: {exc}", "ERROR")
            erro = str(exc) if isinstance(exc, ErroParaOUsuario) else f"{type(exc).__name__}: {exc}"
            final = self._store.finalizar(job.id, JobStatus.FAILED, erro=erro, mensagem="Falhou")
        finally:
            self._atual = None
        if final is not None:
            self._bus.publicar("job.updated", final.model_dump(mode="json"))
