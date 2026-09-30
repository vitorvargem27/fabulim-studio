"""Animação de cena: presets de movimento, câmera, layout, volume da fala e o renderizador de quadros."""

from __future__ import annotations

import math
import threading
from pathlib import Path
from typing import cast

import numpy as np
import pytest
import soundfile as sf
from PIL import Image, ImageDraw

from app.animacao.camera import MOVIMENTOS_DE_CAMERA, ZOOM_MAXIMO, camera_em, folga
from app.animacao.efeitos import brilhos_da_cena, desenhar_brilhos, desenhar_chuva
from app.animacao.envelope import combinar_envelopes, envelope_de_audio
from app.animacao.layout import (
    ItemDeLayout,
    acao_do_texto,
    altura_do_personagem,
    compor_layout,
    efeitos_do_texto,
    escolher_pose,
)
from app.animacao.presets import (
    ACOES,
    DURACAO_DA_ENTRADA,
    ENTRADAS,
    Transformacao,
    combinar,
    ease_in_out,
    ease_out_back,
    ease_out_cubic,
    pular,
    pulso_da_fala,
    transformacao_em,
)
from app.animacao.render import (
    CamadaDeRender,
    CenaDeRender,
    RenderizadorDeCena,
    quadro_de_capa,
    renderizar_cena,
)
from app.erros import ErroParaOUsuario
from app.jobs.worker import JobCanceled
from app.motores.ffmpeg import Ffmpeg
from app.motores.tipos import MotorFalhou

from .fakes_motores import ContextoDeTeste, ContextoReal, FfmpegFalso


class TestPresets:
    @pytest.mark.parametrize("nome", sorted(ACOES))
    def test_todo_movimento_fica_dentro_de_limites_seguros(self, nome: str) -> None:
        for t in np.linspace(0, 12, 241):
            tr = ACOES[nome](float(t), 12.0, 0.3)
            assert 0.85 <= tr.sx <= 1.15 and 0.85 <= tr.sy <= 1.15, (nome, t, tr)
            assert abs(tr.rot) <= 10 and abs(tr.dy) <= 0.3 and abs(tr.dxf) <= 0.2 and tr.alfa == 1.0

    def test_respirar_oscila_em_volta_de_1(self) -> None:
        valores = [ACOES["respirar"](t / 10, 5, 0).sy for t in range(0, 60)]
        assert min(valores) < 1 < max(valores) and max(valores) - min(valores) == pytest.approx(0.04, abs=0.005)

    def test_pular_sai_do_chao_e_volta(self) -> None:
        assert pular(0.0, 5, 0) == Transformacao(sx=1.0, sy=1.0)  # começa no chão
        dys = [pular(t / 100, 5, 0).dy for t in range(0, 110)]
        assert max(dys) == 0.0 and min(dys) == pytest.approx(-0.22, abs=0.01)  # nunca afunda; sobe 22% da altura
        agachado = pular(0.07 * 1.1, 5, 0)  # antes do salto
        assert agachado.sy < 1 < agachado.sx
        no_ar = pular(0.5 * 1.1, 5, 0)
        assert no_ar.dy < -0.2 and no_ar.sy > 1 > no_ar.sx  # estica no ar

    def test_andar_atravessa_a_cena(self) -> None:
        assert ACOES["andar"](0.0, 4, 0).dxf == pytest.approx(-0.18)
        assert ACOES["andar"](2.0, 4, 0).dxf == pytest.approx(0.0)
        assert ACOES["andar"](4.0, 4, 0).dxf == pytest.approx(0.18)

    def test_acao_desconhecida_vira_respirar(self) -> None:
        assert transformacao_em("voar-de-moto", "nenhuma", 1.0, 5, 0) == transformacao_em(
            "respirar", "nenhuma", 1.0, 5, 0
        )

    def test_entradas(self) -> None:
        esq = transformacao_em("respirar", "deslizar_esq", 0.0, 5, 0)
        dir_ = transformacao_em("respirar", "deslizar_dir", 0.0, 5, 0)
        assert esq.dxf == pytest.approx(-0.7) and dir_.dxf == pytest.approx(0.7)
        assert transformacao_em("respirar", "deslizar_esq", DURACAO_DA_ENTRADA, 5, 0).dxf == 0.0  # acabou
        assert transformacao_em("respirar", "aparecer", 0.0, 5, 0).alfa == 0.0
        assert transformacao_em("respirar", "aparecer", 0.6, 5, 0).alfa == pytest.approx(1.0)
        pequeno = transformacao_em("respirar", "crescer", 0.0, 5, 0)
        assert pequeno.sx == pytest.approx(0.3, abs=0.02) and pequeno.alfa == 0.0
        passou = transformacao_em("respirar", "crescer", 0.35, 5, 0)
        assert passou.sx > 1.0  # passa um pouco do tamanho e volta ("molinha")
        pulo = [transformacao_em("respirar", "pular_entrada", i / 100, 5, 0).dy for i in range(0, 70)]
        assert min(pulo) < -0.2 and set(ENTRADAS) >= {"nenhuma", "crescer"}

    def test_pulso_da_fala_acompanha_o_volume(self) -> None:
        base = Transformacao()
        alto, baixo = pulso_da_fala(base, 1.0), pulso_da_fala(base, 0.2)
        assert alto.sy > baixo.sy > 1 and alto.sx < baixo.sx < 1 and alto.dy < baixo.dy < 0
        assert pulso_da_fala(base, 5.0) == pulso_da_fala(base, 1.0)  # o volume é limitado a 1
        assert (
            transformacao_em("respirar", "nenhuma", 1.0, 5, 0, volume=0.0).sy
            == transformacao_em("respirar", "nenhuma", 1.0, 5, 0).sy
        )

    def test_combinar_soma_deslocamentos_e_multiplica_escalas(self) -> None:
        r = combinar(Transformacao(dy=-0.1, sx=1.1, rot=2, alfa=0.5), Transformacao(dy=-0.05, sx=0.9, rot=3, alfa=0.5))
        assert (r.dy, r.rot, r.alfa) == (pytest.approx(-0.15), 5, 0.25) and r.sx == pytest.approx(0.99)

    def test_curvas_de_suavizacao(self) -> None:
        for curva in (ease_out_cubic, ease_in_out, ease_out_back):
            assert curva(0.0) == pytest.approx(0.0) and curva(1.0) == pytest.approx(1.0)
            assert curva(-1.0) == curva(0.0) and curva(9.0) == curva(1.0)  # fora de 0..1 é limitado
        assert ease_out_back(0.7) > 1.0


