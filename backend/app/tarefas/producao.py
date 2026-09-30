"""Produção do vídeo: animar as cenas (vozes + clipes), montar o áudio (falas, efeitos, música, legendas) e montar o vídeo final."""

from __future__ import annotations

import zlib
from pathlib import Path
from typing import Any

from PIL import Image

from ..animacao.render import quadro_de_capa, renderizar_cena
from ..audio.legendas import gerar_srt
from ..audio.mixagem import Efeito, Fala, carregar_mono, mixar, salvar_wav
from ..audio.musica import ESTILO_PADRAO, ESTILOS, gerar_efeito, gerar_musica
from ..erros import ErroParaOUsuario
from ..jobs.handlers import TITULOS, job_handler
from ..jobs.worker import JobContext
from ..midias.servico import adotar_e_avisar, remover_e_avisar
from ..motores.memoria import liberar_llm
from ..motores.tipos import MotorFalhou
from ..projetos.cenas import ClipeDaCena, DadosDaCena
from ..projetos.estado import carregar_projeto, cenas_do_projeto, gravar_andamento
from ..projetos.montagem import TRANSICOES, medir_volume, montar_video, plano_de_montagem
from ..projetos.pedidos import ParametrosDeAnimacao, ParametrosDeAudio, ParametrosDeMontagem
from ..projetos.pipeline import (
    cena_para_render,
    fps_do_projeto,
    impressao_digital,
    linha_do_tempo,
    personagens_do_projeto,
    resolucao,
)
from ..projetos.qualidade import verificar_flashes
from ..projetos.vozes import gerar_falas
from .comum import conferir_conteudo, temporario, validar

TITULOS["projeto.animar"] = "Animação das cenas"
TITULOS["projeto.audio"] = "Áudio do vídeo"
TITULOS["projeto.montar"] = "Montagem do vídeo"
PARTE_DAS_VOZES = 0.2  # na animação, as vozes ocupam a primeira parte da barra de progresso
GANHO_DOS_EFEITOS = 0.55
ATRASO_DO_EFEITO_S = 0.4


def _semente_da_cena(cena_id: str) -> int:
    return zlib.crc32(cena_id.encode()) % 100_000 + 1


