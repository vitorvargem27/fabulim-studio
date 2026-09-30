"""Motor de recorte de fundo: BiRefNet lite (ONNX, processador). Devolve um PNG transparente cortado rente ao personagem."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from ..config import Settings
from ..ferramentas import detectar
from .tipos import Contexto, MotorFalhou, MotorIndisponivel
from .util import e_png, final_da_saida, json_da_saida

SCRIPT = Path(__file__).resolve().parent / "scripts" / "recortar_imagem.py"
NAO_INSTALADO = "O recorte de fundo ainda não está instalado: abra Modelos e clique em «Instalar tudo o que falta»."
ESTIMATIVA_SEGUNDOS = 30.0


class MotorDeRecorteBiRefNet:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def indisponivel(self) -> str | None:
        itens_faltam, libs_faltam = detectar.pendencias(self._settings, "recorte")
        return NAO_INSTALADO if itens_faltam or libs_faltam else None

    def recortar(
        self, ctx: Contexto, origem: Path, saida: Path, *, caixa: bool = True, faixa: tuple[float, float] = (0.0, 1.0)
    ) -> dict[str, Any]:
        if motivo := self.indisponivel():
            raise MotorIndisponivel(motivo)
        saida.parent.mkdir(parents=True, exist_ok=True)
        comando = [
            sys.executable,
            str(SCRIPT),
            str(detectar.caminho(self._settings, "birefnet-lite")),
            str(origem),
            str(saida),
        ]
        if caixa:
            comando.append("--caixa")
        inicio = time.monotonic()

        def andamento(decorrido: float) -> None:
            ctx.progresso(faixa[0] + (faixa[1] - faixa[0]) * min(0.95, decorrido / ESTIMATIVA_SEGUNDOS), None)

        try:
            proc = ctx.executar_processo(comando, timeout=900, ao_tick=andamento, cwd=SCRIPT.parent)
        except TimeoutError as exc:
            raise MotorFalhou(f"O recorte de fundo não terminou a tempo: {exc}") from exc
        if proc.returncode != 0 or not e_png(saida):
            saida.unlink(missing_ok=True)
            raise MotorFalhou(f"Não consegui recortar o fundo: {final_da_saida(proc.stdout)}")
        try:
            dados = json_da_saida(proc.stdout)
        except ValueError:
            dados = {}
        dados["wall_s"] = round(time.monotonic() - inicio, 1)
        return dados
