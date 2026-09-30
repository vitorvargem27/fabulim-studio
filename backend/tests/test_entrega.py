"""Entrega do vídeo: miniaturas, título e tags, versão em outro formato e idioma, e a fila noturna."""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from app.container import Servicos
from app.erros import ErroParaOUsuario
from app.projetos import miniaturas, noturna
from app.projetos.cenas import DadosDaCena
from app.projetos.metadados import (
    metadados_por_ia,
    metadados_simples,
    tags_validas,
    validar_metadados,
)
from app.projetos.miniaturas import (
    ajustar_titulo,
    caixa_do_titulo,
    carregar_fonte,
    compor_miniatura,
    fundo_16_9,
    salvar_jpeg,
)
from app.projetos.variantes import criar_variante_de_formato
from app.tarefas.entrega import gerar_metadados, gerar_miniaturas, gerar_versao_em_outro_idioma, titulo_curto
from app.tarefas.projetos import gerar_storyboard

from .builders_projetos import dar_cenario, personagem_pronto, png_de_fundo, png_de_personagem, projeto_com_cenas
from .conftest import esperar
from .fakes_motores import ContextoDeTeste, ImagemFalsa, TextoFalso

CENAS_DO_JARDIM: list[dict[str, Any]] = [
    {
        "title": "O jardim",
        "duration_s": 5,
        "visual": "um jardim florido",
        "action": "brinca",
        "narration": "Era uma vez um jardim.",
        "dialogue": [{"character_id": None, "text": "Que dia lindo!"}],
    },
    {
        "title": "A chuva",
        "duration_s": 5,
        "visual": "um céu nublado",
        "action": "corre",
        "narration": "Começou a chover.",
    },
    {
        "title": "O arco-íris",
        "duration_s": 5,
        "visual": "um arco-íris",
        "action": "olha",
        "narration": "Surgiu um arco-íris.",
    },
    {"title": "A volta", "duration_s": 5, "visual": "a casa", "action": "volta", "narration": "Hora de voltar."},
]


def _com_cenarios(sv: Servicos, pasta: Path, n: int = 4, **configuracoes: Any) -> tuple[Any, Any, list[Any]]:
    """Lila pronta e um projeto com ``n`` cenas, todas com cenário (é o que a miniatura precisa)."""
    lila = personagem_pronto(sv, pasta, "Lila")
    cenas = [{**c, "characters": [lila.id]} for c in CENAS_DO_JARDIM[:n]]
    for cena in cenas[:1]:
        cena["dialogue"] = [{"character_id": lila.id, "text": "Que dia lindo!"}]
    projeto, criadas = projeto_com_cenas(sv, [lila], cenas, **configuracoes)
    for cena in criadas:
        dar_cenario(sv, pasta, cena)
    return lila, projeto, [sv.projetos.cena(c.id) for c in criadas]


def _ctx(sv: Servicos) -> ContextoDeTeste:
    return ContextoDeTeste(servicos=sv)