@job_handler("projeto.animar")
def animar_cenas(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    sv = ctx.servicos
    pedido = validar(ParametrosDeAnimacao, params, "animação")
    projeto = carregar_projeto(sv, pedido.project_id)
    cenas = cenas_do_projeto(sv, projeto, pedido.scene_ids)
    if not cenas:
        raise ErroParaOUsuario("Este projeto ainda não tem cenas.")
    for _, dados in cenas:
        conferir_conteudo(
            dados.model_dump(include={"narration", "action", "visual", "lyrics", "title"}),
            *[f.text for f in dados.dialogue],
        )
    qualidade = "rascunho" if pedido.draft else "final"
    largura, altura = resolucao(projeto.proporcao, qualidade)
    fps = fps_do_projeto(projeto)
    personagens = {p.id: p for p in personagens_do_projeto(sv, projeto)}
    if liberados := liberar_llm(sv.ollama):
        ctx.log(f"Modelo de texto descarregado da memória: {', '.join(liberados)}")
    ctx.progresso(0.01, "Preparando as vozes...")
    falas = gerar_falas(ctx, sv, projeto, cenas, personagens, faixa=(0.02, PARTE_DAS_VOZES))
    feitas, reaproveitadas = 0, 0
    for indice, (cena, dados_lidos) in enumerate(cenas):
        ctx.ponto_de_controle()
        inicio = PARTE_DAS_VOZES + (1 - PARTE_DAS_VOZES) * indice / len(cenas)
        fim = PARTE_DAS_VOZES + (1 - PARTE_DAS_VOZES) * (indice + 1) / len(cenas)
        ctx.progresso(inicio, f"Animando a cena {cena.ordem} de {len(cenas)}")
        linhas = falas[cena.id]
        tempo = linha_do_tempo([f.duracao_s for f in linhas], dados_lidos.duration_s, fps)
        por_personagem: dict[str | None, list[tuple[Path, float]]] = {}
        for fala, comeco in zip(linhas, tempo.inicios, strict=True):
            por_personagem.setdefault(fala.character_id, []).append((sv.midias.caminho_absoluto(fala.midia), comeco))
        render, recortes = cena_para_render(
            sv, projeto, dados_lidos, personagens, tempo.duracao_s, fps, por_personagem, _semente_da_cena(cena.id)
        )
        codigo = impressao_digital(
            dados_lidos.background.media_id if dados_lidos.background else None,
            recortes,
            [(c.x, c.base_y, c.altura, c.espelhar, c.acao, c.entrada, c.fase) for c in render.camadas],
            render.camera,
            render.efeitos,
            tempo.duracao_s,
            fps,
            largura,
            altura,
            [f.midia.id for f in linhas],
            tempo.inicios,
        )
        linhas_da_cena = [
            {
                "media_id": f.midia.id,
                "character_id": f.character_id,
                "text": f.texto,
                "start_s": ini,
                "end_s": fim_da_fala,
            }
            for f, ini, fim_da_fala in zip(linhas, tempo.inicios, tempo.fins, strict=True)
        ]
        cronograma = {"lines": linhas_da_cena, "duration_s": tempo.duracao_s}
        clip = dados_lidos.clip
        if (
            clip
            and clip.render_hash == codigo
            and clip.quality == qualidade
            and not pedido.force
            and sv.midias.obter(clip.media_id)
        ):
            reaproveitadas += 1
            gravar_andamento(sv, cena.id, {"timeline": cronograma, "duration_s": tempo.duracao_s})
            ctx.log(f"Cena {cena.ordem}: o clipe pronto ainda vale (nada mudou)")
            continue
        saida = temporario(sv, "clipe", "mp4")
        resultado = renderizar_cena(
            ctx, sv.motores.ffmpeg, render, saida, largura=largura, altura=altura, fps=fps, faixa=(inicio, fim)
        )
        capa = quadro_de_capa(render, largura, altura, t=1.0).convert("RGB")
        miniatura = temporario(sv, "miniatura", "jpg")
        capa.save(miniatura, "JPEG", quality=85)
        midia = adotar_e_avisar(
            sv,
            saida,
            tipo="video",
            papel="cena_clipe",
            extensao="mp4",
            largura=largura,
            altura=altura,
            duracao_s=resultado.duracao_s,
            miniatura_de=miniatura,
            dono_tipo="cena",
            dono_id=cena.id,
            estilo=projeto.estilo,
            modelo="Animação de cena",
            job_id=ctx.job_id,
            metadados={
                "project_id": projeto.id,
                "render_hash": codigo,
                "quality": qualidade,
                "fps": fps,
                "seconds": resultado.segundos,
            },
        )
        miniatura.unlink(missing_ok=True)
        anterior = dados_lidos.clip.media_id if dados_lidos.clip else None
        gravar_andamento(
            sv,
            cena.id,
            {
                "clip": ClipeDaCena(
                    media_id=midia.id, render_hash=codigo, quality=qualidade, duration_s=resultado.duracao_s
                ).model_dump(),
                "timeline": cronograma,
                "duration_s": min(max(tempo.duracao_s, 2.0), 20.0),
            },
        )
        atual = sv.projetos.cena(cena.id)
        if atual is not None:  # o clipe novo precisa ser aprovado de novo
            aprovadas = {**atual.dados.get("approved", {}), "animacao": False}
            gravar_andamento(sv, cena.id, {"approved": aprovadas})
        if anterior and anterior != midia.id:
            remover_e_avisar(sv, anterior)
        feitas += 1
        ctx.log(
            f"Cena {cena.ordem}: {resultado.quadros} quadros em {resultado.segundos:.0f} s ({largura}×{altura}, {fps} fps)"
        )
    if projeto.etapa in ("enredo", "roteiro", "storyboard"):
        sv.projetos.atualizar(projeto.id, etapa="animacao")
    ctx.progresso(1.0, "Animação pronta")
    return {
        "rendered": feitas,
        "reused": reaproveitadas,
        "quality": qualidade,
        "width": largura,
        "height": altura,
        "fps": fps,
    }


# --- áudio -------------------------------------------------------------------------------------------------------------------
def _musica_do_projeto(projeto: Any) -> tuple[bool, str, int, float]:
    config = projeto.musica or {}
    estilo = str(config.get("style") or ESTILO_PADRAO)
    if estilo not in ESTILOS:
        estilo = ESTILO_PADRAO
    semente = int(config.get("seed") or (zlib.crc32(projeto.id.encode()) % 1_000_000 + 1))
    try:
        volume = min(max(float(config.get("volume", 0.22)), 0.0), 0.6)
    except (TypeError, ValueError):
        volume = 0.22
    return bool(config.get("enabled", True)), estilo, semente, volume


@job_handler("projeto.audio")
def montar_audio(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    sv = ctx.servicos
    pedido = validar(ParametrosDeAudio, params, "áudio")
    projeto = carregar_projeto(sv, pedido.project_id)
    cenas = cenas_do_projeto(sv, projeto)
    if not cenas:
        raise ErroParaOUsuario("Este projeto ainda não tem cenas.")
    if any(d.timeline is None for _, d in cenas):
        raise ErroParaOUsuario("Anime as cenas antes: é a animação que fala as linhas e mede o tempo de cada cena.")
    transicao = pedido.transition or str(projeto.configuracoes.get("transition") or "corte")
    if transicao not in TRANSICOES:
        raise ErroParaOUsuario("Transição desconhecida.")
    duracoes = [float(d.timeline["duration_s"]) if d.timeline else d.duration_s for _, d in cenas]
    plano = plano_de_montagem(duracoes, transicao)
    ctx.progresso(0.05, "Reunindo as falas...")
    falas: list[Fala] = []
    efeitos: list[Efeito] = []
    legendas: list[tuple[float, float, str]] = []
    for (cena, dados), inicio_da_cena in zip(cenas, plano.inicios, strict=True):
        ctx.ponto_de_controle()
        for linha in (dados.timeline or {}).get("lines", []):
            midia = sv.midias.obter(str(linha["media_id"]))
            if midia is None:
                raise ErroParaOUsuario(f"Uma fala da cena {cena.ordem} sumiu da biblioteca. Anime as cenas de novo.")
            comeco = inicio_da_cena + float(linha["start_s"])
            falas.append(Fala(comeco, carregar_mono(sv.midias.caminho_absoluto(midia))))
            legendas.append((comeco, inicio_da_cena + float(linha["end_s"]), str(linha["text"])))
        for nome in dados.sfx:
            try:
                efeitos.append(Efeito(inicio_da_cena + ATRASO_DO_EFEITO_S, gerar_efeito(nome), GANHO_DOS_EFEITOS))
            except KeyError:
                ctx.log(f"Efeito sonoro desconhecido na cena {cena.ordem}: {nome}", "WARNING")
    ligada, estilo, semente, volume = _musica_do_projeto(projeto)
    musica = None
    musica_id = None
    if ligada:
        ctx.progresso(0.3, "Compondo a música...")
        musica = gerar_musica(plano.duracao_total_s + 1.0, estilo, semente)
        arquivo = temporario(sv, "musica", "wav")
        salvar_wav(arquivo, musica.reshape(-1, 1))
        registro = adotar_e_avisar(
            sv,
            arquivo,
            tipo="audio",
            papel="musica",
            extensao="wav",
            duracao_s=plano.duracao_total_s + 1.0,
            dono_tipo="projeto",
            dono_id=projeto.id,
            modelo="Música instrumental por código",
            job_id=ctx.job_id,
            metadados={"style": estilo, "seed": semente, "volume": volume},
        )
        musica_id = registro.id
    ctx.progresso(0.6, "Misturando as vozes, os efeitos e a música...")
    trilha = mixar(plano.duracao_total_s, falas, efeitos, musica, ganho_da_musica=volume)
    arquivo_da_mix = temporario(sv, "mix", "wav")
    salvar_wav(arquivo_da_mix, trilha)
    mix = adotar_e_avisar(
        sv,
        arquivo_da_mix,
        tipo="audio",
        papel="mix",
        extensao="wav",
        duracao_s=plano.duracao_total_s,
        dono_tipo="projeto",
        dono_id=projeto.id,
        modelo="Mixagem com ducking",
        job_id=ctx.job_id,
        metadados={"transition": transicao, "voices": len(falas), "effects": len(efeitos)},
    )
    ctx.progresso(0.9, "Escrevendo as legendas...")
    arquivo_srt = temporario(sv, "legendas", "srt")
    arquivo_srt.write_text(gerar_srt(legendas), encoding="utf-8")
    srt = adotar_e_avisar(
        sv,
        arquivo_srt,
        tipo="legenda",
        papel="legenda",
        extensao="srt",
        dono_tipo="projeto",
        dono_id=projeto.id,
        job_id=ctx.job_id,
        metadados={"language": projeto.idioma},
    )
    anterior = projeto.configuracoes.get("audio") or {}
    manter = {mix.id, srt.id, musica_id or ""}
    for chave in ("mix_media_id", "music_media_id", "srt_media_id"):
        if anterior.get(chave) and anterior[chave] not in manter:
            remover_e_avisar(sv, str(anterior[chave]))
    audio = {
        "mix_media_id": mix.id,
        "music_media_id": musica_id,
        "srt_media_id": srt.id,
        "duration_s": plano.duracao_total_s,
        "transition": transicao,
        "offsets": plano.inicios,
    }
    sv.projetos.atualizar(
        projeto.id,
        configuracoes={**projeto.configuracoes, "audio": audio, "transition": transicao},
        aprovacoes={k: v for k, v in projeto.aprovacoes.items() if k not in ("audio", "montagem")},
        **({"etapa": "audio"} if projeto.etapa in ("enredo", "roteiro", "storyboard", "animacao") else {}),
    )
    ctx.progresso(1.0, "Áudio pronto")
    return {
        "mix_media_id": mix.id,
        "srt_media_id": srt.id,
        "music_media_id": musica_id,
        "duration_s": plano.duracao_total_s,
    }


# --- montagem ----------------------------------------------------------------------------------------------------------------
@job_handler("projeto.montar")
def montar_o_video(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    sv = ctx.servicos
    pedido = validar(ParametrosDeMontagem, params, "montagem")
    projeto = carregar_projeto(sv, pedido.project_id)
    cenas = cenas_do_projeto(sv, projeto)
    audio = projeto.configuracoes.get("audio") or {}
    if not audio.get("mix_media_id"):
        raise ErroParaOUsuario("Faça a etapa de áudio antes de montar o vídeo.")
    transicao = pedido.transition or str(audio.get("transition") or "corte")
    if transicao != audio.get("transition"):
        raise ErroParaOUsuario(
            "O áudio foi montado com outra transição entre as cenas. Refaça a etapa de áudio com esta transição."
        )
    clipes: list[Path] = []
    duracoes: list[float] = []
    for cena, dados in cenas:
        midia = sv.midias.obter(dados.clip.media_id) if dados.clip else None
        if midia is None or dados.timeline is None:
            raise ErroParaOUsuario(f"A cena {cena.ordem} ainda não tem clipe. Anime as cenas primeiro.")
        clipes.append(sv.midias.caminho_absoluto(midia))
        duracoes.append(float(dados.timeline["duration_s"]))
    plano = plano_de_montagem(duracoes, transicao)
    if abs(plano.duracao_total_s - float(audio.get("duration_s", 0))) > 0.05:
        raise ErroParaOUsuario("As cenas mudaram desde que o áudio foi montado. Refaça a etapa de áudio.")
    mix = sv.midias.obter(str(audio["mix_media_id"]))
    if mix is None:
        raise ErroParaOUsuario("A trilha de áudio sumiu da biblioteca. Refaça a etapa de áudio.")
    caminho_da_mix = sv.midias.caminho_absoluto(mix)
    ctx.progresso(0.05, "Medindo o volume do áudio...")
    medida = medir_volume(sv.motores.ffmpeg, ctx, caminho_da_mix)
    ctx.progresso(0.15, "Emendando as cenas e juntando o áudio...")
    saida = temporario(sv, "video", "mp4")
    sv.settings.temp_dir.mkdir(parents=True, exist_ok=True)
    montar_video(
        sv.motores.ffmpeg, ctx, clipes, duracoes, transicao, caminho_da_mix, saida, sv.settings.temp_dir, medida
    )
    sonda = sv.motores.ffmpeg.sondar(saida)
    ctx.progresso(0.9, "Conferindo o vídeo...")
    flashes = verificar_flashes(sv.motores.ffmpeg, saida)
    primeira = sv.projetos.cenas(projeto.id)[0]
    capa_id = DadosDaCena.model_validate(primeira.dados).keyframe_media_id
    miniatura = None
    if capa_id and (capa := sv.midias.obter(capa_id)):
        miniatura = temporario(sv, "capa", "jpg")
        with Image.open(sv.midias.caminho_absoluto(capa)) as imagem:
            imagem.convert("RGB").save(miniatura, "JPEG", quality=85)
    else:  # sem a imagem do storyboard: tira um quadro do próprio vídeo
        miniatura = temporario(sv, "capa", "jpg")
        try:
            sv.motores.ffmpeg.rodar(
                ctx,
                ["-ss", "1", "-i", saida.resolve(), "-frames:v", "1", "-q:v", "3", miniatura.resolve()],
                timeout=120,
            )
        except MotorFalhou:
            miniatura = None
    video = adotar_e_avisar(
        sv,
        saida,
        tipo="video",
        papel="video_final",
        extensao="mp4",
        largura=sonda.largura,
        altura=sonda.altura,
        duracao_s=sonda.duracao_s,
        miniatura_de=miniatura,
        dono_tipo="projeto",
        dono_id=projeto.id,
        estilo=projeto.estilo,
        modelo="Animação de cena + ffmpeg",
        job_id=ctx.job_id,
        metadados={
            "project_id": projeto.id,
            "title": projeto.titulo,
            "language": projeto.idioma,
            "format": projeto.formato,
            "fps": sonda.fps,
            "transition": transicao,
            "scenes": len(cenas),
            "loudness": medida or {},
            "flashes_per_second": flashes.maximo_por_segundo,
            "srt_media_id": audio.get("srt_media_id"),
        },
    )
    if miniatura:
        miniatura.unlink(missing_ok=True)
    for antigo in sv.midias.listar(papeis=("video_final",), dono_tipo="projeto", dono_id=projeto.id, limite=50):
        if antigo.id != video.id:
            remover_e_avisar(sv, antigo.id)
    qualidade = {
        "flashes": flashes.para_api(),
        "loudness_input": (medida or {}).get("input_i"),
        "loudness_target": -14.0,
        "duration_s": sonda.duracao_s,
    }
    sv.projetos.atualizar(
        projeto.id,
        configuracoes={**projeto.configuracoes, "final_media_id": video.id, "quality": qualidade},
        aprovacoes={k: v for k, v in projeto.aprovacoes.items() if k != "montagem"},
        etapa="montagem" if projeto.etapa != "revisao" else "revisao",
    )
    ctx.progresso(1.0, "Vídeo montado")
    return {
        "media_id": video.id,
        "duration_s": sonda.duracao_s,
        "width": sonda.largura,
        "height": sonda.altura,
        "flashes": flashes.para_api(),
    }
