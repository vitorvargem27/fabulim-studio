"""Tipos de job disponíveis. Cada fase acrescenta os seus (imagem, voz, música, animação...)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from ..benchmark.runner import BenchmarkRunner
from ..ferramentas.catalogo import por_id
from ..ferramentas.instalador import ErroDeInstalacao, Instalador
from ..hardware.runner import comando_diagnostico
from .worker import Handler, JobContext

REGISTRO: dict[str, Handler] = {}

TITULOS: dict[str, str] = {
    "demo.sleep": "Job de demonstração",
    "system.diagnostico": "Diagnóstico da máquina",
    "benchmark.calibracao": "Benchmark de calibração",
    "ferramentas.instalar": "Instalação de ferramenta",
}


def job_handler(kind: str) -> Callable[[Handler], Handler]:
    def registrar(funcao: Handler) -> Handler:
        REGISTRO[kind] = funcao
        return funcao

    return registrar


def _numero(valor: Any, padrao: float, minimo: float, maximo: float) -> float:
    try:
        return min(max(float(valor), minimo), maximo)
    except (TypeError, ValueError):
        return padrao


@job_handler("demo.sleep")
def demonstracao(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    """Job de mentira para ver a fila funcionando (progresso, pausa, cancelamento e retomada)."""
    segundos = _numero(params.get("seconds"), 10.0, 0.2, 600.0)
    passos = int(_numero(params.get("steps"), 20, 1, 600))
    falhar_em = params.get("fail_at")
    for i in range(passos):
        ctx.ponto_de_controle()
        time.sleep(segundos / passos)
        if falhar_em is not None and i + 1 == falhar_em:
            raise RuntimeError("falha de demonstração pedida em fail_at")
        ctx.progresso((i + 1) / passos, f"Passo {i + 1} de {passos}")
    return {"seconds": segundos, "steps": passos}


@job_handler("system.diagnostico")
def diagnostico(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    leve = bool(params.get("leve", False))
    sv = ctx.servicos
    if sv.hardware.notebook_na_bateria():
        ctx.log("Notebook na bateria: o diagnóstico é leve, mas jobs pesados devem esperar a tomada.", "WARNING")
    ctx.progresso(0.05, "Coletando informações da máquina..." if not leve else "Conferindo se a máquina mudou...")
    limite = 60 if leve else 180
    proc = ctx.executar_processo(
        comando_diagnostico(sv.settings, leve=leve),
        timeout=900,
        ao_tick=lambda t: ctx.progresso(min(0.85, 0.05 + 0.8 * t / limite), None),
    )
    if proc.returncode != 0:
        resumo = " ".join(proc.stdout.split())[:300]
        raise RuntimeError(f"o coletor terminou com código {proc.returncode}: {resumo}")
    ctx.progresso(0.9, "Classificando o perfil e calculando as capacidades...")
    sv.hardware.salvar_capacidades()
    snap = sv.hardware.snapshot()
    if not snap.get("valid"):
        raise RuntimeError("o coletor gerou um hardware.json inválido: " + "; ".join(snap.get("errors", [])[:3]))
    return {"profile": snap["profile"]["letter"], "changed": snap["changed"], "mode": snap["mode"]}


@job_handler("ferramentas.instalar")
def instalar_ferramenta(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    """Baixa e instala um item do catálogo (só fonte oficial, SHA-256 conferido) com progresso na Fila."""
    from .servico import enfileirar, job_ativo_do_tipo  # import tardio: servico importa este módulo

    try:
        item = por_id(str(params.get("id")))
    except KeyError:
        raise RuntimeError(f"ferramenta desconhecida: {params.get('id')!r}") from None
    sv = ctx.servicos

    def progresso(etapa: str, feitos: int, total: int) -> None:
        ctx.ponto_de_controle()  # pausa e cancelamento valem durante o download (o que já veio fica para retomar)
        if etapa == "baixando" and total:
            ctx.progresso(
                0.05 + 0.85 * feitos / total, f"Baixando {item.nome}: {feitos // 1_000_000} de {total // 1_000_000} MB"
            )
        else:
            ctx.progresso(
                {"consultando a fonte oficial": 0.02, "conferindo o SHA-256": 0.9, "extraindo": 0.95}.get(etapa, 0.5),
                etapa.capitalize() + "...",
            )

    ctx.log(f"Instalando {item.nome} ({item.licenca})")
    try:
        resultado = Instalador(sv.settings).instalar(item, progresso)
    except ErroDeInstalacao as exc:
        raise RuntimeError(str(exc)) from exc
    ctx.log(f"{item.nome}: {resultado.situacao}")
    if job_ativo_do_tipo(sv, "system.diagnostico") is None:  # o diagnóstico leve reconhece o que acabou de entrar
        enfileirar(sv, "system.diagnostico", {"leve": True}, titulo="Diagnóstico da máquina (leve)")
    ctx.progresso(1.0, f"{item.nome} pronto")
    return {"id": item.id, "status": resultado.situacao}


@job_handler("benchmark.calibracao")
def calibracao(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    sv = ctx.servicos
    if sv.hardware.notebook_na_bateria():
        ctx.log("Notebook na bateria: a medição fica menos confiável (o processador reduz a velocidade).", "WARNING")
    snap = sv.hardware.carregar() or {}
    resultado = BenchmarkRunner(sv.ollama, sv.benchmarks, str(snap.get("fingerprint") or ""), sv.medidores).executar(
        ctx
    )
    sv.hardware.salvar_capacidades()  # os ETAs medidos entram na matriz
    return resultado
