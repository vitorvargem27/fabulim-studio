"""Entrega do vídeo (briefing 7.10 e 7.11): miniaturas do YouTube, título, descrição e tags, e a versão em outro idioma."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..erros import ErroParaOUsuario
from ..jobs.handlers import TITULOS, job_handler
from ..jobs.worker import JobContext
from ..midias.servico import adotar_e_avisar
from ..motores.tipos import MotorFalhou, MotorIndisponivel
from ..projetos.cenas import DadosDaCena
from ..projetos.estado import carregar_projeto, cenas_do_projeto
from ..projetos.metadados import metadados_por_ia, metadados_simples
from ..projetos.miniaturas import LAYOUTS, compor_miniatura, salvar_jpeg
from ..projetos.pedidos import ParametrosDeMetadados, ParametrosDeMiniaturas, ParametrosDeVersaoEmOutroIdioma
from ..projetos.pipeline import escolher_recorte, personagens_do_projeto
from ..projetos.repositorio import Projeto
from ..projetos.traducao import traduzir_cenas, traduzir_historia
from ..projetos.variantes import NOME_DO_IDIOMA, ajustes_herdados, dados_da_cena_no_outro_idioma
from .comum import conferir_conteudo, temporario, validar

if TYPE_CHECKING:
    from ..container import Servicos

TITULOS["projeto.miniaturas"] = "Miniaturas do vídeo"
TITULOS["projeto.metadados"] = "Título, descrição e tags"
TITULOS["projeto.versao_idioma"] = "Versão em outro idioma"


# --- miniaturas ----------------------------------------------------------------------------------------------------------------
def titulo_curto(texto: str, maximo: int = 44) -> str:
    """O título para a miniatura: sem o sufixo depois de « | » e curto (letras grandes precisam de poucas palavras)."""
    base = " ".join(texto.split("|")[0].split())
    if len(base) <= maximo:
        return base
    corte = base[:maximo].rsplit(" ", 1)[0]
    return (corte or base[:maximo]).rstrip(",;:.-") + "…"


@job_handler("projeto.miniaturas")
def gerar_miniaturas(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    sv = ctx.servicos
    pedido = validar(ParametrosDeMiniaturas, params, "miniaturas")
    projeto = carregar_projeto(sv, pedido.project_id)
    cenas = cenas_do_projeto(sv, projeto, pedido.scene_ids)
    com_cenario = [(c, d) for c, d in cenas if d.background is not None]
    if not com_cenario:
        raise ErroParaOUsuario("Gere o storyboard antes: a miniatura usa os cenários das cenas.")
    personagens = {p.id: p for p in personagens_do_projeto(sv, projeto)}
    if not personagens:
        raise ErroParaOUsuario("Este projeto não tem personagens para aparecer na miniatura.")
    titulo = titulo_curto(pedido.text or str(projeto.titulo))
    conferir_conteudo({"title": titulo})
    ids: list[str] = []
    for i in range(pedido.count):
        ctx.ponto_de_controle()
        ctx.progresso(i / pedido.count, f"Montando a miniatura {i + 1} de {pedido.count}")
        passo = max(
            len(com_cenario) // pedido.count, 1
        )  # cada variação usa um cenário diferente, espalhados pelo vídeo
        cena, dados = com_cenario[(i * passo) % len(com_cenario)]
        fundo = sv.midias.obter(dados.background.media_id) if dados.background else None
        if fundo is None:
            continue
        # quem está na cena vem primeiro; depois os outros personagens do vídeo (no máximo 3 na miniatura)
        ordem = [
            *[p for p in dados.characters if p in personagens],
            *[p for p in personagens if p not in dados.characters],
        ]
        recortes: list[Path] = []
        for personagem_id in ordem[:3]:
            _, recorte = escolher_recorte(sv, personagens[personagem_id], "feliz", "respirar", None)
            recortes.append(sv.midias.caminho_absoluto(recorte))
        quadro = compor_miniatura(
            sv.midias.caminho_absoluto(fundo),
            recortes,
            titulo=titulo,
            variacao=i,
            zoom=1.0 + 0.06 * (i % 3),
            deslocamento=(0.5, 0.35, 0.65)[i % 3],
        )
        saida = temporario(sv, "miniatura", "jpg")
        salvar_jpeg(quadro, saida)
        midia = adotar_e_avisar(
            sv,
            saida,
            tipo="imagem",
            papel="thumbnail",
            extensao="jpg",
            dono_tipo="projeto",
            dono_id=projeto.id,
            prompt=titulo,
            estilo=projeto.estilo,
            job_id=ctx.job_id,
            metadados={
                "variation": i,
                "layout": i % LAYOUTS,
                "scene_id": cena.id,
                "title": titulo,
                "project_id": projeto.id,
            },
        )
        ids.append(midia.id)
        ctx.log(f"Miniatura {i + 1} de {pedido.count} pronta (desenho {i % LAYOUTS + 1})")
    ctx.progresso(1.0, "Miniaturas prontas")
    return {"media_ids": ids}


# --- metadados -------------------------------------------------------------------------------------------------------------------
def guardar_metadados(sv: Servicos, projeto_id: str, metadados: dict[str, Any]) -> Projeto:
    """Grava no projeto sem apagar ajustes feitos enquanto o job rodava (lê o projeto de novo antes de gravar)."""
    atual = carregar_projeto(sv, projeto_id)
    novo = sv.projetos.atualizar(atual.id, configuracoes={**atual.configuracoes, "metadata": metadados})
    assert novo is not None
    return novo


@job_handler("projeto.metadados")
def gerar_metadados(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    sv = ctx.servicos
    pedido = validar(ParametrosDeMetadados, params, "metadados")
    projeto = carregar_projeto(sv, pedido.project_id)
    cenas = [d for _, d in cenas_do_projeto(sv, projeto)]
    nomes = [p.nome for p in personagens_do_projeto(sv, projeto)]
    conferir_conteudo({"title": projeto.titulo, "story": projeto.enredo.get("story", "")})
    avisos: list[str] = []
    resultado: dict[str, Any] | None = None
    origem = "simples"
    ctx.progresso(0.05, "Lendo a história...")
    if pedido.mode == "ia":
        try:
            resultado = metadados_por_ia(ctx, sv.motores.texto, projeto, cenas, nomes, faixa=(0.08, 0.95))
            origem = "ia"
        except (MotorIndisponivel, MotorFalhou) as exc:
            ctx.log(f"O modelo local não escreveu os textos ({exc}); usando o modelo pronto", "WARNING")
            avisos.append(f"O modelo local não conseguiu escrever os textos ({exc}). Usei o modelo pronto.")
    if resultado is None:
        resultado = metadados_simples(projeto, cenas, nomes)
        outro = "en" if projeto.idioma == "pt-BR" else "pt-BR"
        avisos.append(
            f"A versão em {NOME_DO_IDIOMA[outro]} é genérica (sem o modelo local não há tradução da história): "
            "confira e edite antes de publicar."
        )
    guardar_metadados(
        sv, projeto.id, {**resultado, "source": origem, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    )
    ctx.progresso(1.0, "Textos prontos")
    return {"origin": origem, "warnings": avisos}


# --- versão em outro idioma ----------------------------------------------------------------------------------------------------
@job_handler("projeto.versao_idioma")
def gerar_versao_em_outro_idioma(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    """Um projeto novo com o mesmo visual e o texto (roteiro, falas, letras e título) no outro idioma."""
    sv = ctx.servicos
    pedido = validar(ParametrosDeVersaoEmOutroIdioma, params, "versão em outro idioma")
    origem = carregar_projeto(sv, pedido.project_id)
    destino = pedido.language or ("en" if origem.idioma == "pt-BR" else "pt-BR")
    if destino == origem.idioma:
        raise ErroParaOUsuario("O projeto já está nesse idioma.")
    cenas = cenas_do_projeto(sv, origem)
    if not cenas:
        raise ErroParaOUsuario("Gere o roteiro antes de criar a versão em outro idioma: ela traduz as cenas.")
    conferir_conteudo({"title": origem.titulo, "story": origem.enredo.get("story", "")})
    originais = [d for _, d in cenas]
    avisos: list[str] = []
    historia: dict[str, str] = {}
    traduzidas: list[DadosDaCena] = originais
    if pedido.mode == "ia":
        try:
            ctx.progresso(0.03, "Traduzindo a história...")
            historia = traduzir_historia(
                ctx,
                sv.motores.texto,
                origem.idioma,
                destino,
                str(origem.enredo.get("title") or origem.titulo),
                str(origem.enredo.get("theme") or ""),
                str(origem.enredo.get("story") or ""),
                faixa=(0.03, 0.2),
            )
            traduzidas = traduzir_cenas(
                ctx, sv.motores.texto, origem.idioma, destino, originais, avisos, faixa=(0.2, 0.85)
            )
        except (MotorIndisponivel, MotorFalhou) as exc:
            ctx.log(f"O modelo local não traduziu ({exc}); os textos ficam no idioma original", "WARNING")
            avisos.append(
                f"O modelo local não conseguiu traduzir ({exc}). Os textos ficaram no idioma original: "
                "traduza-os na etapa do roteiro."
            )
            historia, traduzidas = {}, originais
    else:
        avisos.append("Os textos foram copiados sem tradução: traduza as falas na etapa do roteiro.")
    ctx.ponto_de_controle()
    ctx.progresso(0.88, "Criando o projeto...")
    narracao = " ".join(d.narration for d in traduzidas if d.narration.strip())
    enredo = {
        **origem.enredo,
        "language": destino,
        "title": historia.get("title") or origem.enredo.get("title") or origem.titulo,
        "theme": historia.get("theme") or origem.enredo.get("theme") or "",
        "story": historia.get("story") or narracao or str(origem.enredo.get("story") or ""),
    }
    titulo = historia.get("title") or f"{origem.titulo} ({NOME_DO_IDIOMA[destino]})"
    conferir_conteudo({"title": titulo, "story": enredo["story"]})
    herdados = {k: v for k, v in ajustes_herdados(origem).items() if k in ("fps", "transition")}
    novo = sv.projetos.criar(
        titulo[:160],
        origem.formato,
        destino,
        origem.estilo,
        origem.duracao_alvo_s,
        enredo,
        list(origem.personagens),
        musica=dict(origem.musica),
        configuracoes=herdados,
        origem_id=origem.id,
    )
    for (cena, dados), traduzida in zip(cenas, traduzidas, strict=True):
        nova = sv.projetos.criar_cena(novo.id, traduzida.model_dump(), cena.ordem)
        finais = dados_da_cena_no_outro_idioma(sv, dados, traduzida, nova.id, novo.id)
        sv.projetos.atualizar_cena_sem_versao(nova.id, DadosDaCena.model_validate(finais).model_dump())
    aprovacoes = {"enredo": True} if origem.aprovacoes.get("enredo") else {}
    sv.projetos.atualizar(novo.id, aprovacoes=aprovacoes, etapa="roteiro" if aprovacoes else "enredo")
    for aviso in avisos:
        ctx.log(aviso, "WARNING")
    ctx.progresso(1.0, "Versão criada: revise o roteiro")
    return {"project_id": novo.id, "language": destino, "scenes": len(cenas), "warnings": avisos}