class TestCamera:
    def test_parada_e_desconhecida(self) -> None:
        for nome in ("parada", "qualquer"):
            assert camera_em(nome, 1.0, 4.0).zoom == 1.0
        assert set(MOVIMENTOS_DE_CAMERA) >= {"parada", "zoom_in", "zoom_out"}

    def test_zoom_in_e_zoom_out(self) -> None:
        assert camera_em("zoom_in", 0, 5).zoom == 1.0 and camera_em("zoom_in", 5, 5).zoom == pytest.approx(ZOOM_MAXIMO)
        assert (
            camera_em("zoom_out", 0, 5).zoom == pytest.approx(ZOOM_MAXIMO) and camera_em("zoom_out", 5, 5).zoom == 1.0
        )
        zooms = [camera_em("zoom_in", t / 10, 5).zoom for t in range(51)]
        assert zooms == sorted(zooms)  # nunca volta atrás

    @pytest.mark.parametrize("nome", ["panoramica_esq", "panoramica_dir"])
    def test_panoramica_nunca_sai_do_cenario(self, nome: str) -> None:
        for t in np.linspace(0, 5, 51):
            c = camera_em(nome, float(t), 5.0)
            assert abs(c.px) <= folga(c.zoom) and c.py == 0.0
        assert camera_em("panoramica_esq", 0, 5).px > 0 > camera_em("panoramica_esq", 5, 5).px
        assert camera_em("panoramica_dir", 0, 5).px < 0 < camera_em("panoramica_dir", 5, 5).px

    def test_duracao_zero_nao_divide_por_zero(self) -> None:
        assert camera_em("zoom_in", 1.0, 0.0).zoom <= ZOOM_MAXIMO


