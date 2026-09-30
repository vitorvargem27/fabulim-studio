"""Benchmark de calibração (briefing, seção 2.4): mede o que já está instalado e confirma as estimativas.

Mede de verdade o LLM local, a voz, o recorte de fundo e a geração de imagem, quando o motor está instalado. O que ainda
não pode ser medido (música, animação por IA) aparece como "não medido", com o motivo. Nada é fingido.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from ..db import Database
from ..jobs.models import agora_iso
from ..services.ollama import OllamaClient, OllamaIndisponivel
from .medidores import Medidores
from .resultado import ResultadoBench

if TYPE_CHECKING:
    from ..jobs.worker import JobContext

PROMPT_CURTO = (
    "Responda somente com JSON valido em portugues do Brasil, sem explicacoes. Crie uma cena curta para criancas de 3 anos: "
    "um coelho azul chamado Bolinho descobre a cor amarela num campo de girassois. "
    "Campos: titulo, fala_do_narrador, acao_do_personagem."
)
_PARAGRAFO = (
    "O coelho Bolinho acordou cedo, esticou as orelhas e foi ate o campo. La ele viu flores grandes, redondas e brilhantes. "
    "A borboleta Lili contou que aquela cor se chama amarelo, a mesma cor do sol. Bolinho riu, pulou tres vezes e abracou um girassol. "
)
PROMPT_LONGO = (
    _PARAGRAFO * 12
    + " Com base na historia acima, escreva em JSON o titulo e uma fala curta do narrador, sem explicacoes."
)

PENDENTES: tuple[tuple[str, str], ...] = (
    ("music", "A medição da música ainda não está disponível nesta versão."),
    ("video", "A medição da animação por IA ainda não está disponível nesta versão."),
)

__all__ = ["BenchmarkRunner", "BenchmarkStore", "ResultadoBench", "medir_llm"]


class BenchmarkStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def salvar(self, r: ResultadoBench, fingerprint: str | None = None) -> None:
        with self._db.transaction() as c:
            c.execute(
                "INSERT INTO benchmarks (task, status, model, seconds, metrics, detail, fingerprint, measured_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (r.task, r.status, r.model, r.seconds, json.dumps(r.metrics), r.detail, fingerprint, agora_iso()),
            )

    def ultimos(self) -> list[dict[str, Any]]:
        """A medição mais recente de cada tarefa."""
        with self._db.transaction() as c:
            rows = c.execute(
                "SELECT b.* FROM benchmarks b JOIN (SELECT task, MAX(id) AS id FROM benchmarks GROUP BY task) u ON b.id = u.id"
                " ORDER BY b.task"
            ).fetchall()
        saida = []
        for r in rows:
            d = dict(r)
            d["metrics"] = json.loads(d["metrics"] or "{}")
            saida.append(d)
        return saida

    def medicoes(self) -> dict[str, Any]:
        """Números usados pela matriz de capacidades (ETAs medidos)."""
        saida: dict[str, Any] = {}
        for r in self.ultimos():
            if r["task"] == "llm_ollama" and r["status"] == "ok":
                m = r["metrics"]
                saida.update(
                    llm_gen_tok_s=m.get("gen_tok_s"),
                    llm_prefill_tok_s=m.get("prefill_tok_s"),
                    llm_modelo=r["model"],
                    llm_processador=m.get("processor"),
                    llm_medido_em=r["measured_at"],
                )
            elif r["task"] == "tts" and r["status"] == "ok":
                saida.update(voz_rtf=r["metrics"].get("rtf"), voz_medido_em=r["measured_at"])
            elif r["task"] == "cutout" and r["status"] == "ok":
                saida.update(recorte_seg=r["metrics"].get("infer_s"), recorte_medido_em=r["measured_at"])
            elif r["task"] == "image" and r["status"] == "ok":
                m = r["metrics"]
                saida.update(
                    imagem_seg=m.get("wall_s"),
                    imagem_lado=m.get("size"),
                    imagem_passos=m.get("steps"),
                    imagem_backend=m.get("backend"),
                    imagem_modelo=r["model"],
                    imagem_medido_em=r["measured_at"],
                )
        return saida


def _tok_s(tokens: Any, duracao_ns: Any) -> float | None:
    try:
        return round(float(tokens) / (float(duracao_ns) / 1e9), 2) if float(duracao_ns) > 0 else None
    except (TypeError, ValueError):
        return None


def medir_llm(ollama: OllamaClient, modelo_preferido: str | None = None) -> ResultadoBench:
    """Velocidade de geração e de prefill do menor modelo instalado (ou do escolhido)."""
    inicio = time.monotonic()
    try:
        modelos = [m for m in ollama.modelos() if "embed" not in str(m.get("name", "")).lower()]
    except OllamaIndisponivel as exc:
        return ResultadoBench("llm_ollama", "skipped", detail=f"Ollama não respondeu: {exc}")
    if not modelos:
        return ResultadoBench("llm_ollama", "skipped", detail="Nenhum modelo instalado no Ollama.")
    escolhido = next((m for m in modelos if m.get("name") == modelo_preferido), None) or min(
        modelos, key=lambda m: m.get("size", 0)
    )
    nome = str(escolhido["name"])
    try:
        ollama.gerar(nome, "ola", num_predict=4)  # carrega o modelo na memória
        curto = ollama.gerar(nome, PROMPT_CURTO, num_predict=96)
        longo = ollama.gerar(nome, PROMPT_LONGO, num_predict=8)
        carregados = ollama.carregados()
        processador = (
            "gpu" if any((m.get("size_vram") or 0) > 0 for m in carregados if m.get("name") == nome) else "cpu"
        )
        ollama.descarregar(nome)  # libera a RAM para o próximo job pesado
    except OllamaIndisponivel as exc:
        return ResultadoBench("llm_ollama", "error", model=nome, detail=f"Falha durante a medição: {exc}")
    gen = _tok_s(curto.get("eval_count"), curto.get("eval_duration"))
    prefill = _tok_s(longo.get("prompt_eval_count"), longo.get("prompt_eval_duration"))
    return ResultadoBench(
        "llm_ollama",
        "ok",
        model=nome,
        seconds=round(time.monotonic() - inicio, 1),
        metrics={
            "gen_tok_s": gen,
            "prefill_tok_s": prefill,
            "prompt_tokens": longo.get("prompt_eval_count"),
            "processor": processador,
        },
    )


class BenchmarkRunner:
    def __init__(
        self, ollama: OllamaClient, store: BenchmarkStore, fingerprint: str | None, medidores: Medidores
    ) -> None:
        self._ollama = ollama
        self._store = store
        self._fingerprint = fingerprint
        self._medidores = medidores

    def _registrar(self, ctx: JobContext, resultado: ResultadoBench, nome: str) -> None:
        self._store.salvar(resultado, self._fingerprint)
        ctx.log(f"{nome}: {resultado.status}" + (f" ({resultado.detail})" if resultado.detail else ""))

    def executar(self, ctx: JobContext) -> dict[str, Any]:
        ctx.progresso(0.03, "Medindo o LLM local (leva cerca de 1 minuto)...")
        ctx.ponto_de_controle()
        llm = medir_llm(self._ollama)
        self._store.salvar(llm, self._fingerprint)
        ctx.log(
            f"LLM: {llm.status}"
            + (f" ({llm.model}: {llm.metrics.get('gen_tok_s')} tok/s)" if llm.status == "ok" else f": {llm.detail}")
        )
        etapas = (
            ("Voz", self._medidores.voz, (0.2, 0.26)),
            ("Recorte de fundo", self._medidores.recorte, (0.26, 0.4)),
            ("Imagem", self._medidores.imagem, (0.4, 0.95)),
        )
        resultados: dict[str, ResultadoBench] = {}
        for nome, medir, faixa in etapas:
            ctx.ponto_de_controle()
            ctx.progresso(faixa[0], f"Medindo: {nome.lower()}...")
            resultado = medir(ctx, faixa)
            resultados[nome] = resultado
            self._registrar(ctx, resultado, nome)
        ctx.progresso(0.96, "Registrando o que ainda não pode ser medido...")
        for tarefa, motivo in PENDENTES:
            self._store.salvar(ResultadoBench(tarefa, "skipped", detail=motivo), self._fingerprint)
        ctx.progresso(1.0, "Benchmark concluído")
        return {
            "llm": llm.status,
            "model": llm.model,
            "gen_tok_s": llm.metrics.get("gen_tok_s"),
            "prefill_tok_s": llm.metrics.get("prefill_tok_s"),
            "voice": resultados["Voz"].status,
            "cutout": resultados["Recorte de fundo"].status,
            "image": resultados["Imagem"].status,
        }
