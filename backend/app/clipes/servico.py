"""Clipes enviados e continuação de vídeo: validar o arquivo de verdade, extrair o último quadro e preparar o novo projeto."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..animacao.layout import ItemDeLayout
from ..erros import ErroParaOUsuario
from ..midias.repositorio import Midia
from ..midias.servico import adotar_e_avisar
from ..motores.contexto import ContextoSincrono
from ..motores.ffmpeg import Sonda
from ..motores.tipos import MotorFalhou
from ..projetos.cenas import DadosDaCena, ImagemDaCena
from ..projetos.repositorio import Projeto
from ..projetos.servico import DURACAO_PADRAO_S
from ..prompts.formatos import FichaEnredo
from ..prompts.parser import detectar_tipo, interpretar_estruturado

if TYPE_CHECKING:
    from ..container import Servicos

MAXIMO_DE_BYTES = 1024 * 1024 * 1024
DURACAO_MAXIMA_S = 1800.0
PAPEIS_DA_BIBLIOTECA = ("clipe_rapido", "clipe_enviado", "clipe_unido", "clipe_reenquadrado", "video_final")
DURACAO_DA_LIGACAO_S = 3.0


def extensao_do_container(sonda: Sonda) -> str:
    """A extensão certa pelo conteúdo real do arquivo (a extensão do nome enviado não vale como prova)."""
    formato = sonda.formato.lower()
    if "mp4" in formato or "mov" in formato:
        return "mp4"
    if "webm" in formato and sonda.codec_de_video in ("vp8", "vp9", "av1"):
        return "webm"
    raise ErroParaOUsuario("Formato de vídeo não suportado. Envie um arquivo MP4, MOV ou WebM.")


def validar_video_enviado(sv: Servicos, arquivo: Path) -> tuple[Sonda, str]:
    """Confere com o ffprobe que o arquivo é um vídeo de verdade e dentro dos limites. Devolve (sonda, extensão)."""
    try:
        sonda = sv.motores.ffmpeg.sondar(arquivo)
    except MotorFalhou as exc:
        raise ErroParaOUsuario(str(exc)) from exc
    if not sonda.tem_video or not sonda.largura or not sonda.altura:
        raise ErroParaOUsuario("O arquivo não tem imagem de vídeo.")
    if sonda.largura < 64 or sonda.altura < 64 or sonda.largura > 7680 or sonda.altura > 7680:
        raise ErroParaOUsuario("O tamanho do vídeo não é suportado (de 64 a 7680 pixels por lado).")
    if not 0.2 <= sonda.duracao_s <= DURACAO_MAXIMA_S:
        raise ErroParaOUsuario("A duração do vídeo precisa ficar entre 0,2 segundo e 30 minutos.")
    return sonda, extensao_do_container(sonda)


def quadro_do_video(
    sv: Servicos, video: Path, destino: Path, *, do_fim: bool = False, em_s: float = 0.5
) -> Path | None:
    """Um quadro do vídeo (o último, se ``do_fim``) como imagem; ``None`` se não deu."""
    posicao = ["-sseof", "-0.15"] if do_fim else ["-ss", f"{em_s:.2f}"]
    try:
        sv.motores.ffmpeg.rodar(
            ContextoSincrono(),
            [*posicao, "-i", video.resolve(), "-frames:v", "1", "-update", "1", "-q:v", "2", destino.resolve()],
            timeout=120,
        )
    except MotorFalhou:
        return None
    return destino if destino.is_file() else None


# --- continuar a partir de um vídeo -------------------------------------------------------------------------------------------
def _projeto_de_origem(sv: Servicos, midia: Midia) -> Projeto | None:
    id_ = midia.metadados.get("project_id")
    return sv.projetos.obter(str(id_)) if id_ else None


def _copiar_cenario(sv: Servicos, origem_id: str | None, projeto_id: str) -> Midia | None:
    if not origem_id:
        return None
    original = sv.midias.obter(origem_id)
    if original is None or not sv.midias.caminho_absoluto(original).is_file():
        return None
    return adotar_e_avisar(
        sv,
        sv.midias.caminho_absoluto(original),
        tipo="imagem",
        papel="fundo_ligacao",
        extensao=original.formato or "png",
        mover=False,
        dono_tipo="projeto",
        dono_id=projeto_id,
        prompt=original.prompt,
        estilo=original.estilo,
        seed=original.seed,
        modelo=original.modelo,
        metadados={"copied_from": original.id, "project_id": projeto_id},
    )


def _ligacao_do_projeto_de_origem(sv: Servicos, origem: Projeto) -> tuple[dict[str, Any], str | None] | None:
    """A última cena de um vídeo feito no app: os mesmos personagens, no mesmo lugar, sobre o mesmo cenário."""
    cenas = sv.projetos.cenas(origem.id)
    if not cenas:
        return None
    dados = DadosDaCena.model_validate(cenas[-1].dados)
    if dados.background is None:
        return None
    return dados.model_dump(), dados.background.media_id


def preparar_ligacao(
    sv: Servicos, midia: Midia, projeto: Projeto, ultimo_quadro: Path, descricao: str
) -> dict[str, Any]:
    """A cena de ligação: começa igual ao último quadro do vídeo original, para a junção ficar imperceptível."""
    base: dict[str, Any] = {
        "title": "Ligação com o vídeo anterior",
        "duration_s": DURACAO_DA_LIGACAO_S,
        "visual": descricao or "o final do vídeo anterior",
        "camera": "parada",
        "emotion": "neutro",
    }
    origem = _projeto_de_origem(sv, midia)
    fundo: Midia | None = None
    if origem is not None and (ligacao := _ligacao_do_projeto_de_origem(sv, origem)):
        dados, fundo_id = ligacao
        fundo = _copiar_cenario(sv, fundo_id, projeto.id)
        if fundo is not None:
            base["characters"] = dados["characters"]
            base["emotion"] = dados["emotion"]
            base["framing"] = dados["framing"]
            base["camera"] = "parada"
            layout = [ItemDeLayout.de_dict(i) for i in (dados.get("layout") or [])]
            base["layout"] = [{**i.para_dict(), "entrada": "nenhuma"} for i in layout] or None
            base["action"] = dados.get("action", "")
    elif midia.papel == "clipe_rapido" and midia.metadados.get("background_media_id"):
        fundo = _copiar_cenario(sv, str(midia.metadados["background_media_id"]), projeto.id)
        if fundo is not None:
            personagem_id = str(midia.metadados.get("character_id") or "")
            base["characters"] = [personagem_id] if personagem_id else []
            base["emotion"] = str(midia.metadados.get("emotion") or "neutro")
            itens = midia.metadados.get("layout") or []
            base["layout"] = [{**ItemDeLayout.de_dict(i).para_dict(), "entrada": "nenhuma"} for i in itens] or None
    if fundo is None:  # vídeo de fora ou sem dados: o último quadro vira o cenário (sem personagens por cima)
        fundo = adotar_e_avisar(
            sv,
            ultimo_quadro,
            tipo="imagem",
            papel="fundo_ligacao",
            extensao="jpg",
            mover=False,
            dono_tipo="projeto",
            dono_id=projeto.id,
            metadados={"project_id": projeto.id, "last_frame_of": midia.id},
        )
    base["background"] = ImagemDaCena(
        media_id=fundo.id, seed=fundo.seed, prompt=descricao or "último quadro do vídeo anterior"
    ).model_dump()
    base["candidates"] = [fundo.id]
    return DadosDaCena.model_validate(base).model_dump()


def ficha_da_continuacao(
    prompt: str, titulo: str, formato: str, idioma: str, estilo: str, nomes: list[str]
) -> FichaEnredo:
    """O texto da continuação vira a ficha do enredo: no formato estruturado (### ENREDO) ou como história livre."""
    if detectar_tipo(prompt) == "enredo":
        ficha = interpretar_estruturado(prompt, "enredo").ficha
        assert isinstance(ficha, FichaEnredo)
        return ficha.model_copy(
            update={"title": titulo or ficha.title, "format": formato, "language": idioma, "style": estilo}
        )
    return FichaEnredo.model_validate(
        {
            "title": titulo,
            "story": prompt.strip(),
            "format": formato,
            "language": idioma,
            "style": estilo,
            "characters": nomes,
        }
    )


def formato_pelo_video(sonda: Sonda) -> str:
    return "short" if (sonda.altura or 0) > (sonda.largura or 0) else "longo"


def duracao_padrao_da_continuacao(formato: str) -> int:
    return int(DURACAO_PADRAO_S[formato] * (2 / 3))