class TestLayout:
    def test_um_personagem_fica_no_centro_e_grande(self) -> None:
        [item] = compor_layout(["a"], "16:9")
        assert (item.x, item.base_y, item.altura, item.espelhar) == (0.5, 0.92, 0.58, False)

    def test_tres_personagens_dividem_a_cena_e_o_da_direita_olha_para_o_centro(self) -> None:
        itens = compor_layout(["a", "b", "c"], "16:9")
        assert [i.x for i in itens] == [0.22, 0.5, 0.78] and [i.espelhar for i in itens] == [False, False, True]
        assert all(i.altura == 0.44 for i in itens)

    def test_quanto_mais_personagens_menores(self) -> None:
        alturas = [altura_do_personagem(n, "16:9", "medio") for n in (1, 2, 3, 4, 8)]
        assert alturas == sorted(alturas, reverse=True)
        xs = [i.x for i in compor_layout([str(n) for n in range(7)], "16:9")]
        assert xs == sorted(xs) and xs[0] > 0.05 and xs[-1] < 0.95

    def test_vertical_usa_personagens_menores_e_chao_mais_alto(self) -> None:
        [item] = compor_layout(["a"], "9:16")
        assert item.altura == 0.40 and item.base_y == 0.88
        assert altura_do_personagem(2, "9:16", "medio") < altura_do_personagem(2, "16:9", "medio")

    def test_enquadramento(self) -> None:
        assert (
            altura_do_personagem(1, "16:9", "aberto")
            < altura_do_personagem(1, "16:9", "medio")
            < altura_do_personagem(1, "16:9", "proximo")
        )
        assert altura_do_personagem(1, "16:9", "proximo") <= 0.9 and compor_layout([], "16:9") == []

    def test_de_dict_limita_valores_absurdos(self) -> None:
        item = ItemDeLayout.de_dict(
            {"personagem_id": "p", "x": 5, "base_y": -3, "altura": 99, "espelhar": 1, "pose": ""}
        )
        assert (item.x, item.base_y, item.altura, item.espelhar, item.pose) == (1.0, 0.3, 1.2, True, None)
        assert ItemDeLayout.de_dict(item.para_dict()) == item

    @pytest.mark.parametrize(
        ("disponiveis", "emocao", "acao", "esperada"),
        [
            ({"principal", "frente", "lado", "feliz"}, "feliz", "respirar", "feliz"),
            ({"principal", "frente", "lado"}, "feliz", "respirar", "frente"),
            ({"principal", "frente", "lado"}, "neutro", "andar", "lado"),
            ({"principal", "tres_quartos"}, "neutro", "pular", "tres_quartos"),
            ({"principal"}, "triste", "respirar", "principal"),
            (set(), "neutro", "respirar", "principal"),
        ],
    )
    def test_escolher_pose(self, disponiveis: set[str], emocao: str, acao: str, esperada: str) -> None:
        assert escolher_pose(disponiveis, emocao, acao) == esperada

    @pytest.mark.parametrize(
        ("texto", "esperada"),
        [
            ("o coelho pula na poça", "pular"),
            ("Lila caminha até a casa", "andar"),
            ("ela vai dormir cedo", "dormir"),  # "vai" também sugere andar, mas dormir manda
            ("vamos dançar juntos", "dancar"),
            ("Bento acena para os amigos", "saudar"),
            ("oi, amiguinho!", "saudar"),
            ("os dois cantam uma música", "balancar"),
            ("a grande banda toca quando anoitece", "respirar"),  # "and" no meio da palavra não conta
            ("ela olha o céu", "respirar"),
            ("", "respirar"),
        ],
    )
    def test_acao_do_texto(self, texto: str, esperada: str) -> None:
        assert acao_do_texto(texto) == esperada

    @pytest.mark.parametrize(
        ("texto", "esperados"),
        [
            ("está chovendo e as gotas caem", ("chuva",)),
            ("estrelas mágicas brilham no céu", ("brilhos",)),
            ("chuva de estrelas", ("chuva", "brilhos")),
            ("um dia de sol", ()),
            ("ela imagina uma casa", ()),  # "magi" dentro de "imagina" não conta
        ],
    )
    def test_efeitos_do_texto(self, texto: str, esperados: tuple[str, ...]) -> None:
        assert efeitos_do_texto(texto) == esperados


def _tom(caminho: Path, trechos: list[tuple[float, float]], duracao: float, taxa: int = 24_000) -> Path:
    """Um WAV com silêncio e trechos de tom (inicio, fim) em segundos."""
    dados = np.zeros(int(duracao * taxa), dtype=np.float32)
    for ini, fim in trechos:
        n = np.arange(int(ini * taxa), int(fim * taxa))
        dados[n] = 0.5 * np.sin(2 * np.pi * 220 * n / taxa)
    sf.write(str(caminho), dados, taxa)
    return caminho