# =============================================================================================================================
class TestMiniaturasPuras:
    def test_a_fonte_do_estudio_vem_junto_e_o_negrito_funciona(self) -> None:
        assert miniaturas.FONTE.is_file() and miniaturas.FONTE.stat().st_size > 10_000
        negrito = carregar_fonte(80)
        assert isinstance(negrito, ImageFont.FreeTypeFont)
        padrao = ImageFont.truetype(str(miniaturas.FONTE), 80)

        def tinta(fonte: ImageFont.FreeTypeFont) -> int:
            folha = Image.new("L", (500, 140), 0)
            ImageDraw.Draw(folha).text((10, 10), "Fabulim", font=fonte, fill=255)
            return sum(folha.getdata())

        assert tinta(negrito) > tinta(padrao) * 1.05  # o eixo de peso está em 700: as letras têm mais tinta

    def test_a_licenca_da_fonte_acompanha_o_arquivo(self) -> None:
        licenca = miniaturas.FONTE.parent / "Fredoka-OFL.txt"
        assert licenca.is_file() and "SIL Open Font License" in licenca.read_text(encoding="utf-8")

    def test_cenario_horizontal_preenche_e_vertical_fica_inteiro_no_meio(self, tmp_path: Path) -> None:
        horizontal = fundo_16_9(png_de_fundo(tmp_path / "h.png", (320, 180)))
        assert horizontal.size == (1280, 720)
        vertical = Image.new("RGB", (90, 160))
        for x in range(90):  # metade azul, metade vermelha
            for y in range(160):
                vertical.putpixel((x, y), (0, 0, 255) if x < 45 else (255, 0, 0))
        vertical.save(tmp_path / "v.png")
        montada = fundo_16_9(tmp_path / "v.png")
        assert montada.size == (1280, 720)
        esquerda, direita = montada.getpixel((560, 360)), montada.getpixel((720, 360))
        assert (
            esquerda[2] > 200 and esquerda[0] < 60 and direita[0] > 200 and direita[2] < 60
        )  # a imagem inteira, no meio
        assert (
            montada.getpixel((4, 360))[2] > montada.getpixel((4, 360))[0]
        )  # nas laterais, o fundo desfocado da mesma imagem

    def test_titulo_quebra_em_linhas_e_a_letra_encolhe_para_caber(self) -> None:
        caixa = caixa_do_titulo(1).px()
        linhas, fonte, passo = ajustar_titulo("A Lila e a estrelinha que se perdeu no bosque", caixa)
        assert 1 <= len(linhas) <= 3
        assert all(fonte.getlength(linha) <= caixa[2] - caixa[0] for linha in linhas)
        assert len(linhas) * passo <= caixa[3] - caixa[1]
        assert ajustar_titulo("Lila", caixa)[1].size > fonte.size  # título curto ganha letra maior

    def test_cada_desenho_e_diferente_tem_1280_por_720_e_o_titulo_aparece(self, tmp_path: Path) -> None:
        fundo = png_de_fundo(tmp_path / "f.png")
        recortes = [png_de_personagem(tmp_path / "a.png"), png_de_personagem(tmp_path / "b.png", (20, 20, 230))]
        imagens = [compor_miniatura(fundo, recortes, titulo="A chuva do jardim", variacao=v) for v in range(4)]
        assert all(i.size == (1280, 720) and i.mode == "RGB" for i in imagens)
        assert len({hashlib.md5(i.tobytes()).hexdigest() for i in imagens}) == 4
        caixa = caixa_do_titulo(0).px()
        amarelo = sum(1 for px in imagens[0].crop(caixa).getdata() if px[0] > 240 and 180 < px[1] < 220 and px[2] < 90)
        assert amarelo > 500  # a primeira linha do título é amarela

    def test_a_ordem_dos_personagens_muda_de_uma_rodada_para_outra(self, tmp_path: Path) -> None:
        fundo = png_de_fundo(tmp_path / "f.png")
        a, b = png_de_personagem(tmp_path / "a.png"), png_de_personagem(tmp_path / "b.png", (20, 20, 230))
        primeira = compor_miniatura(fundo, [a, b], titulo="", variacao=0)
        volta = compor_miniatura(fundo, [a, b], titulo="", variacao=4)  # mesmo desenho, personagens trocados
        assert primeira.tobytes() != volta.tobytes()

    def test_sem_titulo_com_um_personagem_e_personagem_largo_demais(self, tmp_path: Path) -> None:
        fundo = png_de_fundo(tmp_path / "f.png")
        largo = Image.new("RGBA", (2400, 300), (0, 0, 0, 0))
        largo.paste(Image.new("RGBA", (2000, 280), (200, 40, 40, 255)), (200, 10))
        largo.save(tmp_path / "largo.png")
        for variacao in range(4):
            imagem = compor_miniatura(fundo, [tmp_path / "largo.png"], titulo="", variacao=variacao)
            assert imagem.size == (1280, 720)  # o que passa da borda é cortado, sem erro
        vazio = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
        vazio.save(tmp_path / "vazio.png")
        assert compor_miniatura(fundo, [tmp_path / "vazio.png"], titulo="oi").size == (1280, 720)

    def test_o_logo_do_estudio_nunca_entra_na_miniatura(self) -> None:
        codigo = inspect.getsource(miniaturas)
        assert "marca/" not in codigo and "fabulim-logo" not in codigo and "fabulim-icone" not in codigo

    def test_salvar_jpeg_cabe_no_limite_do_youtube(self, tmp_path: Path) -> None:
        imagem = compor_miniatura(
            png_de_fundo(tmp_path / "f.png"), [png_de_personagem(tmp_path / "a.png")], titulo="Oi"
        )
        destino = tmp_path / "saida" / "m.jpg"
        salvar_jpeg(imagem, destino)
        assert 1_000 < destino.stat().st_size <= 1_900_000
        with Image.open(destino) as aberta:
            assert aberta.format == "JPEG" and aberta.size == (1280, 720)

    def test_titulo_curto(self) -> None:
        assert titulo_curto("A Lila e a estrelinha | Vídeo infantil") == "A Lila e a estrelinha"
        longo = titulo_curto("A aventura muito comprida da Lila e do Bento pelo bosque encantado das estrelas")
        assert longo.endswith("…") and len(longo) <= 46 and " " in longo


