"""Motor de voz: Kokoro 82M (ONNX, processador), em português do Brasil e em inglês.

Fala vários textos por processo (o modelo carrega uma vez só). O tom da voz (mais grave ou mais aguda) é ajustado depois,
com o ffmpeg, sem mudar a duração.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

from ..config import Settings
from ..ferramentas import detectar
from .tipos import Contexto, ItemDeVoz, MotorFalhou, MotorIndisponivel, ResultadoDeVoz
from .util import final_da_saida, json_da_saida

SCRIPT = Path(__file__).resolve().parent / "scripts" / "sintetizar_voz.py"
NAO_INSTALADO = "A voz ainda não está instalada: abra Modelos e clique em «Instalar tudo o que falta»."

# Vozes do Kokoro por idioma (as três em português do Brasil e as principais em inglês).
VOZES: dict[str, list[dict[str, str]]] = {
    "pt-BR": [
        {"id": "pf_dora", "nome": "Dora (feminina)", "lingua": "pt-br"},
        {"id": "pm_alex", "nome": "Alex (masculina)", "lingua": "pt-br"},
        {"id": "pm_santa", "nome": "Santa (masculina, grave)", "lingua": "pt-br"},
    ],
    "en": [
        {"id": "af_heart", "nome": "Heart (feminina)", "lingua": "en-us"},
        {"id": "af_bella", "nome": "Bella (feminina)", "lingua": "en-us"},
        {"id": "am_adam", "nome": "Adam (masculina)", "lingua": "en-us"},
        {"id": "bf_emma", "nome": "Emma (feminina, britânica)", "lingua": "en-gb"},
    ],
}
LINGUA_DA_VOZ = {v["id"]: v["lingua"] for vozes in VOZES.values() for v in vozes}


def lingua_da_voz(voz: str) -> str:
    return LINGUA_DA_VOZ.get(voz, "pt-br")


class MotorDeVozKokoro:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def indisponivel(self) -> str | None:
        itens_faltam, libs_faltam = detectar.pendencias(self._settings, "voz")
        return NAO_INSTALADO if itens_faltam or libs_faltam else None

    def falar(
        self, ctx: Contexto, itens: Sequence[ItemDeVoz], faixa: tuple[float, float] = (0.0, 1.0)
    ) -> list[ResultadoDeVoz]:
        """Fala todos os textos e devolve a duração de cada áudio, na mesma ordem."""
        if motivo := self.indisponivel():
            raise MotorIndisponivel(motivo)
        if not itens:
            return []
        for item in itens:
            item.saida.parent.mkdir(parents=True, exist_ok=True)
        estimativa = 8.0 + 2.5 * len(itens)  # carga do modelo + ~2,5 s por fala
        inicio = time.monotonic()
        self._settings.temp_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="voz-", dir=self._settings.temp_dir) as pasta:
            pedidos = Path(pasta) / "pedidos.json"
            pedidos.write_text(
                json.dumps(
                    [
                        {
                            "texto": i.texto,
                            "voz": i.voz,
                            "velocidade": i.velocidade,
                            "lingua": i.lingua,
                            "saida": str(i.saida),
                        }
                        for i in itens
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            comando = [
                sys.executable,
                str(SCRIPT),
                str(detectar.caminho(self._settings, "kokoro-modelo")),
                str(detectar.caminho(self._settings, "kokoro-vozes")),
                str(pedidos),
            ]

            def andamento(decorrido: float) -> None:
                ctx.progresso(faixa[0] + (faixa[1] - faixa[0]) * min(0.95, decorrido / estimativa), None)

            try:
                proc = ctx.executar_processo(comando, timeout=1800, ao_tick=andamento, cwd=SCRIPT.parent)
            except TimeoutError as exc:
                raise MotorFalhou(f"A voz não terminou a tempo: {exc}") from exc
        if proc.returncode != 0:
            raise MotorFalhou(f"Não consegui gerar a voz: {final_da_saida(proc.stdout)}")
        try:
            dados = json_da_saida(proc.stdout)
            duracoes = [float(x["duration_s"]) for x in dados["items"]]
        except (ValueError, KeyError, TypeError) as exc:
            raise MotorFalhou(f"A voz terminou sem devolver as durações: {final_da_saida(proc.stdout)}") from exc
        if len(duracoes) != len(itens) or any(not i.saida.is_file() for i in itens):
            raise MotorFalhou("A voz não gerou todos os áudios pedidos.")
        ctx.log(f"Voz: {len(itens)} fala(s) em {time.monotonic() - inicio:.1f} s")
        return [ResultadoDeVoz(i.saida, d) for i, d in zip(itens, duracoes, strict=True)]