class TestEnvelope:
    def test_o_volume_aparece_so_onde_ha_fala(self, tmp_path: Path) -> None:
        wav = _tom(tmp_path / "a.wav", [(0.5, 1.0)], 1.5)
        env = envelope_de_audio(wav, fps=10, quadros=15)
        assert env.shape == (15,) and env.dtype == np.float32
        assert np.all(env[:5] == 0.0) and np.all(env[5:10] > 0.5) and env[14] < 0.1 and env.max() <= 1.0

    def test_o_inicio_desloca_o_audio_dentro_da_cena(self, tmp_path: Path) -> None:
        wav = _tom(tmp_path / "a.wav", [(0.0, 0.5)], 0.5)
        env = envelope_de_audio(wav, fps=10, quadros=20, inicio_s=1.0)
        assert np.all(env[:10] == 0.0) and np.all(env[10:15] > 0.5)

    def test_audio_maior_que_a_cena_e_cortado_e_inicio_depois_do_fim_fica_mudo(self, tmp_path: Path) -> None:
        wav = _tom(tmp_path / "a.wav", [(0.0, 2.0)], 2.0)
        assert envelope_de_audio(wav, fps=10, quadros=5).shape == (5,)
        assert not envelope_de_audio(wav, fps=10, quadros=5, inicio_s=9.0).any()

    def test_silencio_total_e_arquivo_curto(self, tmp_path: Path) -> None:
        assert not envelope_de_audio(_tom(tmp_path / "s.wav", [], 1.0), fps=10, quadros=10).any()
        sf.write(str(tmp_path / "c.wav"), np.zeros(10, dtype=np.float32), 24_000)
        assert not envelope_de_audio(tmp_path / "c.wav", fps=10, quadros=10).any()

    def test_combinar_pega_o_maior_de_cada_quadro(self) -> None:
        a = np.array([0.1, 0.9, 0.0], dtype=np.float32)
        b = np.array([0.5, 0.2, 0.7, 1.0], dtype=np.float32)
        assert combinar_envelopes([a, b], 3).tolist() == pytest.approx([0.5, 0.9, 0.7])
        assert not combinar_envelopes([], 4).any()


