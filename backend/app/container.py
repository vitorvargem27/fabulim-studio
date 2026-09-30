"""Contêiner de serviços: monta e guarda as peças do backend (banco, fila, eventos, hardware, Ollama, medidores)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import tarefas  # noqa: F401  (registra os tipos de job das ferramentas)
from .benchmark.medidores import Medidores, MedidoresReais
from .benchmark.runner import BenchmarkStore
from .config import Settings
from .db import Database
from .hardware.estado import HardwareState
from .hardware.perfil import obter
from .jobs.events import EventBus
from .jobs.handlers import REGISTRO
from .jobs.store import JobStore
from .jobs.worker import JobWorker
from .midias import RepositorioMidias
from .motores.fabrica import Motores, criar_motores
from .personagens import RepositorioPersonagens
from .projetos.repositorio import RepositorioProjetos
from .prompts.historico import HistoricoDePrompts
from .services.ollama import OllamaClient


@dataclass
class Servicos:
    settings: Settings
    db: Database
    store: JobStore
    bus: EventBus
    benchmarks: BenchmarkStore
    hardware: HardwareState
    ollama: OllamaClient
    medidores: Medidores
    midias: RepositorioMidias
    motores: Motores
    personagens: RepositorioPersonagens
    historico: HistoricoDePrompts
    projetos: RepositorioProjetos
    inicio: float = field(default_factory=time.monotonic)
    worker: JobWorker | None = None


def criar_servicos(
    settings: Settings,
    *,
    ollama: OllamaClient | None = None,
    medidores: Medidores | None = None,
    motores: Motores | None = None,
) -> Servicos:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.db_path)
    db.migrar()
    benchmarks = BenchmarkStore(db)
    hardware = HardwareState(settings, benchmarks.medicoes)

    def usa_vulkan() -> bool:
        return bool(obter(hardware.carregar() or {}, "acceleration.vulkan.available"))

    cliente = ollama or OllamaClient(settings.ollama_url)
    sv = Servicos(
        settings=settings,
        db=db,
        store=JobStore(db),
        bus=EventBus(),
        benchmarks=benchmarks,
        hardware=hardware,
        ollama=cliente,
        medidores=medidores or MedidoresReais(settings, usa_vulkan),
        midias=RepositorioMidias(db, settings.midias_dir),
        motores=motores or criar_motores(settings, cliente, benchmarks.medicoes, usa_vulkan),
        personagens=RepositorioPersonagens(db),
        historico=HistoricoDePrompts(db),
        projetos=RepositorioProjetos(db),
    )
    sv.worker = JobWorker(sv.store, sv.bus, sv, REGISTRO)
    return sv
