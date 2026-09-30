"""Pipeline de vídeo: roteiro, storyboard, animação, áudio e montagem (com os motores falsos; o desenho dos quadros é de verdade)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import soundfile as sf
from PIL import Image

from app.audio.mixagem import TAXA
from app.container import Servicos
from app.erros import ErroParaOUsuario
from app.jobs.worker import JobCanceled
from app.projetos.cenas import DadosDaCena
from app.tarefas.producao import animar_cenas, montar_audio, montar_o_video
from app.tarefas.projetos import gerar_roteiro, gerar_storyboard, recompor_capa_da_cena

from .builders_projetos import dar_cenario, personagem_pronto, projeto_com_cenas
from .fakes_motores import ContextoDeTeste, FfmpegFalso, ImagemFalsa, TextoFalso, VozFalsa
from .test_projetos import BRUTO

pytestmark = pytest.mark.usefixtures("resolucoes_pequenas")


def _ctx(sv: Servicos, **kw: Any) -> ContextoDeTeste:
    return ContextoDeTeste(servicos=sv, **kw)


def _imagem(sv: Servicos) -> ImagemFalsa:
    return cast(ImagemFalsa, sv.motores.imagem)


def _ffmpeg(sv: Servicos) -> FfmpegFalso:
    return cast(FfmpegFalso, sv.motores.ffmpeg)


def _voz(sv: Servicos) -> VozFalsa:
    return cast(VozFalsa, sv.motores.voz)


def _texto(sv: Servicos) -> TextoFalso:
    return cast(TextoFalso, sv.motores.texto)


def _dados(sv: Servicos, cena_id: str) -> DadosDaCena:
    cena = sv.projetos.cena(cena_id)
    assert cena is not None
    return DadosDaCena.model_validate(cena.dados)


@pytest.fixture
def elenco(servicos: Servicos, tmp_path: Path) -> list[Any]:
    return [
        personagem_pronto(servicos, tmp_path, "Lila"),
        personagem_pronto(servicos, tmp_path, "Bento", species="urso", voice="grave"),
    ]


class TestRoteiro:
    def _projeto(self, sv: Servicos, elenco: list[Any], **campos: Any) -> Any:
        enredo = {
            "title": "A chuva",
            "story": "Lila brinca no jardim. Começa a chover. Bento chega com um guarda-chuva.",
            "characters": ["Lila", "Bento"],
            "settings": "jardim",
            "language": "pt-BR",
            "style": "2D",
        }
        projeto = sv.projetos.criar("", "short", "pt-BR", "2D", 30, {**enredo, **campos}, [p.id for p in elenco])
        return projeto

    def test_o_modelo_local_escreve_o_roteiro_e_as_cenas_nascem_validadas(
        self, servicos: Servicos, elenco: list[Any]
    ) -> None:
        _texto(servicos).respostas.append(BRUTO)
        projeto = self._projeto(servicos, elenco)
        resultado = gerar_roteiro(_ctx(servicos), {"project_id": projeto.id, "mode": "ia"})
        assert resultado["scenes"] == 2 and resultado["origin"] == "ia"
        cenas = servicos.projetos.cenas(projeto.id)
        # o título da segunda cena repetia o do vídeo («A chuva»): ela ganha o começo da narração
        assert [c.dados["title"] for c in cenas] == ["O jardim", "Começou a chover"]
        assert cenas[0].dados["characters"] == [elenco[0].id, elenco[1].id] and cenas[1].dados["suggestion"] is True
        atual = servicos.projetos.obter(projeto.id)
        assert atual is not None and atual.etapa == "roteiro" and atual.titulo == "A chuva do jardim"
        assert any("Sol" in aviso for aviso in resultado["warnings"])

    def test_sem_o_modelo_local_cai_no_modo_simples_e_avisa(self, servicos: Servicos, elenco: list[Any]) -> None:
        servicos.motores.texto = TextoFalso(indisponivel="O Ollama não está no ar")
        projeto = self._projeto(servicos, elenco)
        r = gerar_roteiro(_ctx(servicos), {"project_id": projeto.id})
        assert r["origin"] == "simples" and r["scenes"] >= 2
        assert any("Usei o modo simples" in aviso for aviso in r["warnings"])

    def test_modelo_que_nao_devolve_cenas_tambem_cai_no_simples(self, servicos: Servicos, elenco: list[Any]) -> None:
        _texto(servicos).respostas.append({"scenes": []})
        projeto = self._projeto(servicos, elenco)
        r = gerar_roteiro(_ctx(servicos), {"project_id": projeto.id})
        assert r["origin"] == "simples" and any("nenhuma cena utilizável" in a for a in r["warnings"])

    def test_modo_simples_nao_chama_o_modelo(self, servicos: Servicos, elenco: list[Any]) -> None:
        projeto = self._projeto(servicos, elenco)
        r = gerar_roteiro(_ctx(servicos), {"project_id": projeto.id, "mode": "simples"})
        assert r["origin"] == "simples" and _texto(servicos).chamadas == []

    def test_gerar_de_novo_guarda_o_roteiro_anterior_e_apaga_o_que_era_das_cenas_velhas(
        self, servicos: Servicos, elenco: list[Any], tmp_path: Path
    ) -> None:
        projeto = self._projeto(servicos, elenco)
        gerar_roteiro(_ctx(servicos), {"project_id": projeto.id, "mode": "simples"})
        primeira = servicos.projetos.cenas(projeto.id)[0]
        fundo = dar_cenario(servicos, tmp_path, primeira)
        gerar_roteiro(_ctx(servicos), {"project_id": projeto.id, "mode": "simples"})
        atual = servicos.projetos.obter(projeto.id)
        assert atual is not None and len(atual.configuracoes["script_history"]) == 1
        assert servicos.projetos.cena(primeira.id) is None and servicos.midias.obter(fundo) is None
        assert atual.aprovacoes == {}

    def test_o_filtro_barra_uma_historia_com_marca_de_terceiros(self, servicos: Servicos, elenco: list[Any]) -> None:
        projeto = self._projeto(servicos, elenco, story="Lila encontra a Peppa Pig no jardim.")
        with pytest.raises(ErroParaOUsuario, match="peppa"):
            gerar_roteiro(_ctx(servicos), {"project_id": projeto.id})

    def test_projeto_apagado_e_pedido_invalido(self, servicos: Servicos) -> None:
        with pytest.raises(ErroParaOUsuario, match="não existe mais"):
            gerar_roteiro(_ctx(servicos), {"project_id": "0" * 32})
        with pytest.raises(ErroParaOUsuario, match="incompleto"):
            gerar_roteiro(_ctx(servicos), {"project_id": "x"})


class TestStoryboard:
    def test_gera_o_cenario_de_cada_cena_sem_os_personagens_e_compoe_a_imagem_da_cena(
        self, servicos: Servicos, elenco: list[Any]
    ) -> None:
        projeto, cenas = projeto_com_cenas(servicos, elenco)
        resultado = gerar_storyboard(_ctx(servicos), {"project_id": projeto.id, "quality": "padrao", "seed": 10})
        assert resultado["scenes"] == 2 and set(resultado["generated"]) == {c.id for c in cenas}
        pedidos = _imagem(servicos).pedidos
        assert len(pedidos) == 2 and all((p.largura, p.altura) == (432, 768) for p in pedidos)  # short: 9:16
        assert (
            "jardim florido" in pedidos[0].prompt
            and "Lila" not in pedidos[0].prompt
            and "No characters" in pedidos[0].prompt
        )
        for cena in cenas:
            dados = _dados(servicos, cena.id)
            assert dados.background is not None and dados.candidates == [dados.background.media_id]
            fundo = servicos.midias.obter(dados.background.media_id)
            assert fundo is not None and fundo.papel == "fundo" and fundo.dono_id == cena.id and fundo.seed is not None
            assert fundo.metadados["project_id"] == projeto.id and fundo.prompt_tecnico
            assert dados.keyframe_media_id is not None
            capa = servicos.midias.obter(dados.keyframe_media_id)
            assert capa is not None and capa.papel == "quadro" and capa.formato == "jpg" and capa.dono_id == cena.id
            with Image.open(servicos.midias.caminho_absoluto(capa)) as imagem:
                assert imagem.size == (90, 160)
            assert dados.approved == {"storyboard": False, "animacao": False}
        atual = servicos.projetos.obter(projeto.id)
        assert atual is not None and atual.etapa == "storyboard"
        assert all(c.versao == 2 for c in servicos.projetos.cenas(projeto.id))  # a edição virou uma versão do histórico

    def test_video_longo_gera_cenarios_16_por_9(self, servicos: Servicos, elenco: list[Any]) -> None:
        projeto, _ = projeto_com_cenas(servicos, elenco, formato="longo")
        gerar_storyboard(_ctx(servicos), {"project_id": projeto.id, "quality": "rascunho"})
        assert {(p.largura, p.altura) for p in _imagem(servicos).pedidos} == {(640, 352)}

    def test_faltantes_pula_quem_ja_tem_cenario(self, servicos: Servicos, elenco: list[Any], tmp_path: Path) -> None:
        projeto, cenas = projeto_com_cenas(servicos, elenco)
        existente = dar_cenario(servicos, tmp_path, cenas[0])
        gerar_storyboard(_ctx(servicos), {"project_id": projeto.id})
        assert len(_imagem(servicos).pedidos) == 1
        assert _dados(servicos, cenas[0].id).background.media_id == existente  # type: ignore[union-attr]
        assert _dados(servicos, cenas[1].id).background is not None
        assert _dados(servicos, cenas[0].id).keyframe_media_id is not None  # a imagem composta também foi feita

    def test_regerar_troca_o_cenario_e_guarda_o_antigo_como_candidato(
        self, servicos: Servicos, elenco: list[Any], tmp_path: Path
    ) -> None:
        projeto, cenas = projeto_com_cenas(servicos, elenco)
        antigo = dar_cenario(servicos, tmp_path, cenas[0])
        gerar_storyboard(_ctx(servicos), {"project_id": projeto.id, "scene_ids": [cenas[0].id], "mode": "regerar"})
        dados = _dados(servicos, cenas[0].id)
        assert len(_imagem(servicos).pedidos) == 1 and dados.background is not None
        assert dados.background.media_id != antigo and dados.candidates[0] == antigo
        assert dados.candidates[-1] == dados.background.media_id
        assert servicos.midias.obter(antigo) is not None  # nada é sobrescrito

    def test_variacoes_acrescentam_candidatos_sem_trocar_o_escolhido(
        self, servicos: Servicos, elenco: list[Any], tmp_path: Path
    ) -> None:
        projeto, cenas = projeto_com_cenas(servicos, elenco)
        escolhido = dar_cenario(servicos, tmp_path, cenas[0])
        gerar_storyboard(
            _ctx(servicos),
            {"project_id": projeto.id, "scene_ids": [cenas[0].id], "mode": "variacoes", "variations": 3, "seed": 5},
        )
        dados = _dados(servicos, cenas[0].id)
        assert len(dados.candidates) == 4 and dados.candidates[0] == escolhido
        assert dados.background is not None and dados.background.media_id == escolhido
        assert [p.seed for p in _imagem(servicos).pedidos] == [5, 5 + 7919, 5 + 2 * 7919]

    def test_variacoes_de_uma_cena_sem_cenario_escolhem_a_primeira(self, servicos: Servicos, elenco: list[Any]) -> None:
        projeto, cenas = projeto_com_cenas(servicos, elenco)
        gerar_storyboard(
            _ctx(servicos), {"project_id": projeto.id, "scene_ids": [cenas[0].id], "mode": "variacoes", "variations": 2}
        )
        dados = _dados(servicos, cenas[0].id)
        assert dados.background is not None and dados.background.media_id == dados.candidates[0]

    def test_recompor_troca_a_imagem_da_cena_e_apaga_a_antiga(self, servicos: Servicos, elenco: list[Any]) -> None:
        projeto, cenas = projeto_com_cenas(servicos, elenco)
        gerar_storyboard(_ctx(servicos), {"project_id": projeto.id})
        antiga = _dados(servicos, cenas[0].id).keyframe_media_id
        nova = recompor_capa_da_cena(servicos, projeto, cenas[0].id)
        assert nova != antiga and servicos.midias.obter(str(antiga)) is None
        assert _dados(servicos, cenas[0].id).keyframe_media_id == nova

    def test_personagem_sem_recorte_bloqueia_antes_de_gastar_tempo(self, servicos: Servicos, tmp_path: Path) -> None:
        sem_recorte = personagem_pronto(servicos, tmp_path, "Sol", slots=())
        projeto, _ = projeto_com_cenas(servicos, [sem_recorte])
        with pytest.raises(ErroParaOUsuario, match="PNG transparente"):
            gerar_storyboard(_ctx(servicos), {"project_id": projeto.id})
        assert _imagem(servicos).pedidos == []

    def test_personagem_apagado_da_biblioteca_bloqueia(self, servicos: Servicos, elenco: list[Any]) -> None:
        projeto, _ = projeto_com_cenas(servicos, elenco)
        servicos.personagens.remover(elenco[0].id)
        with pytest.raises(ErroParaOUsuario, match="não está mais na biblioteca"):
            gerar_storyboard(_ctx(servicos), {"project_id": projeto.id})

    def test_sem_cenas_pede_o_roteiro(self, servicos: Servicos, elenco: list[Any]) -> None:
        projeto, _ = projeto_com_cenas(servicos, elenco, cenas=[])
        with pytest.raises(ErroParaOUsuario, match="roteiro primeiro"):
            gerar_storyboard(_ctx(servicos), {"project_id": projeto.id})

    def test_cancelar_no_meio_mantem_as_cenas_que_ja_ficaram_prontas(
        self, servicos: Servicos, elenco: list[Any]
    ) -> None:
        projeto, cenas = projeto_com_cenas(servicos, elenco)
        with pytest.raises(JobCanceled):
            gerar_storyboard(_ctx(servicos, cancelar_no_ponto=3), {"project_id": projeto.id})
        assert _dados(servicos, cenas[0].id).background is not None and _dados(servicos, cenas[1].id).background is None

    def test_o_filtro_confere_o_cenario_de_novo(self, servicos: Servicos, elenco: list[Any]) -> None:
        projeto, _ = projeto_com_cenas(
            servicos,
            elenco,
            cenas=[{"title": "x", "visual": "uma floresta com muito sangue", "characters": [elenco[0].id]}],
        )
        with pytest.raises(ErroParaOUsuario, match="sangue"):
            gerar_storyboard(_ctx(servicos), {"project_id": projeto.id})
        assert _imagem(servicos).pedidos == []


def _pronto_para_animar(sv: Servicos, elenco: list[Any], tmp_path: Path, **kw: Any) -> tuple[Any, list[Any]]:
    projeto, cenas = projeto_com_cenas(sv, elenco, **{"fps": 12, **kw})
    for cena in cenas:
        dar_cenario(sv, tmp_path, cena)
    return projeto, cenas


class TestAnimacao:
    def test_fala_as_linhas_calcula_o_tempo_e_desenha_um_clipe_por_cena(
        self, servicos: Servicos, elenco: list[Any], tmp_path: Path
    ) -> None:
        projeto, cenas = _pronto_para_animar(servicos, elenco, tmp_path)
        r = animar_cenas(_ctx(servicos), {"project_id": projeto.id})
        assert (r["rendered"], r["reused"], r["quality"], r["fps"]) == (2, 0, "final", 12) and (
            r["width"],
            r["height"],
        ) == (90, 160)
        primeira = _dados(servicos, cenas[0].id)
        linhas = primeira.timeline["lines"]  # type: ignore[index]
        assert [(linha["text"], linha["character_id"]) for linha in linhas] == [
            ("Era uma vez um jardim.", None),
            ("Que dia lindo!", elenco[0].id),
        ]
        assert (
            linhas[0]["start_s"] == 0.35
            and linhas[0]["end_s"] == pytest.approx(1.45)
            and linhas[1]["start_s"] == pytest.approx(1.85)
        )
        assert primeira.timeline["duration_s"] == 5.0  # type: ignore[index]
        clipe = servicos.midias.obter(primeira.clip.media_id)  # type: ignore[union-attr]
        assert (
            clipe is not None and clipe.tipo == "video" and clipe.papel == "cena_clipe" and clipe.dono_id == cenas[0].id
        )
        assert (clipe.largura, clipe.altura, clipe.duracao_s) == (90, 160, 5.0) and clipe.miniatura is not None
        assert clipe.metadados["quality"] == "final" and clipe.metadados["fps"] == 12
        render = _ffmpeg(servicos).renders[0]
        assert (render["quadros"], render["fps"]) == (60, 12) and primeira.approved.get("animacao") is False
        atual = servicos.projetos.obter(projeto.id)
        assert atual is not None and atual.etapa == "animacao"

    def test_as_vozes_sao_de_cada_personagem_e_do_narrador(
        self, servicos: Servicos, elenco: list[Any], tmp_path: Path
    ) -> None:
        projeto, cenas = _pronto_para_animar(servicos, elenco, tmp_path)
        animar_cenas(_ctx(servicos), {"project_id": projeto.id})
        itens = _voz(servicos).itens
        assert [(i.texto, i.voz) for i in itens] == [
            ("Era uma vez um jardim.", "pm_alex"),  # narrador padrão
            ("Que dia lindo!", "pf_dora"),  # a voz cadastrada da Lila
            ("Começou a chover.", "pm_alex"),
        ]
        falas = servicos.midias.listar(papeis=("fala",), dono_tipo="cena", dono_id=cenas[0].id)
        assert len(falas) == 2 and all(f.tipo == "audio" and f.metadados["hash"] for f in falas)
        aguda = next(f for f in falas if f.prompt == "Que dia lindo!")
        assert aguda.metadados["voice"]["pitch"] == 1.0 and aguda.metadados["character_id"] == elenco[0].id
        rubber = [a for a in _ffmpeg(servicos).execucoes if any("rubberband" in x for x in a)]
        assert rubber == []  # a voz padrão da Lila está no tom normal; o ffmpeg só reamostrou

    def test_tom_do_personagem_passa_pelo_ffmpeg(self, servicos: Servicos, tmp_path: Path) -> None:
        lila = personagem_pronto(servicos, tmp_path, "Lila", voz={"id": "pf_dora", "speed": 1.0, "pitch": 1.15})
        projeto, _ = _pronto_para_animar(servicos, [lila], tmp_path)
        animar_cenas(_ctx(servicos), {"project_id": projeto.id})
        assert any("rubberband=pitch=1.1500" in a for args in _ffmpeg(servicos).execucoes for a in args)

    def test_o_que_nao_mudou_nao_e_refeito(self, servicos: Servicos, elenco: list[Any], tmp_path: Path) -> None:
        projeto, cenas = _pronto_para_animar(servicos, elenco, tmp_path)
        animar_cenas(_ctx(servicos), {"project_id": projeto.id})
        clipe = _dados(servicos, cenas[0].id).clip.media_id  # type: ignore[union-attr]
        falou, desenhou = len(_voz(servicos).itens), len(_ffmpeg(servicos).renders)
        r = animar_cenas(_ctx(servicos), {"project_id": projeto.id})
        assert (r["rendered"], r["reused"]) == (0, 2)
        assert len(_voz(servicos).itens) == falou and len(_ffmpeg(servicos).renders) == desenhou
        assert _dados(servicos, cenas[0].id).clip.media_id == clipe  # type: ignore[union-attr]

    def test_forcar_desenha_de_novo_e_apaga_o_clipe_velho(
        self, servicos: Servicos, elenco: list[Any], tmp_path: Path
    ) -> None:
        projeto, cenas = _pronto_para_animar(servicos, elenco, tmp_path)
        animar_cenas(_ctx(servicos), {"project_id": projeto.id})
        velho = _dados(servicos, cenas[0].id).clip.media_id  # type: ignore[union-attr]
        r = animar_cenas(_ctx(servicos), {"project_id": projeto.id, "force": True})
        assert r["rendered"] == 2 and servicos.midias.obter(velho) is None
        assert _dados(servicos, cenas[0].id).clip.media_id != velho  # type: ignore[union-attr]

    def test_editar_a_narracao_refaz_so_essa_fala_e_o_clipe_dessa_cena(
        self, servicos: Servicos, elenco: list[Any], tmp_path: Path
    ) -> None:
        projeto, cenas = _pronto_para_animar(servicos, elenco, tmp_path)
        animar_cenas(_ctx(servicos), {"project_id": projeto.id})
        dados = _dados(servicos, cenas[1].id).model_dump()
        dados["narration"] = "Pingou uma gotinha no nariz."
        servicos.projetos.atualizar_cena(cenas[1].id, dados, "editada")
        falou = len(_voz(servicos).itens)
        r = animar_cenas(_ctx(servicos), {"project_id": projeto.id})
        assert (r["rendered"], r["reused"]) == (1, 1) and len(_voz(servicos).itens) == falou + 1
        assert _voz(servicos).itens[-1].texto == "Pingou uma gotinha no nariz."

    def test_cena_com_fala_longa_dura_o_tempo_da_fala(
        self, servicos: Servicos, elenco: list[Any], tmp_path: Path
    ) -> None:
        longa = "Lila brinca no jardim com os amigos. " * 8  # ~300 letras: ~15 s de fala
        projeto, cenas = projeto_com_cenas(
            servicos,
            elenco,
            [{"title": "x", "duration_s": 4, "narration": longa.strip(), "characters": [elenco[0].id]}],
            fps=12,
        )
        dar_cenario(servicos, tmp_path, cenas[0])
        animar_cenas(_ctx(servicos), {"project_id": projeto.id})
        dados = _dados(servicos, cenas[0].id)
        fala = servicos.midias.listar(papeis=("fala",), dono_id=cenas[0].id)[0].duracao_s or 0
        assert (
            dados.timeline["duration_s"] == pytest.approx(0.35 + fala + 0.7, abs=0.1)
            and dados.timeline["duration_s"] > 10
        )  # type: ignore[index]
        assert dados.duration_s == pytest.approx(dados.timeline["duration_s"], abs=0.1)  # type: ignore[index]
        assert _ffmpeg(servicos).renders[0]["quadros"] == round(dados.timeline["duration_s"] * 12)  # type: ignore[index]

    def test_rascunho_e_longo(self, servicos: Servicos, elenco: list[Any], tmp_path: Path) -> None:
        projeto, _ = _pronto_para_animar(servicos, elenco, tmp_path, formato="longo")
        r = animar_cenas(_ctx(servicos), {"project_id": projeto.id, "draft": True})
        assert (r["quality"], r["width"], r["height"]) == ("rascunho", 160, 90)

    def test_fps_configuravel_e_limitado(self, servicos: Servicos, elenco: list[Any], tmp_path: Path) -> None:
        projeto, _ = _pronto_para_animar(servicos, elenco, tmp_path, fps=999)
        assert animar_cenas(_ctx(servicos), {"project_id": projeto.id})["fps"] == 60

    def test_so_as_cenas_pedidas(self, servicos: Servicos, elenco: list[Any], tmp_path: Path) -> None:
        projeto, cenas = _pronto_para_animar(servicos, elenco, tmp_path)
        r = animar_cenas(_ctx(servicos), {"project_id": projeto.id, "scene_ids": [cenas[1].id]})
        assert (
            r["rendered"] == 1
            and _dados(servicos, cenas[0].id).clip is None
            and _dados(servicos, cenas[1].id).clip is not None
        )

    def test_cena_sem_cenario_pede_o_storyboard(self, servicos: Servicos, elenco: list[Any]) -> None:
        projeto, _ = projeto_com_cenas(servicos, elenco, fps=12)
        with pytest.raises(ErroParaOUsuario, match="storyboard"):
            animar_cenas(_ctx(servicos), {"project_id": projeto.id})

    def test_cena_sem_falas_nem_personagens_anima_so_o_cenario(self, servicos: Servicos, tmp_path: Path) -> None:
        projeto, cenas = projeto_com_cenas(
            servicos, [], [{"title": "só o céu", "duration_s": 3.0, "camera": "zoom_in"}], fps=12
        )
        dar_cenario(servicos, tmp_path, cenas[0])
        animar_cenas(_ctx(servicos), {"project_id": projeto.id})
        assert _dados(servicos, cenas[0].id).timeline == {"lines": [], "duration_s": 3.0}

    def test_cancelar_no_meio(self, servicos: Servicos, elenco: list[Any], tmp_path: Path) -> None:
        projeto, cenas = _pronto_para_animar(servicos, elenco, tmp_path)
        with pytest.raises(JobCanceled):
            animar_cenas(_ctx(servicos, cancelar_no_ponto=8), {"project_id": projeto.id})
        assert _dados(servicos, cenas[1].id).clip is None

    def test_o_filtro_de_conteudo_confere_as_falas(self, servicos: Servicos, elenco: list[Any], tmp_path: Path) -> None:
        projeto, _ = _pronto_para_animar(servicos, elenco, tmp_path, cenas=None)
        cenas = servicos.projetos.cenas(projeto.id)
        dados = _dados(servicos, cenas[0].id).model_dump()
        dados["dialogue"] = [{"character_id": elenco[0].id, "text": "Vou pegar a faca!"}]
        servicos.projetos.atualizar_cena_sem_versao(cenas[0].id, dados)
        with pytest.raises(ErroParaOUsuario, match="faca"):
            animar_cenas(_ctx(servicos), {"project_id": projeto.id})
        assert _voz(servicos).itens == []


def _animado(sv: Servicos, elenco: list[Any], tmp_path: Path, **kw: Any) -> tuple[Any, list[Any]]:
    projeto, cenas = _pronto_para_animar(sv, elenco, tmp_path, **kw)
    animar_cenas(_ctx(sv), {"project_id": projeto.id})
    return projeto, cenas


class TestAudio:
    def test_mistura_vozes_efeitos_e_musica_e_escreve_as_legendas(
        self, servicos: Servicos, elenco: list[Any], tmp_path: Path
    ) -> None:
        projeto, _ = _animado(servicos, elenco, tmp_path)
        r = montar_audio(_ctx(servicos), {"project_id": projeto.id})
        assert r["duration_s"] == 10.0
        mix = servicos.midias.obter(r["mix_media_id"])
        assert mix is not None and mix.papel == "mix" and mix.tipo == "audio" and mix.dono_id == projeto.id
        dados, taxa = sf.read(str(servicos.midias.caminho_absoluto(mix)), always_2d=True)
        assert taxa == TAXA and dados.shape == (10 * TAXA, 2) and abs(dados).max() <= 0.98
        assert abs(dados).max() > 0.1  # a música está lá (as vozes falsas são silêncio)
        musica = servicos.midias.obter(r["music_media_id"])
        assert musica is not None and musica.papel == "musica" and musica.metadados["style"] == "alegre"
        srt = servicos.midias.obter(r["srt_media_id"])
        assert srt is not None and srt.tipo == "legenda"
        texto = servicos.midias.caminho_absoluto(srt).read_text(encoding="utf-8")
        assert "00:00:00,350 --> 00:00:01,450\nEra uma vez um jardim." in texto and "Que dia lindo!" in texto
        assert "00:00:05,350 --> " in texto and "Começou a chover." in texto  # a 2ª cena começa em 5 s
        atual = servicos.projetos.obter(projeto.id)
        assert atual is not None and atual.etapa == "audio" and atual.configuracoes["audio"]["offsets"] == [0.0, 5.0]

    def test_a_transicao_sobrepoe_as_cenas_e_encurta_o_video(
        self, servicos: Servicos, elenco: list[Any], tmp_path: Path
    ) -> None:
        projeto, _ = _animado(servicos, elenco, tmp_path)
        r = montar_audio(_ctx(servicos), {"project_id": projeto.id, "transition": "fade"})
        assert r["duration_s"] == 9.5
        assert servicos.projetos.obter(projeto.id).configuracoes["audio"]["offsets"] == [0.0, 4.5]  # type: ignore[union-attr]
        srt = servicos.midias.caminho_absoluto(servicos.midias.obter(r["srt_media_id"]))  # type: ignore[arg-type]
        assert "00:00:04,850 --> " in srt.read_text(encoding="utf-8")

    def test_musica_desligada_e_estilo(self, servicos: Servicos, elenco: list[Any], tmp_path: Path) -> None:
        projeto, _ = _animado(servicos, elenco, tmp_path)
        servicos.projetos.atualizar(projeto.id, musica={"enabled": False})
        r = montar_audio(_ctx(servicos), {"project_id": projeto.id})
        assert r["music_media_id"] is None
        dados, _ = sf.read(str(servicos.midias.caminho_absoluto(servicos.midias.obter(r["mix_media_id"]))))  # type: ignore[arg-type]
        assert abs(dados).max() < 0.05 or abs(dados).max() > 0  # só efeitos (o boing) e as vozes silenciosas
        servicos.projetos.atualizar(projeto.id, musica={"enabled": True, "style": "calma", "seed": 3, "volume": 0.4})
        r2 = montar_audio(_ctx(servicos), {"project_id": projeto.id})
        musica = servicos.midias.obter(r2["music_media_id"])
        assert musica is not None and musica.metadados == {"style": "calma", "seed": 3, "volume": 0.4}

    def test_refazer_apaga_a_mix_e_as_legendas_antigas(
        self, servicos: Servicos, elenco: list[Any], tmp_path: Path
    ) -> None:
        projeto, _ = _animado(servicos, elenco, tmp_path)
        primeiro = montar_audio(_ctx(servicos), {"project_id": projeto.id})
        segundo = montar_audio(_ctx(servicos), {"project_id": projeto.id})
        for chave in ("mix_media_id", "srt_media_id", "music_media_id"):
            assert servicos.midias.obter(primeiro[chave]) is None and servicos.midias.obter(segundo[chave]) is not None
        assert len(servicos.midias.listar(papeis=("mix",), dono_id=projeto.id)) == 1

    def test_exige_a_animacao_antes(self, servicos: Servicos, elenco: list[Any], tmp_path: Path) -> None:
        projeto, _ = _pronto_para_animar(servicos, elenco, tmp_path)
        with pytest.raises(ErroParaOUsuario, match="Anime as cenas"):
            montar_audio(_ctx(servicos), {"project_id": projeto.id})

    def test_fala_que_sumiu_da_biblioteca(self, servicos: Servicos, elenco: list[Any], tmp_path: Path) -> None:
        projeto, cenas = _animado(servicos, elenco, tmp_path)
        fala = servicos.midias.listar(papeis=("fala",), dono_id=cenas[0].id)[0]
        servicos.midias.remover(fala.id)
        with pytest.raises(ErroParaOUsuario, match="sumiu da biblioteca"):
            montar_audio(_ctx(servicos), {"project_id": projeto.id})

    def test_transicao_desconhecida(self, servicos: Servicos, elenco: list[Any], tmp_path: Path) -> None:
        projeto, _ = _animado(servicos, elenco, tmp_path)
        servicos.projetos.atualizar(projeto.id, configuracoes={**projeto.configuracoes, "transition": "explosao"})
        with pytest.raises(ErroParaOUsuario, match="Transição desconhecida"):
            montar_audio(_ctx(servicos), {"project_id": projeto.id})


def _com_audio(sv: Servicos, elenco: list[Any], tmp_path: Path, transition: str | None = None) -> tuple[Any, list[Any]]:
    projeto, cenas = _animado(sv, elenco, tmp_path)
    montar_audio(_ctx(sv), {"project_id": projeto.id, **({"transition": transition} if transition else {})})
    return projeto, cenas


class TestMontagem:
    def test_emenda_as_cenas_e_guarda_o_video_final(
        self, servicos: Servicos, elenco: list[Any], tmp_path: Path
    ) -> None:
        projeto, cenas = _com_audio(servicos, elenco, tmp_path)
        recompor_capa_da_cena(servicos, projeto, cenas[0].id)  # a imagem do storyboard vira a miniatura do vídeo
        _ffmpeg(servicos).sondas.clear()
        r = montar_o_video(_ctx(servicos), {"project_id": projeto.id})
        video = servicos.midias.obter(r["media_id"])
        assert (
            video is not None and video.papel == "video_final" and video.tipo == "video" and video.dono_id == projeto.id
        )
        assert (
            video.metadados["transition"] == "corte"
            and video.metadados["scenes"] == 2
            and video.metadados["srt_media_id"]
        )
        assert video.miniatura is not None
        comandos = _ffmpeg(servicos).execucoes
        montagem = comandos[-1]
        assert "concat" in montagem and "copy" in montagem and any(a.startswith("loudnorm=I=-14") for a in montagem)
        assert montagem[-1].endswith(".mp4") and montagem.count("-i") == 2  # a lista de cenas e a trilha
        atual = servicos.projetos.obter(projeto.id)
        assert atual is not None and atual.etapa == "montagem" and atual.configuracoes["final_media_id"] == video.id
        assert atual.configuracoes["quality"]["flashes"]["passed"] is True
        assert not list(servicos.settings.temp_dir.glob("lista-*"))  # a lista temporária foi apagada

    def test_com_transicao_usa_xfade_e_reencoda(self, servicos: Servicos, elenco: list[Any], tmp_path: Path) -> None:
        projeto, _ = _com_audio(servicos, elenco, tmp_path, transition="fade")
        r = montar_o_video(_ctx(servicos), {"project_id": projeto.id, "transition": "fade"})
        montagem = next(a for a in _ffmpeg(servicos).execucoes if "-filter_complex" in a)
        filtro = montagem[montagem.index("-filter_complex") + 1]
        assert "xfade=transition=fade:duration=0.5:offset=4.500" in filtro and "libx264" in montagem
        assert servicos.midias.obter(r["media_id"]) is not None

    def test_refazer_troca_o_video_final_antigo(self, servicos: Servicos, elenco: list[Any], tmp_path: Path) -> None:
        projeto, _ = _com_audio(servicos, elenco, tmp_path)
        primeiro = montar_o_video(_ctx(servicos), {"project_id": projeto.id})["media_id"]
        segundo = montar_o_video(_ctx(servicos), {"project_id": projeto.id})["media_id"]
        assert servicos.midias.obter(primeiro) is None and servicos.midias.obter(segundo) is not None

    def test_flashes_reprovam(self, servicos: Servicos, elenco: list[Any], tmp_path: Path) -> None:
        projeto, _ = _com_audio(servicos, elenco, tmp_path)
        _ffmpeg(servicos).luminancias = {}
        # o vídeo sintético piscando entre escuro e claro 12 vezes por segundo
        piscando = [0.05 if i % 2 else 0.95 for i in range(60)]
        original = _ffmpeg(servicos).extrair_luminancia
        _ffmpeg(servicos).extrair_luminancia = lambda video, amostras_por_s=12: piscando  # type: ignore[method-assign]
        r = montar_o_video(_ctx(servicos), {"project_id": projeto.id})
        assert r["flashes"]["passed"] is False and r["flashes"]["max_per_second"] > 3
        _ffmpeg(servicos).extrair_luminancia = original  # type: ignore[method-assign]

    def test_exige_audio_animacao_e_coerencia(self, servicos: Servicos, elenco: list[Any], tmp_path: Path) -> None:
        projeto, cenas = _pronto_para_animar(servicos, elenco, tmp_path)
        with pytest.raises(ErroParaOUsuario, match="etapa de áudio"):
            montar_o_video(_ctx(servicos), {"project_id": projeto.id})
        animar_cenas(_ctx(servicos), {"project_id": projeto.id})
        montar_audio(_ctx(servicos), {"project_id": projeto.id})
        with pytest.raises(ErroParaOUsuario, match="outra transição"):
            montar_o_video(_ctx(servicos), {"project_id": projeto.id, "transition": "suave"})
        dados = _dados(servicos, cenas[0].id).model_dump()
        dados["timeline"]["duration_s"] = 7.0
        servicos.projetos.atualizar_cena_sem_versao(cenas[0].id, dados)
        with pytest.raises(ErroParaOUsuario, match="mudaram desde que o áudio"):
            montar_o_video(_ctx(servicos), {"project_id": projeto.id})

    def test_cena_sem_clipe(self, servicos: Servicos, elenco: list[Any], tmp_path: Path) -> None:
        projeto, cenas = _com_audio(servicos, elenco, tmp_path)
        dados = _dados(servicos, cenas[1].id).model_dump()
        dados["clip"] = None
        servicos.projetos.atualizar_cena_sem_versao(cenas[1].id, dados)
        with pytest.raises(ErroParaOUsuario, match="cena 2 ainda não tem clipe"):
            montar_o_video(_ctx(servicos), {"project_id": projeto.id})

    def test_trilha_que_sumiu(self, servicos: Servicos, elenco: list[Any], tmp_path: Path) -> None:
        projeto, _ = _com_audio(servicos, elenco, tmp_path)
        audio = servicos.projetos.obter(projeto.id).configuracoes["audio"]  # type: ignore[union-attr]
        servicos.midias.remover(audio["mix_media_id"])
        with pytest.raises(ErroParaOUsuario, match="trilha de áudio sumiu"):
            montar_o_video(_ctx(servicos), {"project_id": projeto.id})
