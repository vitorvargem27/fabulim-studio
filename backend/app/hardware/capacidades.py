"""Matriz de capacidades: o estado de cada funcionalidade do briefing (seção 7) neste perfil de hardware.

Estados: ``available`` (disponível), ``slow`` (lenta, com tempo estimado) e ``unavailable`` (com o motivo).
Os tempos vêm do benchmark de calibração quando existe medição; senão são estimativas e vêm marcados como tal.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .perfil import Classificacao, obter

DISPONIVEL = "available"
LENTA = "slow"
INDISPONIVEL = "unavailable"

Caso = tuple[str, str, str | None]  # (estado, motivo, tempo estimado)


@dataclass(frozen=True)
class Capacidade:
    id: str
    nome: str
    secao: str
    fase: int
    estado: str
    motivo: str
    eta: str | None = None
    eta_medido: bool = False

    def para_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.nome,
            "section": self.secao,
            "state": self.estado,
            "reason": self.motivo,
            "eta": self.eta,
            "eta_measured": self.eta_medido,
        }


def formatar_duracao(segundos: float) -> str:
    if segundos < 90:
        return f"{segundos:.0f} s"
    return f"{segundos / 60:.1f}".replace(".", ",") + " min"


def eta_roteiro(medicoes: dict[str, Any]) -> tuple[str | None, bool]:
    """Tempo de um roteiro de 6 cenas (~1.500 tokens de saída, ~1.000 de prompt) com o modelo medido."""
    gen = medicoes.get("llm_gen_tok_s")
    if not isinstance(gen, (int, float)) or gen <= 0:
        return None, False
    pre = medicoes.get("llm_prefill_tok_s")
    prefill = 1000 / pre if isinstance(pre, (int, float)) and pre > 0 else 0.0
    modelo = medicoes.get("llm_modelo") or "o modelo medido"
    return (
        f"≈ {formatar_duracao(1500 / gen + prefill)} por roteiro de 6 cenas com o {modelo} (modelos maiores demoram mais)",
        True,
    )


def _numero(medicoes: dict[str, Any], chave: str) -> float | None:
    valor = medicoes.get(chave)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor <= 0:
        return None
    return float(valor)


def eta_imagem(medicoes: dict[str, Any]) -> tuple[str | None, bool]:
    """Tempo de uma imagem, medido de verdade com o motor de imagens instalado (benchmark de calibração)."""
    segundos = _numero(medicoes, "imagem_seg")
    if segundos is None:
        return None, False
    onde = "com a placa de vídeo" if medicoes.get("imagem_backend") == "vulkan" else "no processador"
    return (
        f"≈ {formatar_duracao(segundos)} por imagem de {medicoes.get('imagem_lado', 512)} px "
        f"({medicoes.get('imagem_passos', 4)} passos, {onde})",
        True,
    )


def eta_personagem(medicoes: dict[str, Any]) -> str | None:
    """4 variações e ~6 poses são ~10 imagens: conta a partir do tempo medido (por isso é estimativa, não medição)."""
    segundos = _numero(medicoes, "imagem_seg")
    return None if segundos is None else f"≈ {formatar_duracao(segundos * 10)} por personagem (10 imagens)"


def eta_voz(medicoes: dict[str, Any]) -> tuple[str | None, bool]:
    fator = _numero(medicoes, "voz_rtf")  # segundos de processamento para cada segundo de fala
    if fator is None:
        return None, False
    return f"≈ {formatar_duracao(fator * 60)} para cada minuto de fala", True


def eta_recorte(medicoes: dict[str, Any]) -> tuple[str | None, bool]:
    segundos = _numero(medicoes, "recorte_seg")
    if segundos is None:
        return None, False
    return f"≈ {formatar_duracao(segundos)} por imagem de 1024 px", True


def calcular(
    hw: dict[str, Any],
    c: Classificacao,
    medicoes: dict[str, Any] | None = None,
    motores: set[str] | None = None,
) -> list[Capacidade]:
    """Estado previsto de cada funcionalidade para este hardware, perfil e conjunto de ferramentas.

    motores são os motores de IA realmente instalados (imagem, voz, recorte...); None = supõe todos.
    """
    medicoes = medicoes or {}
    p = c.perfil
    ffmpeg = bool(obter(hw, "tools.ffmpeg.installed"))
    notebook = bool(obter(hw, "system.is_laptop"))
    neste = "notebook" if notebook else "computador"
    outra = "no desktop" if notebook else "em outra máquina"
    eta_llm, llm_medido = eta_roteiro(medicoes)
    eta_img, img_medido = eta_imagem(medicoes)
    eta_voz_txt, voz_medida = eta_voz(medicoes)
    eta_rec, rec_medido = eta_recorte(medicoes)
    segundos_imagem = _numero(medicoes, "imagem_seg")
    eta_clipe = (
        f"≈ {formatar_duracao(segundos_imagem * 1.3 + 60)} por clipe (1 cenário + animação)"
        if segundos_imagem
        else "2 a 4 min por clipe"
    )
    voz_rapida = (_numero(medicoes, "voz_rtf") or 0.0) < 1.0  # sem medição, o Kokoro é conhecido por ser rápido
    falta_ffmpeg: Caso = (
        INDISPONIVEL,
        "Precisa do ffmpeg, que ainda não está instalado. Abra Modelos e clique em Instalar.",
        None,
    )

    def por_perfil(a: Caso, b: Caso, c_: Caso, d: Caso) -> Caso:
        return {"A": a, "B": b, "C": c_, "D": d}[p]

    def item(id_: str, nome: str, secao: str, fase: int, caso: Caso, *, medido: bool = False) -> Capacidade:
        estado, motivo, eta = caso
        return Capacidade(id_, nome, secao, fase, estado, motivo, eta, medido and eta is not None)

    pesada_d: Caso = (
        INDISPONIVEL,
        "Neste perfil (RAM ou disco abaixo do mínimo) as gerações pesadas ficam desativadas.",
        None,
    )
    sem_gpu_ia: Caso = (
        INDISPONIVEL,
        f"Animação por IA precisa de uma GPU dedicada. Neste {neste}, use Animação de cena ou exporte o projeto para renderizar {outra}.",
        None,
    )

    llm = por_perfil(
        (DISPONIVEL, "Modelos de 7B a 14B rodam na GPU.", "segundos por roteiro"),
        (DISPONIVEL, "Modelos quantizados de 7B a 14B na GPU.", "segundos a ~1 min por roteiro"),
        (
            LENTA,
            "Roda na CPU (a GPU integrada só acelera o início do prompt): modelos de até ~9B. O Claude ajuda muito aqui.",
            eta_llm or "3 a 6 min por roteiro de 6 cenas (modelo de ~9B)",
        ),
        (LENTA, "Só modelos de 1B a 4B; recomenda-se o Claude para os textos.", eta_llm),
    )
    claude_ok = obter(hw, "tools.claude_code.logged_in") is True
    claude_instalado = bool(obter(hw, "tools.claude_code.installed"))
    if claude_ok:
        plano = obter(hw, "tools.claude_code.subscription")
        claude: Caso = (
            DISPONIVEL,
            f"Claude Code logado{f' (plano {plano})' if plano else ''}: pode ser o reforço opcional de texto e visão "
            "quando você conectar a conta ao app (ainda não disponível nesta versão).",
            None,
        )
    elif claude_instalado:
        claude = (
            INDISPONIVEL,
            "Claude Code sem login (opcional). O login é feito pelo fluxo oficial da Anthropic.",
            None,
        )
    else:
        claude = (INDISPONIVEL, "Claude Code não está instalado (opcional).", None)

    def com_ffmpeg(caso: Caso) -> Caso:
        return caso if ffmpeg else falta_ffmpeg

    animacao_cena = (
        pesada_d
        if p == "D"
        else com_ffmpeg(
            (
                DISPONIVEL,
                "Camadas animadas por código (Python e ffmpeg): rápido e consistente.",
                "cerca de 2 a 4 min de render por minuto de vídeo (1080p, contando as vozes)"
                if p == "C"
                else "cerca de 1 a 2 min por minuto de vídeo (1080p)",
            )
        )
    )
    ia_clipe = por_perfil(
        (DISPONIVEL, "Image-to-video na GPU.", None),
        (LENTA, "Só clipes curtos, com modelos quantizados.", None),
        sem_gpu_ia,
        sem_gpu_ia,
    )

    capacidades = [
        item(
            "prompts",
            "Formulários a partir de prompts (estruturado e texto livre)",
            "6",
            2,
            (
                DISPONIVEL,
                "O formato estruturado não precisa de modelo; o texto livre usa o LLM (local ou Claude).",
                None,
            ),
        ),
        item("llm_local", "LLM local (roteiro, enredo, prompt técnico)", "4, 7.4", 2, llm, medido=llm_medido),
        item("claude", "Reforço do Claude (texto e visão)", "15", 2, claude),
        item(
            "visao_local",
            "Visão local (descrever imagens de personagem)",
            "7.1",
            3,
            (
                INDISPONIVEL,
                "Nenhum modelo de visão está instalado, então a imagem enviada não é descrita sozinha: escreva a descrição "
                "do personagem no formulário.",
                None,
            ),
        ),
        item(
            "imagem",
            "Gerar imagens (personagens, cenários, objetos)",
            "7.1, 7.2",
            3,
            por_perfil(
                (DISPONIVEL, "GPU dedicada: segundos por imagem.", eta_img),
                (DISPONIVEL, "GPU dedicada com modelos quantizados.", eta_img or "segundos a ~1 min por imagem"),
                (LENTA, "Sem GPU dedicada: minutos por imagem (512 px, 4 passos).", eta_img or "2 a 8 min por imagem"),
                pesada_d,
            ),
            medido=img_medido,
        ),
        item(
            "variacoes_folha",
            "Variações e folha de referência de personagem",
            "7.1",
            3,
            por_perfil(
                (DISPONIVEL, "GPU dedicada.", None),
                (DISPONIVEL, "GPU dedicada.", None),
                (
                    LENTA,
                    "4 variações + ~6 poses são ~10 imagens: deixe rodar à noite.",
                    eta_personagem(medicoes) or "30 a 60 min por personagem",
                ),
                pesada_d,
            ),
        ),
        item(
            "recorte",
            "Recorte de fundo (PNG transparente)",
            "7.1",
            3,
            por_perfil(
                (DISPONIVEL, "Segmentação leve (BiRefNet).", eta_rec),
                (DISPONIVEL, "Segmentação leve (BiRefNet).", eta_rec),
                (DISPONIVEL, "Segmentação leve em ONNX na CPU.", eta_rec or "5 a 20 s por imagem"),
                pesada_d,
            ),
            medido=rec_medido,
        ),
        item(
            "consistencia_camadas",
            "Consistência por composição de camadas",
            "3.1",
            4,
            por_perfil(
                (DISPONIVEL, "Personagens em PNG transparente sobre cenários.", None),
                (DISPONIVEL, "Personagens em PNG transparente sobre cenários.", None),
                (DISPONIVEL, "O caminho recomendado aqui: não usa difusão por cena.", None),
                pesada_d,
            ),
        ),
        item(
            "consistencia_referencia",
            "Consistência por imagem de referência (difusão)",
            "3.1",
            4,
            por_perfil(
                (DISPONIVEL, "Modelo de edição com referência na GPU.", None),
                (DISPONIVEL, "Modelo de edição com referência quantizado.", None),
                (
                    LENTA,
                    "Difusão com referência: minutos por imagem; ideal para poses novas, à noite.",
                    "4 a 16 min por imagem",
                ),
                pesada_d,
            ),
        ),
        item(
            "voz",
            "Voz de personagens e narração (TTS)",
            "7.8",
            5,
            por_perfil(
                (DISPONIVEL, "Kokoro roda mais rápido que o tempo real.", eta_voz_txt),
                (DISPONIVEL, "Kokoro roda mais rápido que o tempo real.", eta_voz_txt),
                (
                    DISPONIVEL,
                    "Kokoro roda mais rápido que o tempo real, mesmo na CPU."
                    if voz_rapida
                    else "Kokoro roda mais devagar que o tempo real neste computador.",
                    eta_voz_txt or "6 a 20 s por minuto de fala",
                ),
                pesada_d,
            ),
            medido=voz_medida,
        ),
        item(
            "voz_propria",
            "Voz própria (clonagem)",
            "7.8",
            5,
            (
                INDISPONIVEL,
                "Ainda não disponível nesta versão: as vozes dos personagens vêm do Kokoro (3 em português e 4 em inglês).",
                None,
            ),
        ),
        item(
            "musica",
            "Música original instrumental",
            "7.8",
            5,
            (
                DISPONIVEL,
                "Melodia infantil original gerada por código (marimba, violão e chocalho), em qualquer computador.",
                "segundos por música",
            ),
        ),
        item(
            "musica_cantada",
            "Música com letra cantada",
            "7.8",
            5,
            (
                INDISPONIVEL,
                "Cantar a letra pede o ACE-Step, que não está instalado nesta versão. A música é instrumental e a letra vai "
                "como legenda.",
                None,
            ),
        ),
        item(
            "efeitos_legendas",
            "Efeitos sonoros, mixagem e legendas",
            "7.8",
            5,
            (DISPONIVEL, "Efeitos gerados por código, mixagem com ducking e legendas SRT sincronizadas.", None),
        ),
        item("animacao_cena", "Animação de cena (por código)", "3.2", 6, animacao_cena),
        item("animacao_ia", "Animação por IA (image-to-video)", "3.2", 6, ia_clipe),
        item(
            "clipe_rapido",
            "Clipe rápido (personagem + prompt curto)",
            "7.3",
            6,
            pesada_d
            if p == "D"
            else com_ffmpeg(
                por_perfil(
                    (DISPONIVEL, "Cenário gerado por IA e personagem animado por código.", "menos de 1 min por clipe"),
                    (DISPONIVEL, "Cenário gerado por IA e personagem animado por código.", "cerca de 1 min por clipe"),
                    (LENTA, "Cenário gerado por IA (a parte lenta) e personagem animado por código.", eta_clipe),
                    pesada_d,
                )
            ),
        ),
        item(
            "montagem",
            "Montagem, exportação e formatos (ffmpeg)",
            "7.5, 7.6, 7.10",
            7,
            com_ffmpeg((DISPONIVEL, "Encode H.264, união de clipes, outras resoluções e legendas.", None)),
        ),
        item(
            "portabilidade",
            "Exportar e importar projeto (.fabulim)",
            "2.7",
            7,
            (DISPONIVEL, "Pacote zip com enredo, roteiro, personagens e aprovações, sem os pesos dos modelos.", None),
        ),
        item(
            "continuar",
            "Continuar a partir de um vídeo",
            "7.7",
            8,
            animacao_cena
            if p == "D"
            else com_ffmpeg(
                (
                    DISPONIVEL,
                    "Continua a partir do último quadro"
                    + ("; cenas por código (o modo IA fica indisponível)." if p in ("C", "D") else "."),
                    None,
                )
            ),
        ),
        item(
            "fila_noturna",
            "Fila persistente e fila noturna",
            "7.9",
            1,
            (DISPONIVEL, "A fila sobrevive a reinícios; a fila noturna renderiza o que já foi aprovado.", None),
        ),
    ]
    if motores is None:
        return capacidades
    # o computador pode até dar conta, mas sem o motor instalado a funcionalidade não roda: diz onde instalar
    precisa = {
        "imagem": "imagem",
        "clipe_rapido": "imagem",
        "variacoes_folha": "imagem",
        "consistencia_referencia": "imagem",
        "recorte": "recorte",
        "voz": "voz",
    }

    def sem_motor(cap: Capacidade) -> Capacidade:
        if precisa.get(cap.id) and precisa[cap.id] not in motores:
            motivo = "Ainda não instalado: abra Modelos e clique em Instalar."
        else:
            return cap
        return replace(cap, estado=INDISPONIVEL, motivo=motivo, eta=None, eta_medido=False)

    return [sem_motor(cap) for cap in capacidades]
