"""Os dados de uma cena (roteiro, imagem, clipe, aprovações) e as regras de o que uma edição invalida."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from ..animacao.camera import MOVIMENTOS_DE_CAMERA
from ..animacao.presets import ACOES, ENTRADAS

Enquadramento = Literal["aberto", "medio", "proximo"]
Emocao = Literal["neutro", "feliz", "triste", "surpreso", "sono", "bravo"]
ETAPAS_DA_CENA = ("roteiro", "storyboard", "animacao")
DURACAO_MINIMA = 3.0
DURACAO_MAXIMA = 8.0


class FalaDaCena(BaseModel):
    character_id: str | None = None  # None: fala o narrador
    text: str = Field(default="", max_length=400)


class ImagemDaCena(BaseModel):
    media_id: str
    seed: int | None = None
    prompt: str = ""
    quality: str = "padrao"


class ClipeDaCena(BaseModel):
    media_id: str
    render_hash: str
    quality: str = "final"
    duration_s: float = 0.0


class DadosDaCena(BaseModel):
    title: str = Field(default="", max_length=120)
    duration_s: float = Field(default=6.0, ge=2.0, le=20.0)
    visual: str = Field(default="", max_length=600)
    action: str = Field(default="", max_length=400)
    setting: str = Field(default="", max_length=200)
    framing: Enquadramento = "medio"
    emotion: Emocao = "neutro"
    characters: list[str] = Field(default_factory=list, max_length=8)
    narration: str = Field(default="", max_length=600)
    dialogue: list[FalaDaCena] = Field(default_factory=list, max_length=12)
    lyrics: str = Field(default="", max_length=600)
    sfx: list[str] = Field(default_factory=list, max_length=6)
    camera: str = "parada"
    suggestion: bool = False
    suggestion_notes: str = Field(default="", max_length=400)
    layout: list[dict[str, Any]] | None = None
    background: ImagemDaCena | None = None
    candidates: list[str] = Field(default_factory=list, max_length=12)
    keyframe_media_id: str | None = None
    clip: ClipeDaCena | None = None
    timeline: dict[str, Any] | None = None  # quando cada fala começa e quanto a cena dura (calculado na animação)
    approved: dict[str, bool] = Field(default_factory=dict)
    # variante de formato: a semente do cenário do vídeo original, para o novo cenário sair no mesmo estilo e nas mesmas cores
    seed_hint: int | None = Field(default=None, ge=0, lt=2**31 - 1)

    def validar_camera(self) -> None:
        if self.camera not in MOVIMENTOS_DE_CAMERA:
            raise ValueError(f"câmera desconhecida: {self.camera}")

    def falas(self) -> list[FalaDaCena]:
        """Todas as falas da cena na ordem em que acontecem: a narração primeiro e depois os diálogos."""
        narracao = [FalaDaCena(character_id=None, text=self.narration)] if self.narration.strip() else []
        return [*narracao, *[f for f in self.dialogue if f.text.strip()]]


# O que cada edição invalida. Editar a narração não pede outro cenário, mas editar o cenário refaz tudo dali para a frente.
CAMPOS_DO_CENARIO = {"visual", "setting", "framing", "characters", "layout", "emotion"}
CAMPOS_DO_MOVIMENTO = {"narration", "dialogue", "lyrics", "sfx", "duration_s", "action", "camera", "title"}
CAMPOS_DE_CONTROLE = {"background", "candidates", "keyframe_media_id", "clip", "timeline", "approved", "seed_hint"}


def cena_valida(dados: dict[str, Any]) -> DadosDaCena:
    """Valida os dados de uma cena (levanta ``ValueError`` com uma mensagem que cabe na tela)."""
    try:
        cena = DadosDaCena.model_validate(dados)
    except ValidationError as exc:
        primeiro = exc.errors()[0]
        campo = ".".join(str(p) for p in primeiro["loc"])
        raise ValueError(f"Cena inválida no campo «{campo}»: {primeiro['msg']}") from exc
    cena.validar_camera()
    return cena


def aplicar_edicao(atual: dict[str, Any], mudancas: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    """Junta as mudanças aos dados da cena e devolve (novos dados, campos que de fato mudaram).

    Mudou o cenário: perde a aprovação do storyboard e da animação; mudou o texto ou o movimento: perde a da animação. O
    roteiro sempre volta a pedir aprovação quando algo do roteiro muda.
    """
    permitidos = set(DadosDaCena.model_fields) - CAMPOS_DE_CONTROLE
    desconhecidos = set(mudancas) - permitidos
    if desconhecidos:
        raise ValueError(f"campo de cena desconhecido: {', '.join(sorted(desconhecidos))}")
    novos = {**atual, **mudancas}
    mudou = {campo for campo in mudancas if atual.get(campo) != mudancas[campo]}
    aprovadas = dict(atual.get("approved", {}))
    if mudou & (CAMPOS_DO_CENARIO | CAMPOS_DO_MOVIMENTO):
        aprovadas["roteiro"] = False
        aprovadas["animacao"] = False
    if mudou & CAMPOS_DO_CENARIO:
        aprovadas["storyboard"] = False
    novos["approved"] = aprovadas
    valida = cena_valida(novos)
    return valida.model_dump(), mudou


def opcoes_de_animacao() -> dict[str, list[str]]:
    return {"actions": sorted(ACOES), "entrances": list(ENTRADAS), "cameras": list(MOVIMENTOS_DE_CAMERA)}
