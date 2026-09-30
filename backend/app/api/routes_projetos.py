"""Projetos de vídeo: enredo, cenas com aprovação por etapa e versões, e os jobs de cada etapa (roteiro → storyboard → animação
→ áudio → montagem)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from ..animacao.camera import DESCRICAO_DA_CAMERA
from ..animacao.layout import ItemDeLayout
from ..animacao.presets import DESCRICAO_DAS_ACOES, ENTRADAS
from ..audio.musica import ESTILOS
from ..conteudo.filtro import verificar_campos, verificar_texto
from ..erros import ErroParaOUsuario
from ..jobs.models import ATIVOS, Job
from ..jobs.servico import enfileirar
from ..midias.servico import remover_e_avisar
from ..motores.voz import VOZES
from ..personagens.servico import voz_valida
from ..projetos import etapas, noturna, servico, variantes
from ..projetos.cenas import DadosDaCena, aplicar_edicao, cena_valida, opcoes_de_animacao
from ..projetos.estado import dados_atuais
from ..projetos.metadados import validar_metadados
from ..projetos.montagem import TRANSICOES
from ..projetos.pedidos import (
    ParametrosDeAnimacao,
    ParametrosDeAudio,
    ParametrosDeMetadados,
    ParametrosDeMiniaturas,
    ParametrosDeMontagem,
    ParametrosDeVersaoEmOutroIdioma,
    ParametrosDoRoteiro,
    ParametrosDoStoryboard,
    PedidoDaNoite,
    PedidoDeAnimacao,
    PedidoDeAprovacao,
    PedidoDeAprovacaoDaEtapa,
    PedidoDeAudio,
    PedidoDeEdicaoDeCena,
    PedidoDeEdicaoDoProjeto,
    PedidoDeEscolhaDeCenario,
    PedidoDeMetadados,
    PedidoDeMetadadosEditados,
    PedidoDeMiniaturas,
    PedidoDeMontagem,
    PedidoDeNovaCena,
    PedidoDeProjeto,
    PedidoDeReordenacao,
    PedidoDeVariante,
    PedidoDeVersao,
    PedidoDeVersaoEmOutroIdioma,
    PedidoDoRoteiro,
    PedidoDoStoryboard,
)
from ..projetos.pipeline import layout_da_cena, personagens_do_projeto
from ..projetos.qualidade import checklist
from ..projetos.repositorio import ETAPAS, Cena, Projeto
from ..projetos.roteiro import achar_personagem
from ..projetos.traducao import NOME_DO_IDIOMA as NOME_DO_IDIOMA_POR_EXTENSO
from ..prompts.formatos import FichaEnredo
from ..tarefas.projetos import recompor_capa_da_cena
from .deps import ServicosDep

router = APIRouter(prefix="/api/projects")

IdProjeto = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]
IdCena = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]
ETAPAS_DE_CENA = ("roteiro", "storyboard", "animacao")
CHAVES_DE_AJUSTE = {"fps", "transition", "narrator", "voices"}
CHAVES_DA_HISTORIA = {"title", "story", "theme", "settings", "music", "notes", "target_duration"}


def _achar(sv: ServicosDep, id_: str) -> Projeto:
    projeto = sv.projetos.obter(id_)
    if projeto is None:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return projeto


def _cena(sv: ServicosDep, projeto: Projeto, id_: str) -> Cena:
    cena = sv.projetos.cena(id_)
    if cena is None or cena.projeto_id != projeto.id:
        raise HTTPException(status_code=404, detail="Cena não encontrada")
    return cena


def _exigir(sv: ServicosDep, *motores: str) -> None:
    if motivo := sv.motores.motivo(*motores):
        raise HTTPException(status_code=503, detail=motivo)


def _unico(sv: ServicosDep, tipo: str, parametros: dict[str, Any], titulo: str) -> Job:
    """Um job de cada tipo por projeto por vez: pedir de novo enquanto o primeiro roda devolve o mesmo job."""
    for job in sv.store.listar(ATIVOS):
        if job.kind == tipo and job.params.get("project_id") == parametros["project_id"]:
            return job
    return enfileirar(sv, tipo, parametros, titulo=titulo)


def _validar_ids_de_personagens(sv: ServicosDep, ids: list[str]) -> list[str]:
    unicos = list(dict.fromkeys(ids))
    for id_ in unicos:
        if sv.personagens.obter(id_) is None:
            raise HTTPException(status_code=422, detail="Um dos personagens escolhidos não existe mais na biblioteca.")
    return unicos


def _validar_ajustes(ajustes: dict[str, Any]) -> dict[str, Any]:
    desconhecidos = set(ajustes) - CHAVES_DE_AJUSTE
    if desconhecidos:
        raise HTTPException(status_code=422, detail=f"Ajuste desconhecido: {', '.join(sorted(desconhecidos))}")
    limpos: dict[str, Any] = {}
    try:
        if "fps" in ajustes:
            fps = int(ajustes["fps"])
            if not 12 <= fps <= 60:
                raise ValueError("Os quadros por segundo ficam entre 12 e 60.")
            limpos["fps"] = fps
        if "transition" in ajustes:
            if ajustes["transition"] not in TRANSICOES:
                raise ValueError("Transição desconhecida.")
            limpos["transition"] = ajustes["transition"]
        if "narrator" in ajustes:
            limpos["narrator"] = voz_valida(dict(ajustes["narrator"]))
        if "voices" in ajustes:
            limpos["voices"] = {str(k): voz_valida(dict(v)) for k, v in dict(ajustes["voices"]).items()}
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc) or "Ajuste inválido.") from exc
    return limpos


def _validar_musica(musica: dict[str, Any]) -> dict[str, Any]:
    limpa: dict[str, Any] = {}
    if "enabled" in musica:
        limpa["enabled"] = bool(musica["enabled"])
    if "style" in musica:
        if musica["style"] not in ESTILOS:
            raise HTTPException(status_code=422, detail="Estilo de música desconhecido.")
        limpa["style"] = musica["style"]
    if "seed" in musica:
        try:
            limpa["seed"] = int(musica["seed"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="A semente da música precisa ser um número.") from exc
    if "volume" in musica:
        try:
            limpa["volume"] = min(max(float(musica["volume"]), 0.0), 0.6)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="O volume da música precisa ser um número.") from exc
    return limpa


@router.get("/options")
def opcoes() -> dict[str, Any]:
    return {
        **opcoes_de_animacao(),
        "action_labels": DESCRICAO_DAS_ACOES,
        "camera_labels": DESCRICAO_DA_CAMERA,
        "music_styles": [{"id": e.nome, "label": e.descricao, "bpm": e.bpm} for e in ESTILOS.values()],
        "transitions": [{"id": nome, "seconds": TRANSICOES[nome][1]} for nome in TRANSICOES],
        "voices": VOZES,
        "entrances": list(ENTRADAS),
    }


@router.get("/night-plan")
def plano_da_noite(sv: ServicosDep) -> dict[str, Any]:
    """O que a fila noturna faria agora: para cada projeto, o próximo trabalho pesado que as aprovações já liberaram."""
    return {"items": [item.para_api() for item in noturna.plano_da_noite(sv)]}


@router.post("/night-queue", status_code=202)
def fila_noturna(pedido: PedidoDaNoite, sv: ServicosDep) -> dict[str, Any]:
    """Enfileira o que a noite vai renderizar (cenários, animação, áudio ou montagem), sem aprovar nada por conta própria."""
    jobs, ignorados = noturna.enfileirar_a_noite(sv, pedido.project_ids)
    return {"queued": [j.model_dump(mode="json") for j in jobs], "skipped": [i.para_api() for i in ignorados]}


@router.get("")
def listar(sv: ServicosDep) -> dict[str, Any]:
    projetos = sv.projetos.listar()
    return {"items": [servico.resumo(sv, p) for p in projetos], "total": len(projetos)}


@router.post("", status_code=201)
def criar(pedido: PedidoDeProjeto, sv: ServicosDep) -> dict[str, Any]:
    ficha = pedido.form
    if not ficha.story.strip():
        raise HTTPException(status_code=422, detail="Escreva a história: o que acontece do começo ao fim.")
    reprovacao = verificar_campos(ficha.model_dump()) or verificar_texto(pedido.original_prompt)
    if reprovacao:
        raise HTTPException(status_code=422, detail=reprovacao.motivo)
    ids = _validar_ids_de_personagens(sv, pedido.character_ids)
    faltando: list[str] = []
    todos = sv.personagens.listar(limite=1000)
    for nome in ficha.characters:
        achado = achar_personagem(nome, [p for p in todos if p.estilo == ficha.style] or todos)
        if achado is None:
            faltando.append(nome)
        elif achado.id not in ids:
            ids.append(achado.id)
    limite = 60 if ficha.format == "short" else 300  # Short até 60 s, vídeo longo até 5 min
    duracao = min(
        pedido.target_duration_s or servico.duracao_alvo_em_segundos(ficha.target_duration, ficha.format), limite
    )
    projeto = sv.projetos.criar(
        ficha.title.strip() or "Meu vídeo",
        ficha.format,
        ficha.language,
        ficha.style,
        duracao,
        {**ficha.model_dump(), "original_prompt": pedido.original_prompt},
        ids,
    )
    personagens = personagens_do_projeto(sv, projeto)
    return {
        "project": projeto.para_api(),
        "missing_characters": faltando,
        "style_warnings": servico.avisos_de_estilo(projeto, personagens),
    }


@router.get("/{id_}")
def detalhes(id_: IdProjeto, sv: ServicosDep) -> dict[str, Any]:
    return servico.detalhes(sv, _achar(sv, id_))


@router.patch("/{id_}")
def editar(id_: IdProjeto, pedido: PedidoDeEdicaoDoProjeto, sv: ServicosDep) -> dict[str, Any]:
    projeto = _achar(sv, id_)
    campos: dict[str, Any] = {}
    reabrir: str | None = None
    if pedido.title is not None:
        campos["titulo"] = pedido.title.strip()
    if pedido.target_duration_s is not None:
        limite = 60 if projeto.formato == "short" else 300
        campos["duracao_alvo_s"] = min(pedido.target_duration_s, limite)
    if pedido.character_ids is not None:
        campos["personagens"] = _validar_ids_de_personagens(sv, pedido.character_ids)
    if pedido.music is not None:
        campos["musica"] = {**projeto.musica, **_validar_musica(pedido.music)}
        reabrir = "audio"
    if pedido.settings is not None:
        novos = _validar_ajustes(pedido.settings)
        campos["configuracoes"] = {**projeto.configuracoes, **novos}
        if "fps" in novos and novos["fps"] != projeto.configuracoes.get("fps"):
            reabrir = "animacao"
        elif novos and reabrir is None:
            reabrir = "audio"
    if pedido.story is not None:
        estranhos = set(pedido.story) - CHAVES_DA_HISTORIA
        if estranhos:
            raise HTTPException(
                status_code=422, detail=f"Campo da história desconhecido: {', '.join(sorted(estranhos))}"
            )
        novo_enredo = {**projeto.enredo, **pedido.story}
        ficha = FichaEnredo.model_validate(novo_enredo)
        if reprovacao := verificar_campos(ficha.model_dump()):
            raise HTTPException(status_code=422, detail=reprovacao.motivo)
        if not ficha.story.strip():
            raise HTTPException(status_code=422, detail="A história não pode ficar vazia.")
        campos["enredo"] = {**novo_enredo, "original_prompt": projeto.enredo.get("original_prompt", "")}
        if ficha.story != projeto.enredo.get("story"):
            reabrir = "enredo"
    novo = sv.projetos.atualizar(projeto.id, **campos) if campos else projeto
    assert novo is not None
    if reabrir and any(novo.aprovacoes.get(e) for e in ETAPAS[ETAPAS.index(reabrir) :]):
        novo = etapas.reabrir_a_partir(sv, novo, reabrir)
    return servico.detalhes(sv, novo)


@router.delete("/{id_}")
def apagar(id_: IdProjeto, sv: ServicosDep) -> dict[str, Any]:
    projeto = _achar(sv, id_)
    removidas = 0
    for cena in sv.projetos.cenas(projeto.id):
        removidas += sv.midias.remover_do_dono("cena", cena.id)
    removidas += sv.midias.remover_do_dono("projeto", projeto.id)
    for variante in sv.projetos.variantes_de(projeto.id):  # as variantes continuam, só perdem a ligação com este
        sv.projetos.atualizar(variante.id, configuracoes={**variante.configuracoes, "origin_deleted": True})
    sv.projetos.remover(projeto.id)
    return {"deleted": True, "media_removed": removidas}


# --- etapas --------------------------------------------------------------------------------------------------------------------
@router.post("/{id_}/stages/{etapa}/approve")
def aprovar_etapa(id_: IdProjeto, etapa: str, pedido: PedidoDeAprovacaoDaEtapa, sv: ServicosDep) -> dict[str, Any]:
    projeto = _achar(sv, id_)
    if etapa not in ETAPAS:
        raise HTTPException(status_code=404, detail="Etapa desconhecida")
    novo = etapas.aprovar_etapa(sv, projeto, etapa, pedido.approve_all)
    return servico.detalhes(sv, novo)


@router.post("/{id_}/stages/{etapa}/reopen")
def reabrir_etapa(id_: IdProjeto, etapa: str, sv: ServicosDep) -> dict[str, Any]:
    projeto = _achar(sv, id_)
    if etapa not in ETAPAS:
        raise HTTPException(status_code=404, detail="Etapa desconhecida")
    return servico.detalhes(sv, etapas.reabrir_a_partir(sv, projeto, etapa))


# --- jobs de cada etapa ----------------------------------------------------------------------------------------------------------
@router.post("/{id_}/script", response_model=Job, status_code=202)
def gerar_roteiro(id_: IdProjeto, pedido: PedidoDoRoteiro, sv: ServicosDep) -> Job:
    projeto = _achar(sv, id_)
    etapas.exigir_etapa_aprovada(projeto, "enredo", "gerar o roteiro")
    if pedido.mode == "ia":
        _exigir(sv, "text")
    parametros = ParametrosDoRoteiro(project_id=projeto.id, mode=pedido.mode)
    return _unico(sv, "projeto.roteiro", parametros.model_dump(mode="json"), f"Roteiro de «{projeto.titulo}»")


def _conferir_recortes(sv: ServicosDep, projeto: Projeto, cenas: list[Cena]) -> None:
    """Todo personagem de uma cena precisa ter o PNG transparente: avisa já, antes de gastar minutos de geração."""
    from ..projetos.pipeline import escolher_recorte

    personagens = {p.id: p for p in personagens_do_projeto(sv, projeto)}
    for cena in cenas:
        dados = DadosDaCena.model_validate(cena.dados)
        for item in layout_da_cena(projeto, dados):
            personagem = personagens.get(item.personagem_id)
            if personagem is None:
                raise HTTPException(
                    status_code=409, detail=f"A cena {cena.ordem} usa um personagem que não está mais na biblioteca."
                )
            escolher_recorte(sv, personagem, dados.emotion, "respirar", item.pose)


@router.post("/{id_}/storyboard", response_model=Job, status_code=202)
def gerar_storyboard(id_: IdProjeto, pedido: PedidoDoStoryboard, sv: ServicosDep) -> Job:
    projeto = _achar(sv, id_)
    etapas.exigir_etapa_aprovada(projeto, "roteiro", "gerar o storyboard")
    _exigir(sv, "image")
    cenas = sv.projetos.cenas(projeto.id)
    if not cenas:
        raise HTTPException(status_code=409, detail="Este projeto ainda não tem cenas.")
    escolhidas = set(pedido.scene_ids or [])
    if escolhidas and not escolhidas <= {c.id for c in cenas}:
        raise HTTPException(status_code=422, detail="Uma das cenas escolhidas não é deste projeto.")
    _conferir_recortes(sv, projeto, [c for c in cenas if not escolhidas or c.id in escolhidas])
    parametros = ParametrosDoStoryboard(project_id=projeto.id, **pedido.model_dump())
    return _unico(sv, "projeto.storyboard", parametros.model_dump(mode="json"), f"Storyboard de «{projeto.titulo}»")


@router.post("/{id_}/animate", response_model=Job, status_code=202)
def animar(id_: IdProjeto, pedido: PedidoDeAnimacao, sv: ServicosDep) -> Job:
    projeto = _achar(sv, id_)
    etapas.exigir_etapa_aprovada(projeto, "storyboard", "animar as cenas")
    _exigir(sv, "voice", "ffmpeg")
    cenas = sv.projetos.cenas(projeto.id)
    escolhidas = set(pedido.scene_ids or [])
    if escolhidas and not escolhidas <= {c.id for c in cenas}:
        raise HTTPException(status_code=422, detail="Uma das cenas escolhidas não é deste projeto.")
    parametros = ParametrosDeAnimacao(project_id=projeto.id, **pedido.model_dump())
    return _unico(sv, "projeto.animar", parametros.model_dump(mode="json"), f"Animação de «{projeto.titulo}»")


@router.post("/{id_}/audio", response_model=Job, status_code=202)
def gerar_audio(id_: IdProjeto, pedido: PedidoDeAudio, sv: ServicosDep) -> Job:
    projeto = _achar(sv, id_)
    etapas.exigir_etapa_aprovada(projeto, "animacao", "montar o áudio")
    parametros = ParametrosDeAudio(project_id=projeto.id, **pedido.model_dump())
    return _unico(sv, "projeto.audio", parametros.model_dump(mode="json"), f"Áudio de «{projeto.titulo}»")


@router.post("/{id_}/assemble", response_model=Job, status_code=202)
def montar(id_: IdProjeto, pedido: PedidoDeMontagem, sv: ServicosDep) -> Job:
    projeto = _achar(sv, id_)
    etapas.exigir_etapa_aprovada(projeto, "audio", "montar o vídeo")
    _exigir(sv, "ffmpeg")
    parametros = ParametrosDeMontagem(project_id=projeto.id, **pedido.model_dump())
    return _unico(sv, "projeto.montar", parametros.model_dump(mode="json"), f"Montagem de «{projeto.titulo}»")


@router.get("/{id_}/review")
def revisar(id_: IdProjeto, sv: ServicosDep) -> dict[str, Any]:
    projeto = _achar(sv, id_)
    detalhes = servico.detalhes(sv, projeto)
    return {
        "checklist": checklist(sv, projeto),
        "files": detalhes["files"],
        "metadata": detalhes["metadata"],
        "quality": detalhes["quality"],
        "reminder": "Ao enviar ao YouTube, marque o vídeo como «conteúdo para crianças».",
    }


# --- entrega: miniaturas, título e tags, outro idioma e outro formato -------------------------------------------------------------
@router.post("/{id_}/thumbnails", response_model=Job, status_code=202)
def gerar_miniaturas(id_: IdProjeto, pedido: PedidoDeMiniaturas, sv: ServicosDep) -> Job:
    """Miniaturas 1280×720 com os personagens do vídeo sobre os cenários do storyboard (desenhadas por código, sem IA)."""
    projeto = _achar(sv, id_)
    cenas = sv.projetos.cenas(projeto.id)
    if not any(DadosDaCena.model_validate(c.dados).background for c in cenas):
        raise HTTPException(status_code=409, detail="Gere o storyboard antes: a miniatura usa os cenários das cenas.")
    if pedido.scene_ids and not set(pedido.scene_ids) <= {c.id for c in cenas}:
        raise HTTPException(status_code=422, detail="Uma das cenas escolhidas não é deste projeto.")
    if pedido.text and (reprovacao := verificar_texto(pedido.text)):
        raise HTTPException(status_code=422, detail=reprovacao.motivo)
    parametros = ParametrosDeMiniaturas(project_id=projeto.id, **pedido.model_dump())
    return _unico(sv, "projeto.miniaturas", parametros.model_dump(mode="json"), f"Miniaturas de «{projeto.titulo}»")


@router.delete("/{id_}/thumbnails/{mid}")
def apagar_miniatura(id_: IdProjeto, mid: IdCena, sv: ServicosDep) -> dict[str, bool]:
    projeto = _achar(sv, id_)
    midia = sv.midias.obter(mid)
    if midia is None or midia.papel != "thumbnail" or midia.dono_id != projeto.id:
        raise HTTPException(status_code=404, detail="Miniatura não encontrada")
    return {"deleted": remover_e_avisar(sv, mid)}


@router.post("/{id_}/metadata", response_model=Job, status_code=202)
def gerar_metadados(id_: IdProjeto, pedido: PedidoDeMetadados, sv: ServicosDep) -> Job:
    """Sugere título, descrição e tags em português e em inglês (o modelo local escreve; sem ele, um modelo pronto)."""
    projeto = _achar(sv, id_)
    if not sv.projetos.cenas(projeto.id):
        raise HTTPException(status_code=409, detail="Gere o roteiro antes: os textos partem da história e das cenas.")
    if pedido.mode == "ia":
        _exigir(sv, "text")
    parametros = ParametrosDeMetadados(project_id=projeto.id, **pedido.model_dump())
    return _unico(
        sv, "projeto.metadados", parametros.model_dump(mode="json"), f"Textos do YouTube de «{projeto.titulo}»"
    )


@router.put("/{id_}/metadata")
def salvar_metadados(id_: IdProjeto, pedido: PedidoDeMetadadosEditados, sv: ServicosDep) -> dict[str, Any]:
    """Guarda os textos como o usuário editou (títulos e tags dentro dos limites do YouTube, sem conteúdo proibido)."""
    projeto = _achar(sv, id_)
    try:
        novos = validar_metadados(pedido.texts, projeto.configuracoes.get("metadata"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    atualizado = sv.projetos.atualizar(
        projeto.id, configuracoes={**projeto.configuracoes, "metadata": {**novos, "source": "manual"}}
    )
    assert atualizado is not None
    return servico.detalhes(sv, atualizado)


@router.post("/{id_}/language-version", response_model=Job, status_code=202)
def versao_em_outro_idioma(id_: IdProjeto, pedido: PedidoDeVersaoEmOutroIdioma, sv: ServicosDep) -> Job:
    """Cria a versão em outro idioma (português ↔ inglês): mesmo visual, roteiro, falas e título traduzidos. O original não muda."""
    projeto = _achar(sv, id_)
    if not sv.projetos.cenas(projeto.id):
        raise HTTPException(status_code=409, detail="Gere o roteiro antes: a versão em outro idioma traduz as cenas.")
    destino = pedido.language or ("en" if projeto.idioma == "pt-BR" else "pt-BR")
    if destino == projeto.idioma:
        raise HTTPException(status_code=422, detail="O projeto já está nesse idioma.")
    if pedido.mode == "ia":
        _exigir(sv, "text")
    parametros = ParametrosDeVersaoEmOutroIdioma(project_id=projeto.id, **pedido.model_dump())
    nome = NOME_DO_IDIOMA_POR_EXTENSO[destino]
    return _unico(
        sv, "projeto.versao_idioma", parametros.model_dump(mode="json"), f"Versão em {nome} de «{projeto.titulo}»"
    )


@router.post("/{id_}/variant", status_code=201)
def criar_variante_de_formato(id_: IdProjeto, pedido: PedidoDeVariante, sv: ServicosDep) -> dict[str, Any]:
    """O mesmo vídeo em Short ou em vídeo longo: roteiro e personagens iguais; cenários e posições refeitos no novo formato."""
    projeto = _achar(sv, id_)
    novo, avisos = variantes.criar_variante_de_formato(sv, projeto, pedido.format)
    return {"project": novo.para_api(), "warnings": avisos}


# --- cenas --------------------------------------------------------------------------------------------------------------------------
def _sanear_layout(dados: dict[str, Any]) -> None:
    if dados.get("layout"):
        presentes = set(dados.get("characters", []))
        dados["layout"] = [
            ItemDeLayout.de_dict(i).para_dict() for i in dados["layout"] if i.get("personagem_id") in presentes
        ]


def _incluir_no_projeto(sv: ServicosDep, projeto: Projeto, ids: list[str]) -> Projeto:
    faltam = [i for i in ids if i not in projeto.personagens]
    if not faltam:
        return projeto
    novo = sv.projetos.atualizar(projeto.id, personagens=[*projeto.personagens, *faltam])
    assert novo is not None
    return novo


def _resposta_da_cena(sv: ServicosDep, projeto: Projeto, cena: Cena, aviso: str | None = None) -> dict[str, Any]:
    nomes = {p.id: p.nome for p in personagens_do_projeto(sv, projeto)}
    atual = sv.projetos.cena(cena.id) or cena
    return {
        "scene": servico.cena_para_api(sv, projeto, atual, nomes),
        "stages": etapas.situacao_das_etapas(sv.projetos.obter(projeto.id) or projeto, sv.projetos.cenas(projeto.id)),
        "warning": aviso,
    }


@router.post("/{id_}/scenes", status_code=201)
def criar_cena(id_: IdProjeto, pedido: PedidoDeNovaCena, sv: ServicosDep) -> dict[str, Any]:
    projeto = _achar(sv, id_)
    try:
        dados = cena_valida(pedido.data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    ids = _validar_ids_de_personagens(sv, dados.characters)
    projeto = _incluir_no_projeto(sv, projeto, ids)
    if reprovacao := verificar_campos(
        dados.model_dump(include={"title", "visual", "action", "setting", "narration", "lyrics"})
    ):
        raise HTTPException(status_code=422, detail=reprovacao.motivo)
    cena = sv.projetos.criar_cena(projeto.id, dados.model_dump(), pedido.position)
    novo = etapas.reabrir_a_partir(sv, projeto, "animacao") if projeto.aprovacoes.get("animacao") else projeto
    return _resposta_da_cena(sv, novo, cena)


@router.patch("/{id_}/scenes/{cid}")
def editar_cena(id_: IdProjeto, cid: IdCena, pedido: PedidoDeEdicaoDeCena, sv: ServicosDep) -> dict[str, Any]:
    projeto = _achar(sv, id_)
    cena = _cena(sv, projeto, cid)
    try:
        novos, mudou = aplicar_edicao(cena.dados, pedido.changes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not mudou:
        return _resposta_da_cena(sv, projeto, cena)
    if reprovacao := verificar_campos(
        {k: v for k, v in novos.items() if k in ("title", "visual", "action", "setting", "narration", "lyrics")}
    ) or verificar_campos({"dialogue": [f["text"] for f in novos.get("dialogue", [])]}):
        raise HTTPException(status_code=422, detail=reprovacao.motivo)
    ids = _validar_ids_de_personagens(sv, novos.get("characters", []))
    projeto = _incluir_no_projeto(sv, projeto, ids)
    _sanear_layout(novos)
    if "characters" in mudou and "layout" not in pedido.changes:
        novos["layout"] = None  # trocou quem está na cena: o layout volta ao automático
    atualizada = sv.projetos.atualizar_cena(cena.id, novos, "editada pelo usuário")
    assert atualizada is not None
    projeto = etapas.cascata_da_edicao(sv, projeto, mudou)
    aviso: str | None = None
    if mudou & {"characters", "layout", "framing", "emotion", "action"} and novos.get("background"):
        try:
            recompor_capa_da_cena(sv, projeto, cena.id)
        except ErroParaOUsuario as exc:
            aviso = str(exc)
    return _resposta_da_cena(sv, projeto, atualizada, aviso)


@router.delete("/{id_}/scenes/{cid}")
def apagar_cena(id_: IdProjeto, cid: IdCena, sv: ServicosDep) -> dict[str, Any]:
    projeto = _achar(sv, id_)
    cena = _cena(sv, projeto, cid)
    sv.midias.remover_do_dono("cena", cena.id)
    sv.projetos.remover_cena(cena.id)
    if projeto.aprovacoes.get("animacao"):
        projeto = etapas.reabrir_a_partir(sv, projeto, "animacao")
    return {"deleted": True, "stages": etapas.situacao_das_etapas(projeto, sv.projetos.cenas(projeto.id))}


@router.post("/{id_}/scenes/reorder")
def reordenar_cenas(id_: IdProjeto, pedido: PedidoDeReordenacao, sv: ServicosDep) -> dict[str, Any]:
    projeto = _achar(sv, id_)
    try:
        sv.projetos.reordenar_cenas(projeto.id, pedido.ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if projeto.aprovacoes.get("audio"):
        projeto = etapas.reabrir_a_partir(sv, projeto, "audio")
    return servico.detalhes(sv, projeto)


@router.post("/{id_}/scenes/{cid}/approve")
def aprovar_cena(id_: IdProjeto, cid: IdCena, pedido: PedidoDeAprovacao, sv: ServicosDep) -> dict[str, Any]:
    projeto = _achar(sv, id_)
    cena = _cena(sv, projeto, cid)
    dados = DadosDaCena.model_validate(cena.dados)
    if pedido.approved and pedido.stage == "storyboard" and dados.background is None:
        raise HTTPException(
            status_code=409, detail="Esta cena ainda não tem cenário: gere o storyboard antes de aprovar."
        )
    if pedido.approved and pedido.stage == "animacao" and dados.clip is None:
        raise HTTPException(status_code=409, detail="Esta cena ainda não tem clipe: anime antes de aprovar.")
    novos = dados.model_dump()
    novos["approved"] = {**dados.approved, pedido.stage: pedido.approved}
    sv.projetos.atualizar_cena_sem_versao(cena.id, novos)
    if not pedido.approved and projeto.aprovacoes.get(pedido.stage):
        projeto = etapas.reabrir_a_partir(sv, projeto, pedido.stage)
    return _resposta_da_cena(sv, projeto, cena)


@router.get("/{id_}/scenes/{cid}/versions")
def versoes(id_: IdProjeto, cid: IdCena, sv: ServicosDep) -> dict[str, Any]:
    projeto = _achar(sv, id_)
    cena = _cena(sv, projeto, cid)
    return {"versions": sv.projetos.versoes_da_cena(cena.id), "current": cena.versao}


@router.post("/{id_}/scenes/{cid}/restore")
def voltar_versao(id_: IdProjeto, cid: IdCena, pedido: PedidoDeVersao, sv: ServicosDep) -> dict[str, Any]:
    projeto = _achar(sv, id_)
    cena = _cena(sv, projeto, cid)
    restaurada = sv.projetos.restaurar_versao(cena.id, pedido.version)
    if restaurada is None:
        raise HTTPException(status_code=404, detail="Versão não encontrada")
    dados = _sanear_depois_de_voltar(sv, restaurada)
    sv.projetos.atualizar_cena_sem_versao(cena.id, dados)
    projeto = etapas.reabrir_a_partir(sv, projeto, "roteiro") if projeto.aprovacoes.get("roteiro") else projeto
    aviso: str | None = None
    if dados.get("background"):
        try:
            recompor_capa_da_cena(sv, projeto, cena.id)
        except ErroParaOUsuario as exc:
            aviso = str(exc)
    return _resposta_da_cena(sv, projeto, restaurada, aviso)


def _sanear_depois_de_voltar(sv: ServicosDep, cena: Cena) -> dict[str, Any]:
    """Ao voltar uma versão, o que aponta para mídia que já foi apagada é descartado e todas as aprovações voltam a ser pedidas."""
    dados = DadosDaCena.model_validate(cena.dados).model_dump()
    if dados["background"] and sv.midias.obter(dados["background"]["media_id"]) is None:
        dados["background"] = None
    if dados["clip"] and sv.midias.obter(dados["clip"]["media_id"]) is None:
        dados["clip"] = None
        dados["timeline"] = None
    if dados["keyframe_media_id"] and sv.midias.obter(dados["keyframe_media_id"]) is None:
        dados["keyframe_media_id"] = None
    dados["candidates"] = [c for c in dados["candidates"] if sv.midias.obter(c) is not None]
    dados["approved"] = {}
    return dados


@router.post("/{id_}/scenes/{cid}/choose-background")
def escolher_cenario(id_: IdProjeto, cid: IdCena, pedido: PedidoDeEscolhaDeCenario, sv: ServicosDep) -> dict[str, Any]:
    projeto = _achar(sv, id_)
    cena = _cena(sv, projeto, cid)
    midia = sv.midias.obter(pedido.media_id)
    dados = DadosDaCena.model_validate(cena.dados)
    if midia is None or midia.dono_id != cena.id or midia.papel != "fundo":
        raise HTTPException(status_code=422, detail="Escolha um dos cenários gerados para esta cena.")
    novos = dados.model_dump()
    novos["background"] = {
        "media_id": midia.id,
        "seed": midia.seed,
        "prompt": midia.prompt or "",
        "quality": str(midia.metadados.get("quality") or "padrao"),
    }
    novos["approved"] = {**dados.approved, "storyboard": False, "animacao": False}
    if midia.id not in novos["candidates"]:
        novos["candidates"] = [*novos["candidates"], midia.id]
    atualizada = sv.projetos.atualizar_cena(cena.id, novos, "cenário escolhido")
    assert atualizada is not None
    projeto = etapas.cascata_da_edicao(sv, projeto, {"visual"})
    recompor_capa_da_cena(sv, projeto, cena.id)
    return _resposta_da_cena(sv, projeto, atualizada)


@router.post("/{id_}/scenes/{cid}/recompose")
def recompor(id_: IdProjeto, cid: IdCena, sv: ServicosDep) -> dict[str, Any]:
    """Refaz a imagem da cena com o layout de agora (posição e tamanho dos personagens), sem gerar cenário novo."""
    projeto = _achar(sv, id_)
    cena = _cena(sv, projeto, cid)
    dados = dados_atuais(sv, cena.id)
    if dados is None or dados.background is None:
        raise HTTPException(status_code=409, detail="Esta cena ainda não tem cenário.")
    recompor_capa_da_cena(sv, projeto, cena.id)
    return _resposta_da_cena(sv, projeto, cena)


class PedidoDeLayout(BaseModel):
    items: list[dict[str, Any]] = Field(max_length=8)


@router.put("/{id_}/scenes/{cid}/layout")
def definir_layout(id_: IdProjeto, cid: IdCena, pedido: PedidoDeLayout, sv: ServicosDep) -> dict[str, Any]:
    """Reposiciona os personagens da cena (x, base_y, altura, espelhar, pose, ação, entrada) e recompõe a imagem."""
    projeto = _achar(sv, id_)
    _cena(sv, projeto, cid)  # confere que a cena é deste projeto
    try:
        itens = [ItemDeLayout.de_dict(i).para_dict() for i in pedido.items]
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422, detail="Layout inválido: cada item precisa de personagem_id, x, base_y e altura."
        ) from exc
    return editar_cena(id_, cid, PedidoDeEdicaoDeCena(changes={"layout": itens}), sv)
