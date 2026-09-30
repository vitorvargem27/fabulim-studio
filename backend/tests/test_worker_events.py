"""Worker da fila (um job por vez, pausa, cancelamento, retomada) e barramento de eventos."""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from typing import Any

import pytest

from app.api.sse import gerar_eventos
from app.container import Servicos
from app.jobs.events import EventBus
from app.jobs.models import Job, JobStatus
from app.jobs.worker import Handler, JobCanceled, JobContext, JobWorker

from .conftest import esperar


class RelogioFalso:
    """Faz as vezes do módulo `time` do worker: o relógio só anda quando o teste manda; o resto vem do módulo de verdade."""

    def __init__(self) -> None:
        self.agora = 1000.0

    def monotonic(self) -> float:
        return self.agora

    def __getattr__(self, nome: str) -> Any:
        return getattr(time, nome)


def _ok(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    ctx.progresso(0.5, "no meio")
    return {"ok": True, "eco": params.get("x")}


def _falha(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    raise RuntimeError("a chave sk-ant-abcdefghijk123 vazou")


def _lento(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    passos = int(params.get("passos", 100))
    for i in range(passos):
        ctx.ponto_de_controle()
        time.sleep(0.02)
        ctx.progresso((i + 1) / passos, f"passo {i + 1}")
    return {"passos": passos}


@pytest.fixture
def worker(servicos: Servicos) -> Any:
    """Fábrica de workers de teste (polling rápido) que são parados no fim."""
    criados: list[JobWorker] = []

    def criar(registro: dict[str, Handler]) -> JobWorker:
        w = JobWorker(servicos.store, servicos.bus, servicos, registro, intervalo=0.02)
        criados.append(w)
        return w

    yield criar
    for w in criados:
        w.parar(timeout=5)


def _status(sv: Servicos, job: Job) -> JobStatus:
    atual = sv.store.obter(job.id)
    assert atual is not None
    return atual.status


class TestWorker:
    def test_executa_ate_o_fim(self, servicos: Servicos, worker: Any) -> None:
        job = servicos.store.criar("ok", "A", {"x": 7})
        worker({"ok": _ok}).iniciar()
        assert esperar(lambda: _status(servicos, job) == JobStatus.DONE)
        final = servicos.store.obter(job.id)
        assert final is not None and final.result == {"ok": True, "eco": 7}
        assert final.progress == 1.0 and final.message == "Concluído" and final.finished_at
        assert any("Concluído" in entrada.message for entrada in servicos.store.logs(job.id))

    def test_falha_fica_registrada_e_sem_segredo(self, servicos: Servicos, worker: Any) -> None:
        job = servicos.store.criar("falha", "A")
        worker({"falha": _falha}).iniciar()
        assert esperar(lambda: _status(servicos, job) == JobStatus.FAILED)
        final = servicos.store.obter(job.id)
        assert final is not None and "RuntimeError" in (final.error or "")
        assert "sk-ant" not in (final.error or "")
        assert all("sk-ant-abcdefghijk123" not in entrada.message for entrada in servicos.store.logs(job.id))

    def test_tipo_desconhecido_falha_sem_derrubar_o_worker(self, servicos: Servicos, worker: Any) -> None:
        ruim = servicos.store.criar("nao.existe", "A")
        bom = servicos.store.criar("ok", "B")
        w = worker({"ok": _ok})
        w.iniciar()
        assert esperar(lambda: _status(servicos, ruim) == JobStatus.FAILED)
        assert esperar(lambda: _status(servicos, bom) == JobStatus.DONE)
        assert w.vivo

    def test_um_job_por_vez(self, servicos: Servicos, worker: Any) -> None:
        simultaneos = {"agora": 0, "maximo": 0}
        trava = threading.Lock()

        def medir(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
            with trava:
                simultaneos["agora"] += 1
                simultaneos["maximo"] = max(simultaneos["maximo"], simultaneos["agora"])
            time.sleep(0.1)
            with trava:
                simultaneos["agora"] -= 1
            return {}

        jobs = [servicos.store.criar("medir", f"J{i}") for i in range(4)]
        worker({"medir": medir}).iniciar()
        assert esperar(lambda: all(_status(servicos, j) == JobStatus.DONE for j in jobs))
        assert simultaneos["maximo"] == 1

    def test_respeita_prioridade_e_ordem(self, servicos: Servicos, worker: Any) -> None:
        ordem: list[str] = []

        def registrar(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
            ordem.append(str(params["nome"]))
            return {}

        for nome, prioridade in (("a", 0), ("b", 0), ("urgente", 5), ("c", 0)):
            servicos.store.criar("r", nome, {"nome": nome}, priority=prioridade)
        worker({"r": registrar}).iniciar()
        assert esperar(lambda: len(ordem) == 4)
        assert ordem == ["urgente", "a", "b", "c"]

    def test_cancela_job_em_execucao(self, servicos: Servicos, worker: Any) -> None:
        job = servicos.store.criar("lento", "A", {"passos": 500})
        worker({"lento": _lento}).iniciar()
        assert esperar(lambda: (servicos.store.obter(job.id) or job).progress > 0)
        servicos.store.cancelar(job.id)
        assert esperar(lambda: _status(servicos, job) == JobStatus.CANCELED)
        final = servicos.store.obter(job.id)
        assert final is not None and final.progress < 1.0 and final.message == "Cancelado"

    def test_pausa_segura_o_progresso_e_retoma(self, servicos: Servicos, worker: Any) -> None:
        job = servicos.store.criar("lento", "A", {"passos": 120})
        worker({"lento": _lento}).iniciar()
        assert esperar(lambda: (servicos.store.obter(job.id) or job).progress > 0.05)
        servicos.store.pausar(job.id)
        assert esperar(lambda: _status(servicos, job) == JobStatus.PAUSED)
        parado = (servicos.store.obter(job.id) or job).progress
        time.sleep(0.4)
        assert (servicos.store.obter(job.id) or job).progress == parado  # nada andou durante a pausa
        servicos.store.retomar(job.id)
        # cada passo dorme 20 ms (no Windows, ~31 ms) e grava o progresso: com o computador carregado 120 passos passam dos 15 s
        assert esperar(lambda: _status(servicos, job) == JobStatus.DONE, timeout=120)

    def test_cancelar_job_pausado_no_worker(self, servicos: Servicos, worker: Any) -> None:
        job = servicos.store.criar("lento", "A", {"passos": 500})
        worker({"lento": _lento}).iniciar()
        assert esperar(lambda: (servicos.store.obter(job.id) or job).progress > 0)
        servicos.store.pausar(job.id)
        assert esperar(lambda: _status(servicos, job) == JobStatus.PAUSED)
        servicos.store.cancelar(job.id)
        assert esperar(lambda: _status(servicos, job) == JobStatus.CANCELED)

    def test_job_interrompido_por_reinicio_e_refeito(self, servicos: Servicos, worker: Any) -> None:
        job = servicos.store.criar("ok", "A")
        assert servicos.store.reservar_proximo() is not None  # ficou "executando" quando o app caiu
        assert servicos.store.recuperar_interrompidos() == 1
        worker({"ok": _ok}).iniciar()
        assert esperar(lambda: _status(servicos, job) == JobStatus.DONE)
        assert (servicos.store.obter(job.id) or job).attempts == 2

    def test_eventos_de_cada_transicao(self, servicos: Servicos, worker: Any) -> None:
        vistos: list[tuple[str, str]] = []
        original = servicos.bus.publicar
        servicos.bus.publicar = lambda tipo, dados: (
            vistos.append((tipo, dados.get("status", ""))),
            original(tipo, dados),
        )[1]  # type: ignore[method-assign]
        job = servicos.store.criar("ok", "A")
        worker({"ok": _ok}).iniciar()
        assert esperar(lambda: _status(servicos, job) == JobStatus.DONE)
        assert esperar(lambda: ("job.updated", "done") in vistos)
        assert ("job.updated", "running") in vistos

    def test_acordar_e_parar(self, servicos: Servicos, worker: Any) -> None:
        w = worker({"ok": _ok})
        assert not w.vivo
        w.iniciar()
        w.iniciar()  # idempotente
        assert w.vivo and w.job_atual is None
        job = servicos.store.criar("ok", "A")
        w.acordar()
        assert esperar(lambda: _status(servicos, job) == JobStatus.DONE)
        w.parar()
        assert not w.vivo


class TestExecutarProcesso:
    def _contexto(self, sv: Servicos) -> tuple[JobContext, Job]:
        criado = sv.store.criar("x", "proc")
        job = sv.store.reservar_proximo()
        assert job is not None and job.id == criado.id
        return JobContext(job, sv.store, sv.bus, sv), job

    def test_captura_a_saida(self, servicos: Servicos) -> None:
        ctx, _ = self._contexto(servicos)
        r = ctx.executar_processo([sys.executable, "-c", "print('olá')"], timeout=30)
        assert r.returncode == 0 and "olá" in r.stdout

    def test_devolve_codigo_de_erro(self, servicos: Servicos) -> None:
        ctx, _ = self._contexto(servicos)
        r = ctx.executar_processo([sys.executable, "-c", "import sys; print('x'); sys.exit(3)"], timeout=30)
        assert r.returncode == 3

    def test_estoura_o_tempo_limite_e_mata_o_processo(self, servicos: Servicos) -> None:
        ctx, _ = self._contexto(servicos)
        inicio = time.monotonic()
        with pytest.raises(TimeoutError):
            ctx.executar_processo([sys.executable, "-c", "import time; time.sleep(60)"], timeout=0.6)
        assert time.monotonic() - inicio < 10

    def test_cancelar_mata_o_processo(self, servicos: Servicos) -> None:
        ctx, job = self._contexto(servicos)
        resultado: dict[str, BaseException | None] = {"erro": None}

        def rodar() -> None:
            try:
                ctx.executar_processo([sys.executable, "-c", "import time; time.sleep(60)"], timeout=120)
            except BaseException as exc:
                resultado["erro"] = exc

        t = threading.Thread(target=rodar)
        t.start()
        time.sleep(0.6)
        servicos.store.cancelar(job.id)
        t.join(10)
        assert not t.is_alive()
        assert isinstance(resultado["erro"], JobCanceled)

    def test_ao_tick_recebe_o_tempo_decorrido(self, servicos: Servicos) -> None:
        ctx, _ = self._contexto(servicos)
        ticks: list[float] = []
        ctx.executar_processo([sys.executable, "-c", "import time; time.sleep(0.8)"], timeout=30, ao_tick=ticks.append)
        assert len(ticks) >= 2 and ticks == sorted(ticks)

    def test_progresso_calcula_eta_e_ignora_repeticao(
        self, servicos: Servicos, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        relogio = (
            RelogioFalso()
        )  # o tempo é do teste: dormir de verdade deixava o resultado na mão da carga do computador
        monkeypatch.setattr("app.jobs.worker.time", relogio)
        ctx, job = self._contexto(servicos)
        relogio.agora += 1.1
        ctx.progresso(0.5, "metade")
        atual = servicos.store.obter(job.id)
        assert atual is not None and atual.eta_seconds == pytest.approx(1.1)  # metade em 1,1 s: falta mais 1,1 s
        relogio.agora += 0.05
        ctx.progresso(0.6, "metade")  # mesma mensagem, menos de 0,1 s depois: não regrava
        atual2 = servicos.store.obter(job.id)
        assert atual2 is not None and atual2.progress == 0.5
        relogio.agora += 0.2
        ctx.progresso(0.6, "metade")  # agora passou mais de 0,1 s: regrava
        atual3 = servicos.store.obter(job.id)
        assert atual3 is not None and atual3.progress == 0.6


class TestEventBus:
    def test_entrega_de_outra_thread_para_o_loop(self) -> None:
        async def principal() -> dict[str, Any]:
            bus = EventBus()
            sub = bus.assinar()
            threading.Thread(target=lambda: bus.publicar("job.updated", {"id": "1"})).start()
            evento = await asyncio.wait_for(sub.fila.get(), 3)
            bus.cancelar(sub)
            assert bus.total_assinantes() == 0
            return evento

        assert asyncio.run(principal()) == {"type": "job.updated", "data": {"id": "1"}}

    def test_fila_cheia_descarta_o_mais_antigo(self) -> None:
        async def principal() -> list[Any]:
            fila: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=2)
            for n in range(4):
                EventBus._entregar(fila, {"n": n})
            return [fila.get_nowait()["n"], fila.get_nowait()["n"]]

        assert asyncio.run(principal()) == [2, 3]

    def test_varios_assinantes_recebem(self) -> None:
        async def principal() -> tuple[Any, Any]:
            bus = EventBus()
            a, b = bus.assinar(), bus.assinar()
            bus.publicar("t", {"v": 1})
            return await asyncio.wait_for(a.fila.get(), 2), await asyncio.wait_for(b.fila.get(), 2)

        x, y = asyncio.run(principal())
        assert x == y == {"type": "t", "data": {"v": 1}}


class TestStreamSse:
    def test_snapshot_ping_e_evento(self, servicos: Servicos) -> None:
        servicos.store.criar("ok", "existente")

        async def principal() -> list[str]:
            async def desconectado() -> bool:
                return False

            saida: list[str] = []

            async def consumir() -> None:
                async for pedaco in gerar_eventos(servicos, desconectado, heartbeat=0.05, max_eventos=2):
                    saida.append(pedaco)

            tarefa = asyncio.create_task(consumir())
            await asyncio.sleep(0.2)
            servicos.bus.publicar("job.updated", {"id": "abc"})
            await asyncio.wait_for(tarefa, 3)
            return saida

        saida = asyncio.run(principal())
        assert saida[0].startswith(": conectado")
        assert saida[1].startswith("event: snapshot") and "existente" in saida[1]
        assert any(p.startswith(": ping") for p in saida)
        assert saida[-1].startswith("event: job.updated") and '"abc"' in saida[-1]
        assert servicos.bus.total_assinantes() == 0

    def test_para_quando_o_cliente_desconecta(self, servicos: Servicos) -> None:
        async def principal() -> int:
            async def desconectado() -> bool:
                return True

            return len([p async for p in gerar_eventos(servicos, desconectado, heartbeat=0.05)])

        assert asyncio.run(principal()) == 2  # só o ": conectado" e o snapshot
        assert servicos.bus.total_assinantes() == 0