class TestJobDeMiniaturas:
    def test_gera_tres_miniaturas_no_projeto(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, cenas = _com_cenarios(servicos, tmp_path)
        ctx = _ctx(servicos)
        r = gerar_miniaturas(ctx, {"project_id": projeto.id, "count": 3})
        assert len(r["media_ids"]) == 3 and ctx.progressos[-1][0] == 1.0
        midias = [servicos.midias.obter(i) for i in r["media_ids"]]
        assert all(
            m and m.papel == "thumbnail" and m.dono_tipo == "projeto" and m.dono_id == projeto.id for m in midias
        )
        assert all(m and (m.largura, m.altura) == (1280, 720) and m.formato == "jpg" for m in midias)
        assert all(
            m and m.prompt == "A chuva do jardim" and m.metadados["title"] == "A chuva do jardim" for m in midias
        )
        assert [m.metadados["layout"] for m in midias if m] == [0, 1, 2]  # cada uma com um desenho
        cenarios = {m.metadados["scene_id"] for m in midias if m}
        assert len(cenarios) == 3 and cenarios <= {c.id for c in cenas}  # espalhadas por cenas diferentes
        assert all(servicos.midias.caminho_absoluto(m).stat().st_size <= 1_900_000 for m in midias if m)

    def test_o_texto_pedido_vira_o_titulo_da_miniatura(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, _ = _com_cenarios(servicos, tmp_path)
        r = gerar_miniaturas(
            _ctx(servicos), {"project_id": projeto.id, "count": 1, "text": "Lila na chuva | inscreva-se"}
        )
        assert servicos.midias.obter(r["media_ids"][0]).prompt == "Lila na chuva"  # type: ignore[union-attr]

    def test_so_as_cenas_escolhidas(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, cenas = _com_cenarios(servicos, tmp_path)
        r = gerar_miniaturas(_ctx(servicos), {"project_id": projeto.id, "count": 2, "scene_ids": [cenas[2].id]})
        assert {servicos.midias.obter(i).metadados["scene_id"] for i in r["media_ids"]} == {cenas[2].id}  # type: ignore[union-attr]

    def test_sem_storyboard_ou_sem_personagens_explica_o_que_falta(self, servicos: Servicos, tmp_path: Path) -> None:
        lila = personagem_pronto(servicos, tmp_path, "Lila")
        projeto, _ = projeto_com_cenas(servicos, [lila])  # cenas sem cenário
        with pytest.raises(ErroParaOUsuario, match="Gere o storyboard"):
            gerar_miniaturas(_ctx(servicos), {"project_id": projeto.id})
        sem_gente, cenas = projeto_com_cenas(servicos, [], [{"title": "Só o cenário", "characters": []}])
        dar_cenario(servicos, tmp_path, cenas[0])
        with pytest.raises(ErroParaOUsuario, match="não tem personagens"):
            gerar_miniaturas(_ctx(servicos), {"project_id": sem_gente.id})

    def test_personagem_sem_o_png_transparente_avisa(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, _ = _com_cenarios(servicos, tmp_path)
        for recorte in servicos.midias.listar(papeis=("recorte",), limite=50):
            servicos.midias.remover(recorte.id)
        with pytest.raises(ErroParaOUsuario, match="PNG transparente"):
            gerar_miniaturas(_ctx(servicos), {"project_id": projeto.id})

    def test_o_job_confere_o_filtro_de_conteudo_e_o_pedido(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, _ = _com_cenarios(servicos, tmp_path)
        with pytest.raises(ErroParaOUsuario):
            gerar_miniaturas(_ctx(servicos), {"project_id": projeto.id, "text": "Peppa Pig no jardim"})
        with pytest.raises(ErroParaOUsuario, match="incompleto ou inválido"):
            gerar_miniaturas(_ctx(servicos), {"project_id": projeto.id, "count": 99})


# =============================================================================================================================
class TestMetadados:
    def test_a_sugestao_pronta_tem_os_dois_idiomas_e_respeita_os_limites(
        self, servicos: Servicos, tmp_path: Path
    ) -> None:
        _, projeto, cenas = _com_cenarios(servicos, tmp_path)
        dados = [DadosDaCena.model_validate(c.dados) for c in cenas]
        m = metadados_simples(projeto, dados, ["Lila", "Bento"])
        assert set(m) == {"pt-BR", "en"}
        assert m["pt-BR"]["title"] == "A chuva do jardim | Vídeo infantil" and m["en"]["title"].endswith(
            "| Kids cartoon"
        )
        pt, en = m["pt-BR"]["description"], m["en"]["description"]
        assert "Lila e a brincadeira" not in pt and "Lila, Bento" in pt and "crianças de 2 a 5 anos" in pt
        assert "#shorts" in pt and "#shorts" in en and "Characters: Lila, Bento." in en
        assert "Lila brinca no jardim" in pt  # o resumo vem da história (no idioma do projeto)
        assert "Lila brinca" not in en  # no outro idioma não há história traduzida: texto genérico
        assert (
            m["pt-BR"]["tags"][0] == "vídeo infantil"
            and "Lila" in m["pt-BR"]["tags"]
            and "kids video" in m["en"]["tags"]
        )
        assert all(len(t) <= 30 for lang in m.values() for t in lang["tags"]) and len(m["pt-BR"]["tags"]) <= 15

    def test_video_longo_nao_leva_shorts(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, cenas = _com_cenarios(servicos, tmp_path, formato="longo")
        m = metadados_simples(projeto, [DadosDaCena.model_validate(c.dados) for c in cenas], [])
        assert "#shorts" not in m["pt-BR"]["description"] and "Personagens:" not in m["pt-BR"]["description"]

    def test_tags_sem_repetir_sem_hash_e_dentro_dos_limites(self) -> None:
        tags = tags_validas(
            ["#Vídeo Infantil", "video infantil", "  desenho  ", "x" * 80, "", None, "Peppa Pig", "lila"]
        )
        assert tags == [
            "Vídeo Infantil",
            "desenho",
            "x" * 30,
            "lila",
        ]  # sem repetir (acento e caixa), sem marca, cortada em 30
        muitas = tags_validas([f"tag número {i}" for i in range(40)])
        assert len(muitas) == 15
        enormes = tags_validas([f"{i:02d}" + "y" * 28 for i in range(40)])
        assert sum(len(t) + 1 for t in enormes) <= 450  # o YouTube aceita 500 caracteres no total
        assert tags_validas("não é lista") == [] and tags_validas(["a"], extras=["b", "a"]) == ["a", "b"]

    def test_o_modelo_local_escreve_e_o_resultado_e_validado(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, cenas = _com_cenarios(servicos, tmp_path)
        dados = [DadosDaCena.model_validate(c.dados) for c in cenas]
        texto = TextoFalso(
            [
                {
                    "pt": {
                        "title": "Lila e a chuva de verão " + "muito " * 30,
                        "description": "Lila brinca. Chove!",
                        "tags": ["chuva", "#Lila", "chuva"],
                    },
                    "en": {"title": "Peppa Pig in the rain", "description": "", "tags": []},
                }
            ]
        )
        m = metadados_por_ia(_ctx(servicos), texto, projeto, dados, ["Lila"])
        assert len(m["pt-BR"]["title"]) <= 100 and m["pt-BR"]["title"].startswith("Lila e a chuva")
        assert m["pt-BR"]["description"] == "Lila brinca. Chove!" and m["pt-BR"]["tags"] == ["chuva", "Lila"]
        # o inglês veio com marca de terceiros, sem descrição e sem tags: cai no modelo pronto
        assert m["en"]["title"] == "A chuva do jardim | Kids cartoon" and "Characters: Lila." in m["en"]["description"]
        assert "kids video" in m["en"]["tags"]
        pedido = texto.chamadas[0]
        assert "Lila brinca no jardim" in pedido["dados"] and "apenas dado" in pedido["sistema"]

    def test_o_job_guarda_no_projeto(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, _ = _com_cenarios(servicos, tmp_path)
        servicos.motores.texto = TextoFalso(
            [
                {
                    "pt": {"title": "Lila e a chuva", "description": "Uma tarde de chuva.", "tags": ["chuva"]},
                    "en": {"title": "Lila and the rain", "description": "A rainy afternoon.", "tags": ["rain"]},
                }
            ]
        )
        r = gerar_metadados(_ctx(servicos), {"project_id": projeto.id})
        assert r == {"origin": "ia", "warnings": []}
        m = servicos.projetos.obter(projeto.id).configuracoes["metadata"]  # type: ignore[union-attr]
        assert m["source"] == "ia" and m["generated_at"] and m["en"]["title"] == "Lila and the rain"
        assert m["pt-BR"]["tags"] == ["chuva"]

    def test_sem_o_modelo_local_usa_o_modelo_pronto_e_avisa(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, _ = _com_cenarios(servicos, tmp_path)
        servicos.motores.texto = TextoFalso(indisponivel="Ollama fora do ar")
        r = gerar_metadados(_ctx(servicos), {"project_id": projeto.id})
        assert r["origin"] == "simples" and any("Usei o modelo pronto" in a for a in r["warnings"])
        assert any("genérica" in a for a in r["warnings"])
        assert servicos.projetos.obter(projeto.id).configuracoes["metadata"]["source"] == "simples"  # type: ignore[union-attr]
        r2 = gerar_metadados(_ctx(servicos), {"project_id": projeto.id, "mode": "simples"})
        assert r2["origin"] == "simples"

    def test_editar_a_mao_valida_e_mescla(self) -> None:
        atuais = {
            "pt-BR": {"title": "A", "description": "b", "tags": ["c"]},
            "en": {"title": "D", "description": "e", "tags": []},
            "source": "ia",
        }
        novos = validar_metadados(
            {"en": {"title": " New   title ", "description": "Line one\r\n\r\n\r\n\r\nLine two", "tags": ["#x", "y"]}},
            atuais,
        )
        assert novos["pt-BR"] == atuais["pt-BR"] and novos["source"] == "ia"
        assert novos["en"] == {"title": "New title", "description": "Line one\n\nLine two", "tags": ["x", "y"]}
        with pytest.raises(ValueError, match="título não pode ficar vazio"):
            validar_metadados({"en": {"title": "  ", "description": "", "tags": []}})
        with pytest.raises(ValueError):
            validar_metadados({"en": {"title": "Peppa Pig", "description": "", "tags": []}})
        with pytest.raises(ValueError, match="precisam ter título"):
            validar_metadados({"pt-BR": "texto solto"})
        assert validar_metadados({"fr": {"title": "x"}}, None) == {}  # idioma desconhecido é ignorado


# =============================================================================================================================
class TestVarianteDeFormato:
    def test_o_mesmo_video_em_outro_formato(self, servicos: Servicos, tmp_path: Path) -> None:
        lila, projeto, cenas = _com_cenarios(servicos, tmp_path)
        servicos.projetos.atualizar(
            projeto.id,
            aprovacoes={"enredo": True, "roteiro": True, "storyboard": True},
            etapa="animacao",
            musica={"style": "calma"},
            configuracoes={"transition": "fade", "fps": 24, "narrator": {"id": "pm_alex"}, "final_media_id": "x" * 32},
        )
        for cena in cenas:  # aprovadas e com clipe
            dados = DadosDaCena.model_validate(servicos.projetos.cena(cena.id).dados).model_dump()  # type: ignore[union-attr]
            dados["approved"] = {"roteiro": True, "storyboard": True, "animacao": True}
            dados["layout"] = [{"personagem_id": lila.id, "x": 0.5, "base_y": 0.9, "altura": 0.4}]
            servicos.projetos.atualizar_cena_sem_versao(cena.id, dados)
        origem = servicos.projetos.obter(projeto.id)
        novo, avisos = criar_variante_de_formato(servicos, origem, "longo")  # type: ignore[arg-type]
        assert (
            novo.formato == "longo"
            and novo.titulo == "A chuva do jardim (vídeo longo)"
            and novo.origem_id == projeto.id
        )
        assert novo.enredo["format"] == "longo" and novo.idioma == "pt-BR" and novo.personagens == [lila.id]
        assert novo.musica == {"style": "calma"} and novo.configuracoes == {
            "transition": "fade",
            "fps": 24,
            "narrator": {"id": "pm_alex"},
        }
        assert novo.aprovacoes == {"enredo": True, "roteiro": True} and novo.etapa == "storyboard" and avisos == []
        assert novo.duracao_alvo_s == 12
        novas = [DadosDaCena.model_validate(c.dados) for c in servicos.projetos.cenas(novo.id)]
        assert [d.title for d in novas] == ["O jardim", "A chuva", "O arco-íris", "A volta"]
        for d in novas:
            assert d.background is None and d.candidates == [] and d.keyframe_media_id is None and d.clip is None
            assert d.layout is None and d.seed_hint == 5 and d.approved == {"roteiro": True}
        # o original não mudou
        assert servicos.projetos.obter(projeto.id).aprovacoes["storyboard"] is True  # type: ignore[union-attr]
        assert DadosDaCena.model_validate(servicos.projetos.cena(cenas[0].id).dados).background is not None  # type: ignore[union-attr]
        assert [p.id for p in servicos.projetos.variantes_de(projeto.id)] == [novo.id]

    def test_o_cenario_novo_parte_da_semente_do_original(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, _ = _com_cenarios(servicos, tmp_path, n=2)
        servicos.projetos.atualizar(projeto.id, aprovacoes={"enredo": True, "roteiro": True})
        novo, _ = criar_variante_de_formato(servicos, servicos.projetos.obter(projeto.id), "longo")  # type: ignore[arg-type]
        r = gerar_storyboard(_ctx(servicos), {"project_id": novo.id, "mode": "faltantes"})
        assert r["scenes"] == 2
        imagem = servicos.motores.imagem
        assert isinstance(imagem, ImagemFalsa)
        assert [p.seed for p in imagem.pedidos] == [5, 5]  # a mesma semente do cenário original
        assert (imagem.pedidos[0].largura, imagem.pedidos[0].altura) == (1024, 576) or imagem.pedidos[
            0
        ].largura > imagem.pedidos[0].altura

    def test_de_longo_para_short_avisa_quando_passa_de_60_segundos(self, servicos: Servicos, tmp_path: Path) -> None:
        lila = personagem_pronto(servicos, tmp_path, "Lila")
        cenas = [{"title": f"Cena {i}", "duration_s": 10, "characters": [lila.id]} for i in range(8)]
        projeto, _ = projeto_com_cenas(servicos, [lila], cenas, formato="longo", duracao_alvo_s=120)
        novo, avisos = criar_variante_de_formato(servicos, projeto, "short")
        assert novo.formato == "short" and novo.duracao_alvo_s == 60
        assert any("80 s" in a and "Short vai até 60 s" in a for a in avisos)
        assert any("roteiro do original ainda não foi aprovado" in a for a in avisos) and novo.etapa == "enredo"

    def test_recusa_o_mesmo_formato_e_projeto_sem_cenas(self, servicos: Servicos, tmp_path: Path) -> None:
        lila = personagem_pronto(servicos, tmp_path, "Lila")
        projeto, _ = projeto_com_cenas(servicos, [lila])
        with pytest.raises(ErroParaOUsuario, match="já está nesse formato"):
            criar_variante_de_formato(servicos, projeto, "short")
        vazio, _ = projeto_com_cenas(servicos, [lila], [])
        with pytest.raises(ErroParaOUsuario, match="Gere o roteiro"):
            criar_variante_de_formato(servicos, vazio, "longo")


# =============================================================================================================================
TRADUCAO_DA_HISTORIA = {
    "title": "Lila and the rain",
    "theme": "friendship",
    "story": "Lila plays in the garden. Then it rains.",
}
TRADUCAO_DAS_CENAS = {
    "scenes": [
        {
            "title": "The garden",
            "narration": "Once upon a time there was a garden.",
            "lyrics": "",
            "dialogue": ["What a lovely day!"],
        },
        {"title": "The rain", "narration": "It started to rain.", "lyrics": "", "dialogue": []},
    ]
}


def _duas_cenas_aprovadas(servicos: Servicos, tmp_path: Path) -> tuple[Any, Any, list[Any]]:
    lila, projeto, cenas = _com_cenarios(servicos, tmp_path, n=2)
    for cena in cenas:
        dados = DadosDaCena.model_validate(servicos.projetos.cena(cena.id).dados).model_dump()  # type: ignore[union-attr]
        dados["approved"] = {"roteiro": True, "storyboard": True, "animacao": True}
        dados["clip"] = {
            "media_id": dados["background"]["media_id"],
            "render_hash": "x",
            "quality": "final",
            "duration_s": 5,
        }
        dados["timeline"] = {"duration_s": 5.0}
        servicos.projetos.atualizar_cena_sem_versao(cena.id, dados)
    servicos.projetos.atualizar(projeto.id, aprovacoes={"enredo": True, "roteiro": True, "storyboard": True})
    return lila, servicos.projetos.obter(projeto.id), cenas


class TestVersaoEmOutroIdioma:
    def test_traduz_o_texto_e_reaproveita_o_visual(self, servicos: Servicos, tmp_path: Path) -> None:
        lila, projeto, cenas = _duas_cenas_aprovadas(servicos, tmp_path)
        servicos.motores.texto = TextoFalso([TRADUCAO_DA_HISTORIA, TRADUCAO_DAS_CENAS])
        r = gerar_versao_em_outro_idioma(_ctx(servicos), {"project_id": projeto.id})
        assert r["language"] == "en" and r["scenes"] == 2 and r["warnings"] == []
        novo = servicos.projetos.obter(r["project_id"])
        assert (
            novo is not None
            and novo.idioma == "en"
            and novo.origem_id == projeto.id
            and novo.titulo == "Lila and the rain"
        )
        assert novo.enredo["language"] == "en" and novo.enredo["story"].startswith("Lila plays in the garden")
        assert novo.personagens == [lila.id] and novo.formato == projeto.formato
        assert novo.aprovacoes == {"enredo": True} and novo.etapa == "roteiro"
        assert "narrator" not in novo.configuracoes  # o narrador padrão do idioma vale
        novas = servicos.projetos.cenas(novo.id)
        dados = [DadosDaCena.model_validate(c.dados) for c in novas]
        assert [d.title for d in dados] == ["The garden", "The rain"]
        assert (
            dados[0].narration == "Once upon a time there was a garden."
            and dados[0].dialogue[0].text == "What a lovely day!"
        )
        assert dados[0].dialogue[0].character_id == lila.id  # quem fala continua sendo o mesmo personagem
        assert dados[0].action == "brinca" and dados[0].visual == "um jardim florido"  # o que não é falado não muda
        for antiga, nova, d in zip(cenas, novas, dados, strict=True):
            assert d.clip is None and d.timeline is None  # a duração muda com a fala: a animação é refeita
            assert d.approved == {"storyboard": True}  # o cenário continua aprovado; o roteiro traduzido não
            original = DadosDaCena.model_validate(servicos.projetos.cena(antiga.id).dados)  # type: ignore[union-attr]
            assert d.background is not None and d.background.media_id != original.background.media_id  # type: ignore[union-attr]
            copia = servicos.midias.obter(d.background.media_id)
            assert (
                copia is not None
                and copia.dono_id == nova.id
                and copia.metadados["copied_from"] == original.background.media_id
            )  # type: ignore[union-attr]
            assert servicos.midias.caminho_absoluto(copia).is_file()
        # o original não mudou
        assert servicos.projetos.obter(projeto.id).idioma == "pt-BR"  # type: ignore[union-attr]
        assert DadosDaCena.model_validate(servicos.projetos.cena(cenas[0].id).dados).clip is not None  # type: ignore[union-attr]

    def test_apagar_o_original_nao_estraga_a_versao(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, cenas = _duas_cenas_aprovadas(servicos, tmp_path)
        servicos.motores.texto = TextoFalso([TRADUCAO_DA_HISTORIA, TRADUCAO_DAS_CENAS])
        r = gerar_versao_em_outro_idioma(_ctx(servicos), {"project_id": projeto.id})
        for cena in cenas:
            servicos.midias.remover_do_dono("cena", cena.id)
        for cena in servicos.projetos.cenas(r["project_id"]):
            fundo = DadosDaCena.model_validate(cena.dados).background
            assert (
                fundo is not None and servicos.midias.caminho_absoluto(servicos.midias.obter(fundo.media_id)).is_file()
            )  # type: ignore[arg-type]

    def test_de_ingles_para_portugues_com_o_idioma_pedido(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, _ = _com_cenarios(servicos, tmp_path, n=2, idioma="en")
        servicos.motores.texto = TextoFalso([TRADUCAO_DA_HISTORIA, TRADUCAO_DAS_CENAS])
        r = gerar_versao_em_outro_idioma(_ctx(servicos), {"project_id": projeto.id, "language": "pt-BR"})
        assert r["language"] == "pt-BR"
        instrucao = servicos.motores.texto.chamadas[0]["sistema"]  # type: ignore[attr-defined]
        assert "inglês para o português do Brasil" in instrucao

    def test_sem_o_modelo_local_os_textos_ficam_e_avisa(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, _ = _duas_cenas_aprovadas(servicos, tmp_path)
        servicos.motores.texto = TextoFalso(indisponivel="Ollama fora do ar")
        r = gerar_versao_em_outro_idioma(_ctx(servicos), {"project_id": projeto.id})
        assert any("Os textos ficaram no idioma original" in a for a in r["warnings"])
        novo = servicos.projetos.obter(r["project_id"])
        assert novo is not None and novo.idioma == "en" and novo.titulo == "A chuva do jardim (EN)"
        assert (
            DadosDaCena.model_validate(servicos.projetos.cenas(novo.id)[0].dados).narration == "Era uma vez um jardim."
        )
        simples = gerar_versao_em_outro_idioma(_ctx(servicos), {"project_id": projeto.id, "mode": "simples"})
        assert any("copiados sem tradução" in a for a in simples["warnings"])

    def test_traducao_incompleta_ou_barrada_pelo_filtro_mantem_o_original_e_avisa(
        self, servicos: Servicos, tmp_path: Path
    ) -> None:
        _, projeto, _ = _duas_cenas_aprovadas(servicos, tmp_path)
        cenas_ruins = {
            "scenes": [
                {
                    "title": "The garden",
                    "narration": "Peppa Pig came to play.",
                    "lyrics": "",
                    "dialogue": [],
                },  # marca + falta a fala
            ]  # e falta a segunda cena
        }
        servicos.motores.texto = TextoFalso([TRADUCAO_DA_HISTORIA, cenas_ruins])
        r = gerar_versao_em_outro_idioma(_ctx(servicos), {"project_id": projeto.id})
        avisos = " | ".join(r["warnings"])
        assert "barrada pelo filtro de conteúdo" in avisos and "voltou com menos falas do que tinha" in avisos
        dados = [DadosDaCena.model_validate(c.dados) for c in servicos.projetos.cenas(r["project_id"])]
        assert (
            dados[0].narration == "Era uma vez um jardim." and dados[0].dialogue[0].text == "Que dia lindo!"
        )  # original
        assert dados[1].title == "A chuva"  # a cena que o modelo esqueceu

    def test_recusa_mesmo_idioma_e_projeto_sem_cenas(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, _ = _duas_cenas_aprovadas(servicos, tmp_path)
        with pytest.raises(ErroParaOUsuario, match="já está nesse idioma"):
            gerar_versao_em_outro_idioma(_ctx(servicos), {"project_id": projeto.id, "language": "pt-BR"})
        lila = personagem_pronto(servicos, tmp_path, "Bento")
        vazio, _ = projeto_com_cenas(servicos, [lila], [])
        with pytest.raises(ErroParaOUsuario, match="Gere o roteiro"):
            gerar_versao_em_outro_idioma(_ctx(servicos), {"project_id": vazio.id})

    def test_o_filtro_barra_a_historia_do_original(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, _ = _duas_cenas_aprovadas(servicos, tmp_path)
        servicos.projetos.atualizar(projeto.id, enredo={**projeto.enredo, "story": "Lila encontra a Peppa Pig."})
        with pytest.raises(ErroParaOUsuario):
            gerar_versao_em_outro_idioma(_ctx(servicos), {"project_id": projeto.id})


# =============================================================================================================================
def _no_estagio(sv: Servicos, pasta: Path, nome: str, estagio: str) -> Any:
    """Um projeto pronto até o ponto pedido: roteiro, storyboard, animacao, audio (aprovados) ou nada."""
    lila = personagem_pronto(sv, pasta, f"Lila {nome}")
    projeto, cenas = projeto_com_cenas(sv, [lila])
    ordem = ["enredo", "roteiro", "storyboard", "animacao", "audio"]
    aprovadas = ordem[: ordem.index(estagio) + 1] if estagio in ordem else []
    if estagio != "nada" and estagio != "roteiro":
        for cena in cenas:
            fundo_id = dar_cenario(sv, pasta, cena, f"fundo-{nome}")
            if estagio in ("animacao", "audio"):  # a animação já foi feita: cada cena tem o seu clipe
                dados = DadosDaCena.model_validate(sv.projetos.cena(cena.id).dados).model_dump()  # type: ignore[union-attr]
                dados["clip"] = {"media_id": fundo_id, "render_hash": "x", "quality": "final", "duration_s": 5}
                sv.projetos.atualizar_cena_sem_versao(cena.id, dados)
    sv.projetos.atualizar(projeto.id, aprovacoes=dict.fromkeys(aprovadas, True))
    return sv.projetos.obter(projeto.id)


class TestFilaNoturna:
    def test_o_plano_pede_o_proximo_trabalho_liberado_pelas_aprovacoes(
        self, servicos: Servicos, tmp_path: Path
    ) -> None:
        a = _no_estagio(servicos, tmp_path, "a", "roteiro")  # roteiro aprovado, sem cenários
        b = _no_estagio(servicos, tmp_path, "b", "storyboard")  # cenários aprovados, sem clipes
        c = _no_estagio(servicos, tmp_path, "c", "animacao")  # animação aprovada, sem áudio
        d = _no_estagio(servicos, tmp_path, "d", "audio")  # áudio aprovado, sem vídeo final
        _no_estagio(servicos, tmp_path, "e", "nada")  # nada aprovado: nada a fazer
        pronto = _no_estagio(servicos, tmp_path, "f", "audio")
        servicos.projetos.atualizar(  # já tem o áudio e o vídeo final
            pronto.id, configuracoes={"final_media_id": "y" * 32, "audio": {"mix_media_id": "z" * 32}}
        )
        plano = {i.projeto_id: (i.etapa, i.tipo) for i in noturna.plano_da_noite(servicos)}
        assert plano == {
            a.id: ("storyboard", "projeto.storyboard"),
            b.id: ("animacao", "projeto.animar"),
            c.id: ("audio", "projeto.audio"),
            d.id: ("montagem", "projeto.montar"),
        }
        assert noturna.plano_da_noite(servicos, [a.id])[0].para_api() == {
            "project_id": a.id,
            "title": "A chuva do jardim",
            "stage": "storyboard",
            "stage_label": "cenários (storyboard)",
            "kind": "projeto.storyboard",
            "blocked_by": None,
        }

    def test_a_noite_nunca_aprova_nada(self, servicos: Servicos, tmp_path: Path) -> None:
        a = _no_estagio(servicos, tmp_path, "a", "roteiro")
        antes = dict(a.aprovacoes)
        jobs, ignorados = noturna.enfileirar_a_noite(servicos)
        assert len(jobs) == 1 and ignorados == []
        assert servicos.projetos.obter(a.id).aprovacoes == antes  # type: ignore[union-attr]

    def test_enfileira_com_os_parametros_de_cada_etapa(self, servicos: Servicos, tmp_path: Path) -> None:
        a = _no_estagio(servicos, tmp_path, "a", "roteiro")
        b = _no_estagio(servicos, tmp_path, "b", "storyboard")
        jobs, _ = noturna.enfileirar_a_noite(servicos)
        por_tipo = {j.kind: j for j in jobs}
        assert por_tipo["projeto.storyboard"].params == {
            "project_id": a.id,
            "mode": "faltantes",
            "variations": 1,
            "quality": "padrao",
        }
        assert por_tipo["projeto.animar"].params == {"project_id": b.id, "draft": False, "force": False}
        assert por_tipo["projeto.animar"].title == "Fila noturna: animação das cenas de «A chuva do jardim»"

    def test_o_que_ja_esta_na_fila_ou_sem_motor_fica_de_fora_com_o_motivo(
        self, servicos: Servicos, tmp_path: Path
    ) -> None:
        a = _no_estagio(servicos, tmp_path, "a", "roteiro")
        b = _no_estagio(servicos, tmp_path, "b", "storyboard")
        noturna.enfileirar_a_noite(servicos, [a.id])
        servicos.motores.ffmpeg = servicos.motores.ffmpeg.__class__(indisponivel="ffmpeg não instalado")  # type: ignore[call-arg]
        jobs, ignorados = noturna.enfileirar_a_noite(servicos)
        assert jobs == []
        motivos = {i.projeto_id: i.bloqueio for i in ignorados}
        assert motivos[a.id] == "Já está na fila." and "ffmpeg" in (motivos[b.id] or "")


# =============================================================================================================================
class TestRotas:
    def test_miniaturas_pela_api(self, client_com_worker: TestClient, servicos: Servicos, tmp_path: Path) -> None:
        c = client_com_worker
        lila = personagem_pronto(servicos, tmp_path, "Lila")
        projeto, cenas = projeto_com_cenas(servicos, [lila])
        assert c.post(f"/api/projects/{projeto.id}/thumbnails", json={}).status_code == 409  # sem storyboard
        for cena in cenas:
            dar_cenario(servicos, tmp_path, cena)
        assert c.post(f"/api/projects/{projeto.id}/thumbnails", json={"count": 9}).status_code == 422
        assert c.post(f"/api/projects/{projeto.id}/thumbnails", json={"scene_ids": [lila.id]}).status_code == 422
        ruim = c.post(f"/api/projects/{projeto.id}/thumbnails", json={"text": "Peppa Pig"})
        assert ruim.status_code == 422
        r = c.post(f"/api/projects/{projeto.id}/thumbnails", json={"count": 2})
        assert r.status_code == 202 and r.json()["title"] == "Miniaturas de «A chuva do jardim»"
        assert esperar(lambda: c.get(f"/api/jobs/{r.json()['id']}").json()["status"] == "done")
        miniaturas_do_projeto = c.get(f"/api/projects/{projeto.id}").json()["files"]["thumbnails"]
        assert len(miniaturas_do_projeto) == 2 and miniaturas_do_projeto[0]["width"] == 1280
        assert c.get(miniaturas_do_projeto[0]["url"]).headers["content-type"] == "image/jpeg"
        apagar = c.delete(f"/api/projects/{projeto.id}/thumbnails/{miniaturas_do_projeto[0]['id']}")
        assert apagar.json() == {"deleted": True}
        assert len(c.get(f"/api/projects/{projeto.id}").json()["files"]["thumbnails"]) == 1
        assert c.delete(f"/api/projects/{projeto.id}/thumbnails/{'0' * 32}").status_code == 404
        principal = lila.imagem_principal_id
        assert (
            c.delete(f"/api/projects/{projeto.id}/thumbnails/{principal}").status_code == 404
        )  # não é miniatura deste projeto

    def test_metadados_pela_api(self, client_com_worker: TestClient, servicos: Servicos, tmp_path: Path) -> None:
        c = client_com_worker
        lila = personagem_pronto(servicos, tmp_path, "Lila")
        vazio, _ = projeto_com_cenas(servicos, [lila], [])
        assert c.post(f"/api/projects/{vazio.id}/metadata", json={}).status_code == 409
        projeto, _ = projeto_com_cenas(servicos, [lila])
        servicos.motores.texto = TextoFalso(indisponivel="Ollama fora do ar")
        assert c.post(f"/api/projects/{projeto.id}/metadata", json={}).status_code == 503  # o modo IA precisa do modelo
        r = c.post(f"/api/projects/{projeto.id}/metadata", json={"mode": "simples"})
        assert r.status_code == 202
        assert esperar(lambda: c.get(f"/api/jobs/{r.json()['id']}").json()["status"] == "done")
        detalhe = c.get(f"/api/projects/{projeto.id}").json()
        assert detalhe["metadata"]["source"] == "simples" and detalhe["metadata"]["en"]["title"].endswith(
            "Kids cartoon"
        )
        salvo = c.put(
            f"/api/projects/{projeto.id}/metadata",
            json={"texts": {"en": {"title": "Lila in the rain", "description": "Rain!", "tags": ["rain", "#kids"]}}},
        )
        assert salvo.status_code == 200
        m = salvo.json()["metadata"]
        assert m["source"] == "manual" and m["en"] == {
            "title": "Lila in the rain",
            "description": "Rain!",
            "tags": ["rain", "kids"],
        }
        assert m["pt-BR"]["title"].endswith("Vídeo infantil")  # o idioma que não foi enviado continua
        assert (
            c.put(
                f"/api/projects/{projeto.id}/metadata", json={"texts": {"en": {"title": "", "description": ""}}}
            ).status_code
            == 422
        )
        assert c.put(f"/api/projects/{projeto.id}/metadata", json={"texts": {}}).status_code == 422
        assert c.put(f"/api/projects/{'0' * 32}/metadata", json={"texts": {"en": {"title": "x"}}}).status_code == 404

    def test_versao_em_outro_idioma_e_variante_pela_api(
        self, client_com_worker: TestClient, servicos: Servicos, tmp_path: Path
    ) -> None:
        c = client_com_worker
        _, projeto, _ = _duas_cenas_aprovadas(servicos, tmp_path)
        assert c.post(f"/api/projects/{projeto.id}/language-version", json={"language": "pt-BR"}).status_code == 422
        servicos.motores.texto = TextoFalso(indisponivel="fora")
        assert c.post(f"/api/projects/{projeto.id}/language-version", json={}).status_code == 503
        servicos.motores.texto = TextoFalso([TRADUCAO_DA_HISTORIA, TRADUCAO_DAS_CENAS])
        r = c.post(f"/api/projects/{projeto.id}/language-version", json={})
        assert r.status_code == 202 and r.json()["title"] == "Versão em inglês de «A chuva do jardim»"
        assert esperar(lambda: c.get(f"/api/jobs/{r.json()['id']}").json()["status"] == "done")
        novo_id = c.get(f"/api/jobs/{r.json()['id']}").json()["result"]["project_id"]
        assert c.get(f"/api/projects/{novo_id}").json()["project"]["language"] == "en"
        assert [v["language"] for v in c.get(f"/api/projects/{projeto.id}").json()["variants"]] == ["en"]
        v = c.post(f"/api/projects/{projeto.id}/variant", json={"format": "longo"})
        assert (
            v.status_code == 201
            and v.json()["project"]["format"] == "longo"
            and v.json()["project"]["origin_id"] == projeto.id
        )
        assert c.post(f"/api/projects/{projeto.id}/variant", json={"format": "short"}).status_code == 409
        assert c.post(f"/api/projects/{projeto.id}/variant", json={"format": "vertical"}).status_code == 422

    def test_fila_noturna_pela_api(self, client: TestClient, servicos: Servicos, tmp_path: Path) -> None:
        a = _no_estagio(servicos, tmp_path, "a", "roteiro")
        b = _no_estagio(servicos, tmp_path, "b", "storyboard")
        plano = client.get("/api/projects/night-plan").json()["items"]
        assert {i["project_id"]: i["stage"] for i in plano} == {a.id: "storyboard", b.id: "animacao"}
        r = client.post("/api/projects/night-queue", json={"project_ids": [a.id]})
        assert r.status_code == 202
        assert [j["kind"] for j in r.json()["queued"]] == ["projeto.storyboard"] and r.json()["skipped"] == []
        de_novo = client.post("/api/projects/night-queue", json={"project_ids": [a.id]}).json()
        assert de_novo["queued"] == [] and de_novo["skipped"][0]["blocked_by"] == "Já está na fila."
        tudo = client.post("/api/projects/night-queue", json={}).json()
        assert [j["kind"] for j in tudo["queued"]] == ["projeto.animar"]
        assert client.post("/api/projects/night-queue", json={"project_ids": ["x"] * 51}).status_code == 422
