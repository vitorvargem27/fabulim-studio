"""Motor de imagem: stable-diffusion.cpp com o FLUX.2 klein (quantizado), pela placa de vídeo (Vulkan) ou pelo processador.

Cada imagem roda num processo à parte (cancelável pela Fila). Sem o motor instalado, `indisponivel()` diz o que fazer.
Com imagens de referência (`-r`), o modelo edita a partir delas: é como um personagem mantém a aparência entre poses.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from ..config import Settings
from ..ferramentas import detectar
from .tipos import Contexto, MotorFalhou, MotorIndisponivel, PedidoImagem, ResultadoImagem
from .util import e_png, final_da_saida, parece_falta_de_memoria, tempo_do_log

MODELO = "FLUX.2 klein 4B (Q4_0)"
CFG = "1.0"  # o FLUX.2 klein é destilado: sem guia por texto negativo
ESTIMATIVA_PADRAO_512 = 120.0  # segundos por imagem de 512 px enquanto não há medição neste computador
PIXELS_512 = 512 * 512
FATOR_DO_PROCESSADOR = (
    7.0  # o processador leva ~7x o tempo da placa de vídeo (medido neste computador); só afeta a barra de progresso
)
TENTATIVAS_NA_PLACA = (
    2  # uma falha na placa de vídeo costuma ser passageira (driver): tenta de novo antes de ir para o processador
)
NAO_INSTALADO = "O motor de imagens ainda não está instalado: abra Modelos e clique em «Instalar tudo o que falta»."


class MotorDeImagemSdCpp:
    def __init__(
        self,
        settings: Settings,
        usa_vulkan: Callable[[], bool],
        segundos_medidos_512: Callable[[], float | None] = lambda: None,
    ) -> None:
        self._settings = settings
        self._usa_vulkan = usa_vulkan
        self._segundos_medidos_512 = segundos_medidos_512

    def indisponivel(self) -> str | None:
        itens_faltam, libs_faltam = detectar.pendencias(self._settings, "imagem")
        if itens_faltam or libs_faltam:
            return NAO_INSTALADO
        return None

    def estimativa(self, largura: int, altura: int, com_referencia: bool = False) -> float:
        """Segundos esperados para uma imagem: a medição deste computador (benchmark) escalada pelos pixels."""
        base = self._segundos_medidos_512() or ESTIMATIVA_PADRAO_512
        fator = (largura * altura) / PIXELS_512
        return base * fator * (1.3 if com_referencia else 1.0)

    def _tentativas(self) -> list[tuple[str, str]]:
        """A ordem das tentativas: placa de vídeo (duas vezes, se for o caminho preferido) e depois o processador."""
        vulkan, cpu = ("vulkan", "sd-cpp"), ("cpu", "sd-cpp-cpu")
        ordem = [*[vulkan] * TENTATIVAS_NA_PLACA, cpu] if self._usa_vulkan() else [cpu, vulkan]
        return [(nome, id_) for nome, id_ in ordem if detectar.caminho(self._settings, id_).exists()]

    def comando(self, programa: str, pedido: PedidoImagem, saida: Path) -> list[str]:
        s = self._settings
        cmd = [
            str(detectar.caminho(s, programa)),
            "--diffusion-model",
            str(detectar.caminho(s, "flux2-klein-4b")),
            "--vae",
            str(detectar.caminho(s, "flux2-vae")),
            "--llm",
            str(detectar.caminho(s, "qwen3-4b-texto")),
            "-p",
            pedido.prompt,
            "-W",
            str(pedido.largura),
            "-H",
            str(pedido.altura),
            "--steps",
            str(pedido.passos),
            "--cfg-scale",
            CFG,
            "--sampling-method",
            "euler",
            "--diffusion-fa",
            "-s",
            str(pedido.seed),
        ]
        for referencia in pedido.referencias:
            cmd += ["-r", str(referencia)]
        return [*cmd, "-o", str(saida)]

    def gerar(
        self, ctx: Contexto, pedido: PedidoImagem, saida: Path, faixa: tuple[float, float] = (0.0, 1.0)
    ) -> ResultadoImagem:
        if motivo := self.indisponivel():
            raise MotorIndisponivel(motivo)
        if (
            pedido.largura % 16
            or pedido.altura % 16
            or not 256 <= pedido.largura <= 2048
            or not 256 <= pedido.altura <= 2048
        ):
            raise MotorFalhou(
                f"Tamanho de imagem não suportado: {pedido.largura}×{pedido.altura} (múltiplos de 16, de 256 a 2048)."
            )
        na_placa = self.estimativa(pedido.largura, pedido.altura, bool(pedido.referencias))
        saida.parent.mkdir(parents=True, exist_ok=True)
        falhas: list[str] = []
        sem_nova_tentativa: set[str] = set()
        tentativas = 0

        for indice, (caminho, programa) in enumerate(self._tentativas()):
            if caminho in sem_nova_tentativa:
                continue
            estimativa = na_placa * (FATOR_DO_PROCESSADOR if caminho == "cpu" else 1.0)

            def andamento(decorrido: float, estimativa: float = estimativa) -> None:
                ctx.progresso(faixa[0] + (faixa[1] - faixa[0]) * min(0.95, decorrido / estimativa), None)

            if indice > 0:
                ctx.progresso(
                    faixa[0],
                    "Tentando de novo pelo processador (bem mais lento)..."
                    if caminho == "cpu"
                    else "Tentando de novo pela placa de vídeo...",
                )
            tentativas += 1
            comando = self.comando(programa, pedido, saida)
            inicio = time.monotonic()
            try:
                proc = ctx.executar_processo(comando, timeout=3600, ao_tick=andamento, cwd=Path(comando[0]).parent)
            except TimeoutError as exc:
                falhas.append(f"{caminho}: não terminou a tempo ({exc})")
                sem_nova_tentativa.add(caminho)  # se travou uma hora, repetir no mesmo caminho só gasta mais uma hora
                continue
            segundos = round(time.monotonic() - inicio, 1)
            if proc.returncode != 0 or not e_png(saida):
                motivo = final_da_saida(proc.stdout)
                falhas.append(f"{caminho}: {motivo}")
                ctx.log(f"A imagem falhou com o caminho {caminho}: {motivo}", "WARNING")
                saida.unlink(missing_ok=True)
                continue
            return ResultadoImagem(
                caminho=saida,
                segundos=segundos,
                seed=pedido.seed,
                largura=pedido.largura,
                altura=pedido.altura,
                caminho_de_execucao=caminho,
                modelo=MODELO,
                metricas={
                    "generate_s": tempo_do_log(r"generate_image completed in ([0-9.]+)s", proc.stdout),
                    "sampling_s": tempo_do_log(r"sampling completed, taking ([0-9.]+)s", proc.stdout),
                    "decode_s": tempo_do_log(r"decode_first_stage completed, taking ([0-9.]+)s", proc.stdout),
                    "steps": pedido.passos,
                    "references": len(pedido.referencias),
                    "attempts": tentativas,
                    "fell_back": bool(falhas),
                },
            )
        if not falhas:
            raise MotorIndisponivel(NAO_INSTALADO)
        dica = (
            " O computador ficou sem memória: tente a qualidade «rascunho», gere uma imagem por vez ou feche outros programas."
            if any(parece_falta_de_memoria(f) for f in falhas)
            else ""
        )
        raise MotorFalhou("Não consegui gerar a imagem. " + " | ".join(falhas) + dica)