def _fundo(caminho: Path, tamanho: tuple[int, int] = (320, 180)) -> Path:
    imagem = Image.new("RGB", tamanho)
    desenho = ImageDraw.Draw(imagem)
    for y in range(tamanho[1]):  # céu azul em cima, grama verde embaixo
        cor = (60, 120 + y * 100 // tamanho[1], 230 - y * 150 // tamanho[1])
        desenho.line([(0, y), (tamanho[0], y)], fill=cor)
    imagem.save(caminho)
    return caminho


def _personagem(caminho: Path, tamanho: tuple[int, int] = (100, 160)) -> Path:
    imagem = Image.new("RGBA", tamanho, (0, 0, 0, 0))
    ImageDraw.Draw(imagem).ellipse((8, 4, tamanho[0] - 8, tamanho[1] - 4), fill=(230, 20, 20, 255))
    imagem.save(caminho)
    return caminho


def _vermelho(quadro: Image.Image, x: int, y: int) -> bool:
    r, g, b = cast(tuple[int, int, int], quadro.getpixel((x, y)))
    return r > 200 and g < 70 and b < 70


def _topo_vermelho(quadro: Image.Image) -> int:
    for y in range(quadro.height):
        if any(_vermelho(quadro, x, y) for x in range(0, quadro.width, 2)):
            return y
    return -1


@pytest.fixture
def cena(tmp_path: Path) -> CenaDeRender:
    return CenaDeRender(
        fundo=_fundo(tmp_path / "fundo.png"),
        duracao_s=2.0,
        camadas=[CamadaDeRender(_personagem(tmp_path / "p.png"), x=0.5, base_y=0.9, altura=0.5)],
    )


class TestRenderizador:
    def test_compoe_cenario_e_personagem_no_lugar_certo(self, cena: CenaDeRender) -> None:
        r = RenderizadorDeCena(cena, 160, 90, 10)
        assert r.quadros_no_total == 20
        quadro = r.quadro(5)
        assert quadro.size == (160, 90) and quadro.mode == "RGB"
        assert _vermelho(quadro, 80, 60)  # o corpo do personagem, no centro e apoiado no chão
        assert not _vermelho(quadro, 10, 10) and not _vermelho(quadro, 150, 60)
        pixel = cast(tuple[int, int, int], quadro.getpixel((5, 5)))
        assert pixel[2] > pixel[0]  # o céu azul aparece no canto

    def test_o_personagem_tem_a_altura_pedida(self, cena: CenaDeRender) -> None:
        r = RenderizadorDeCena(cena, 160, 90, 10)
        assert r.camadas[0].imagem.height == 45  # 50% da altura do quadro
        topo = _topo_vermelho(r.quadro(0))
        assert 36 <= topo <= 40  # pés em 90% (81 px), 45 px de altura, menos a margem do desenho

    def test_personagem_largo_demais_e_reduzido_mantendo_a_proporcao(self, tmp_path: Path) -> None:
        larga = _personagem(tmp_path / "larga.png", (300, 100))
        cena = CenaDeRender(_fundo(tmp_path / "f.png"), 1.0, [CamadaDeRender(larga, 0.5, 0.9, 0.5)])
        assert RenderizadorDeCena(cena, 160, 90, 10).camadas[0].imagem.size == (99, 33)

    def test_espelhar_inverte_o_lado(self, tmp_path: Path) -> None:
        assimetrico = Image.new("RGBA", (100, 160), (0, 0, 0, 0))
        ImageDraw.Draw(assimetrico).rectangle((0, 0, 30, 160), fill=(230, 20, 20, 255))  # só a esquerda é vermelha
        assimetrico.save(tmp_path / "a.png")
        fundo = _fundo(tmp_path / "f.png")
        normal = RenderizadorDeCena(
            CenaDeRender(fundo, 1, [CamadaDeRender(tmp_path / "a.png", 0.5, 0.9, 0.5)]), 160, 90, 10
        )
        espelhada = RenderizadorDeCena(
            CenaDeRender(fundo, 1, [CamadaDeRender(tmp_path / "a.png", 0.5, 0.9, 0.5, espelhar=True)]), 160, 90, 10
        )
        assert _vermelho(normal.quadro(3), 68, 60) and not _vermelho(normal.quadro(3), 92, 60)
        assert _vermelho(espelhada.quadro(3), 92, 60) and not _vermelho(espelhada.quadro(3), 68, 60)

    def test_pular_tira_o_personagem_do_chao(self, cena: CenaDeRender) -> None:
        cena.camadas[0].acao = "pular"
        r = RenderizadorDeCena(cena, 160, 90, 20)
        no_chao = _topo_vermelho(r.quadro(0))
        no_ar = _topo_vermelho(r.quadro(11))  # 0,55 s: o ponto mais alto do primeiro salto
        assert no_ar <= no_chao - 6

    def test_balancar_gira_o_personagem_em_torno_dos_pes(self, cena: CenaDeRender) -> None:
        cena.camadas[0].acao = "balancar"
        r = RenderizadorDeCena(cena, 160, 90, 20)
        pe_parado = [x for x in range(160) if _vermelho(r.quadro(0), x, 79)]
        inclinado = r.quadro(7)  # t = 0,35 s: perto do ponto de maior giro
        pe_girado = [x for x in range(160) if _vermelho(inclinado, x, 79)]
        assert pe_parado and pe_girado and abs(np.mean(pe_parado) - np.mean(pe_girado)) < 2  # os pés ficam no lugar
        assert r.quadro(0).tobytes() != inclinado.tobytes()
        cabeca_parada = [x for x in range(160) if _vermelho(r.quadro(0), x, 42)]
        cabeca_girada = [x for x in range(160) if _vermelho(inclinado, x, 42)]
        assert abs(np.mean(cabeca_parada) - np.mean(cabeca_girada)) > 1  # a cabeça se mexe

    def test_entrada_aparecer_comeca_invisivel(self, cena: CenaDeRender) -> None:
        cena.camadas[0].entrada = "aparecer"
        r = RenderizadorDeCena(cena, 160, 90, 10)
        assert not _vermelho(r.quadro(0), 80, 60) and _vermelho(r.quadro(10), 80, 60)

    def test_entrada_deslizar_vem_de_fora_do_quadro(self, cena: CenaDeRender) -> None:
        cena.camadas[0].entrada = "deslizar_esq"
        r = RenderizadorDeCena(cena, 160, 90, 10)
        assert not _vermelho(r.quadro(0), 80, 60)  # ainda longe, à esquerda
        assert _vermelho(r.quadro(9), 80, 60)  # já chegou

    def test_a_sombra_escurece_o_chao_embaixo_dos_pes(self, cena: CenaDeRender, tmp_path: Path) -> None:
        vazio = CenaDeRender(cena.fundo, 1.0)
        sem = RenderizadorDeCena(vazio, 160, 90, 10).quadro(0).convert("L")
        com = RenderizadorDeCena(cena, 160, 90, 10).quadro(0).convert("L")
        regiao = (60, 82, 100, 88)  # logo abaixo dos pés
        assert np.asarray(com.crop(regiao), dtype=float).mean() < np.asarray(sem.crop(regiao), dtype=float).mean() - 2

    def test_camera_muda_o_enquadramento_do_cenario(self, tmp_path: Path) -> None:
        cena = CenaDeRender(_fundo(tmp_path / "f.png"), 2.0, camera="zoom_in")
        r = RenderizadorDeCena(cena, 160, 90, 10)
        assert r.quadro(0).tobytes() != r.quadro(19).tobytes()
        parada = RenderizadorDeCena(CenaDeRender(cena.fundo, 2.0), 160, 90, 10)
        assert parada.quadro(0).tobytes() == parada.quadro(19).tobytes()  # sem personagem e sem câmera, nada muda

    def test_o_personagem_acompanha_o_zoom_da_camera(self, cena: CenaDeRender) -> None:
        cena.camera = "zoom_in"
        r = RenderizadorDeCena(cena, 160, 90, 10)
        antes, depois = r.quadro(0), r.quadro(19)
        altura_antes = sum(_vermelho(antes, 80, y) for y in range(90))
        altura_depois = sum(_vermelho(depois, 80, y) for y in range(90))
        assert altura_depois > altura_antes

    def test_fala_faz_o_personagem_pulsar(self, cena: CenaDeRender) -> None:
        quadro_mudo = RenderizadorDeCena(cena, 160, 90, 10).quadro(5)  # antes de dar voz ao personagem
        cena.camadas[0].envelope = np.ones(20, dtype=np.float32)
        quadro_falando = RenderizadorDeCena(cena, 160, 90, 10).quadro(5)
        assert quadro_mudo.tobytes() != quadro_falando.tobytes()
        assert sum(_vermelho(quadro_falando, 80, y) for y in range(90)) > sum(
            _vermelho(quadro_mudo, 80, y) for y in range(90)
        )

    def test_brilhos_e_chuva_desenham_por_cima(self, tmp_path: Path) -> None:
        fundo = _fundo(tmp_path / "f.png")
        limpo = RenderizadorDeCena(CenaDeRender(fundo, 2.0), 160, 90, 10).quadro(5)
        com_brilhos = RenderizadorDeCena(CenaDeRender(fundo, 2.0, efeitos=("brilhos",), semente=3), 160, 90, 10).quadro(
            5
        )
        com_chuva = RenderizadorDeCena(CenaDeRender(fundo, 2.0, efeitos=("chuva",), semente=3), 160, 90, 10).quadro(5)
        assert limpo.tobytes() != com_brilhos.tobytes() and limpo.tobytes() != com_chuva.tobytes()

    def test_o_mesmo_pedido_gera_os_mesmos_quadros(self, cena: CenaDeRender) -> None:
        cena.efeitos = ("brilhos", "chuva")
        cena.camadas[0].acao = "dancar"
        a, b = RenderizadorDeCena(cena, 160, 90, 10), RenderizadorDeCena(cena, 160, 90, 10)
        assert [a.quadro(i).tobytes() for i in (0, 7, 13)] == [b.quadro(i).tobytes() for i in (0, 7, 13)]

    def test_cenario_ou_personagem_ausente_da_erro_em_portugues(self, cena: CenaDeRender, tmp_path: Path) -> None:
        with pytest.raises(ErroParaOUsuario, match="cenário"):
            RenderizadorDeCena(CenaDeRender(tmp_path / "nao-existe.png", 1.0), 160, 90, 10)
        (tmp_path / "quebrado.png").write_bytes(b"isto nao e uma imagem")
        with pytest.raises(ErroParaOUsuario, match="personagem"):
            RenderizadorDeCena(
                CenaDeRender(cena.fundo, 1.0, [CamadaDeRender(tmp_path / "quebrado.png", 0.5, 0.9, 0.5)]), 160, 90, 10
            )

    def test_camada_fora_do_quadro_nao_quebra(self, cena: CenaDeRender) -> None:
        cena.camadas[0].x = 3.0
        RenderizadorDeCena(cena, 160, 90, 10).quadro(0)

    def test_quadros_tem_o_tamanho_de_um_video_rgb(self, cena: CenaDeRender) -> None:
        r = RenderizadorDeCena(cena, 160, 90, 10)
        quadros = list(r.quadros())
        assert len(quadros) == 20 and all(len(q) == 160 * 90 * 3 for q in quadros)

    @pytest.mark.parametrize("camera", ["zoom_in", "zoom_out", "panoramica_esq", "panoramica_dir"])
    def test_a_camera_por_recorte_equivale_a_transformacao_afim(self, tmp_path: Path, camera: str) -> None:
        """O quadro da câmera sai de um `resize` com `box` (metade do tempo); tem de ser o mesmo desenho da transformação afim."""
        r = RenderizadorDeCena(CenaDeRender(_fundo(tmp_path / "f.png"), 2.0, camera=camera), 160, 90, 10)
        for indice in (0, 5, 13, 19):
            cam = camera_em(camera, indice / 10, 2.0)
            cx, cy = 80 + cam.px * 160, 45 + cam.py * 90
            a = 1 / cam.zoom
            afim = r.fundo.transform(
                (160, 90),
                Image.Transform.AFFINE,
                (a, 0, cx - 160 * a / 2, 0, a, cy - 90 * a / 2),
                resample=Image.Resampling.BILINEAR,
            )
            diferenca = np.abs(np.asarray(r.quadro(indice), dtype=int) - np.asarray(afim, dtype=int))
            assert diferenca.max() <= 2, (camera, indice)

    def test_varios_desenhistas_dao_os_mesmos_quadros_na_mesma_ordem(self, cena: CenaDeRender) -> None:
        cena.efeitos = ("brilhos",)
        cena.camera = "zoom_in"
        cena.camadas[0].acao = "pular"
        r = RenderizadorDeCena(cena, 160, 90, 10)
        um = list(r.quadros(desenhistas=1))
        varios = list(r.quadros(desenhistas=3))
        assert len(um) == len(varios) == 20 and um == varios

    def test_sem_nucleos_de_sobra_o_desenho_e_sequencial(
        self, cena: CenaDeRender, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("app.animacao.render.os.cpu_count", lambda: 1)
        r = RenderizadorDeCena(cena, 160, 90, 10)
        antes = {t.name for t in threading.enumerate()}
        assert len(list(r.quadros())) == 20
        assert {t.name for t in threading.enumerate()} == antes  # nenhum desenhista foi criado

    def test_parar_no_meio_solta_os_desenhistas(self, cena: CenaDeRender) -> None:
        r = RenderizadorDeCena(cena, 160, 90, 10)
        quadros = r.quadros(desenhistas=3)
        assert len(next(quadros)) == 160 * 90 * 3
        quadros.close()  # como quando o job é cancelado: nada fica rodando
        assert not [t for t in threading.enumerate() if t.name.startswith("quadro")]

    def test_capa_da_cena(self, cena: CenaDeRender) -> None:
        capa = quadro_de_capa(cena, 160, 90)
        assert capa.size == (160, 90) and _vermelho(capa, 80, 60)
        assert quadro_de_capa(CenaDeRender(cena.fundo, 0.3), 160, 90, t=5.0).size == (
            160,
            90,
        )  # cena mais curta que 1 s


class TestEfeitos:
    def test_brilhos_sao_previsiveis_e_lentos(self) -> None:
        assert brilhos_da_cena(4) == brilhos_da_cena(4) and brilhos_da_cena(4) != brilhos_da_cena(5)
        assert all(2.2 <= b.periodo <= 4.0 for b in brilhos_da_cena(1))  # bem abaixo de 3 piscadas por segundo

    def test_desenhar_muda_so_o_necessario(self) -> None:
        quadro = Image.new("RGB", (160, 90), (10, 10, 10))
        desenhar_brilhos(quadro, brilhos_da_cena(1), 1.0)
        assert quadro.getbbox() is not None and np.asarray(quadro).max() > 200
        chuva = Image.new("RGB", (160, 90), (10, 10, 10))
        desenhar_chuva(chuva, 1, 0.5)
        assert np.asarray(chuva).max() > 100


class TestRenderizarCena:
    def test_manda_todos_os_quadros_ao_ffmpeg_e_reporta_o_andamento(self, cena: CenaDeRender, tmp_path: Path) -> None:
        ffmpeg = FfmpegFalso()
        ctx = ContextoDeTeste()
        r = renderizar_cena(
            ctx, ffmpeg, cena, tmp_path / "saida" / "c.mp4", largura=160, altura=90, fps=10, faixa=(0.2, 0.6)
        )
        assert (r.quadros, r.duracao_s) == (20, 2.0) and r.caminho.is_file()
        render = ffmpeg.renders[0]
        assert (render["largura"], render["altura"], render["fps"], render["quadros"]) == (160, 90, 10, 20)
        assert "libx264" in render["argumentos"] and "yuv420p" in render["argumentos"]
        assert ctx.progressos and all(0.2 <= f <= 0.6 for f, _ in ctx.progressos)
        assert ffmpeg.sondar(r.caminho).duracao_s == pytest.approx(2.0)

    def test_cancelar_no_meio_para_o_desenho(self, cena: CenaDeRender, tmp_path: Path) -> None:
        ffmpeg = FfmpegFalso()
        with pytest.raises(JobCanceled):
            renderizar_cena(
                ContextoDeTeste(cancelar_no_ponto=2), ffmpeg, cena, tmp_path / "c.mp4", largura=160, altura=90, fps=10
            )
        assert ffmpeg.renders == [] and not (tmp_path / "c.mp4").exists()

    def test_falha_do_ffmpeg_vira_mensagem(self, cena: CenaDeRender, tmp_path: Path) -> None:
        ffmpeg = FfmpegFalso()
        ffmpeg.falhar_com = "A montagem do vídeo falhou: codec não encontrado"
        with pytest.raises(MotorFalhou, match="codec"):
            renderizar_cena(ContextoDeTeste(), ffmpeg, cena, tmp_path / "c.mp4", largura=160, altura=90, fps=10)


class TestComFfmpegDeVerdade:
    """Poucos testes com o ffmpeg real: conferem que o vídeo sai válido (duração, tamanho, codec, sem áudio)."""

    def test_renderiza_um_clipe_mp4_valido(self, cena: CenaDeRender, tmp_path: Path, ffmpeg_real: Ffmpeg) -> None:
        cena.duracao_s = 1.0
        cena.camadas[0].acao = "pular"
        saida = tmp_path / "clipe.mp4"
        r = renderizar_cena(ContextoReal(), ffmpeg_real, cena, saida, largura=128, altura=72, fps=12)
        assert r.quadros == 12 and saida.stat().st_size > 1000
        sonda = ffmpeg_real.sondar(saida)
        assert (sonda.largura, sonda.altura, sonda.codec_de_video) == (128, 72, "h264")
        assert sonda.duracao_s == pytest.approx(1.0, abs=0.15) and sonda.fps == pytest.approx(12, abs=0.1)
        assert not sonda.tem_audio and sonda.tem_video

    def test_quadro_com_tamanho_errado_e_recusado(self, tmp_path: Path, ffmpeg_real: Ffmpeg) -> None:
        with pytest.raises(MotorFalhou, match="tamanho errado"):
            ffmpeg_real.rodar_com_quadros(
                ContextoReal(), [b"curto"], largura=64, altura=36, fps=10, total=1, saida=tmp_path / "x.mp4"
            )

    def test_argumento_invalido_do_ffmpeg_vira_erro_legivel(self, tmp_path: Path, ffmpeg_real: Ffmpeg) -> None:
        quadro = bytes(64 * 36 * 3)
        with pytest.raises(MotorFalhou, match="montagem do vídeo falhou"):
            ffmpeg_real.rodar_com_quadros(
                ContextoReal(),
                [quadro] * 3,
                largura=64,
                altura=36,
                fps=10,
                total=3,
                saida=tmp_path / "x.mp4",
                argumentos_de_saida=["-c:v", "codec_que_nao_existe"],
            )

    def test_cancelar_encerra_o_processo(self, tmp_path: Path, ffmpeg_real: Ffmpeg) -> None:
        quadro = bytes(64 * 36 * 3)
        with pytest.raises(JobCanceled):
            ffmpeg_real.rodar_com_quadros(
                ContextoDeTeste(cancelar_no_ponto=2),
                (quadro for _ in range(100)),
                largura=64,
                altura=36,
                fps=10,
                total=100,
                saida=tmp_path / "x.mp4",
            )

    def test_sondar_arquivo_que_nao_e_video(self, tmp_path: Path, ffmpeg_real: Ffmpeg) -> None:
        falso = tmp_path / "falso.mp4"
        falso.write_bytes(b"isto nao e um video de verdade")
        with pytest.raises(MotorFalhou, match="não é um vídeo"):
            ffmpeg_real.sondar(falso)

    def test_a_rotacao_de_pontos_da_pivo_esta_certa(self) -> None:
        # o pé (parte de baixo do centro) gira em torno do centro da imagem: verificação da fórmula usada no renderizador
        h1, angulo = 100.0, math.radians(30)
        largura_expandida = altura_expandida = 200.0
        esquerda = 50.0 - (largura_expandida / 2 + (h1 / 2) * math.sin(angulo))
        topo = 80.0 - (altura_expandida / 2 + (h1 / 2) * math.cos(angulo))
        assert (esquerda, topo) == pytest.approx((50 - 100 - 25, 80 - 100 - 43.30127), abs=1e-3)
