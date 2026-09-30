"""Montagem final: plano de tempos, filtros do ffmpeg, medição de volume e flashes (puros e, no fim, com o ffmpeg de verdade)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from PIL import Image

from app.animacao.render import CamadaDeRender, CenaDeRender, renderizar_cena
from app.audio.mixagem import TAXA, Fala, mixar, salvar_wav
from app.motores.ffmpeg import Ffmpeg
from app.motores.tipos import MotorFalhou
from app.projetos.montagem import (
    argumentos_com_transicao,
    argumentos_de_corte_seco,
    escrever_lista_de_concatenacao,
    filtro_de_transicoes,
    filtro_de_volume,
    ler_medicao,
    medir_volume,
    montar_video,
    plano_de_montagem,
)
from app.projetos.qualidade import (
    MAXIMO_DE_FLASHES_POR_SEGUNDO,
    contar_flashes,
    semelhanca,
    verificar_flashes,
)

from .builders_projetos import png_de_personagem
from .fakes_motores import ContextoDeTeste, ContextoReal, FfmpegFalso


class TestPlano:
    def test_corte_seco_uma_cena_comeca_quando_a_outra_acaba(self) -> None:
        plano = plano_de_montagem([5.0, 4.0, 6.0], "corte")
        assert plano.inicios == [0.0, 5.0, 9.0] and plano.duracao_total_s == 15.0 and plano.sobreposicao_s == 0.0

    def test_com_transicao_as_cenas_se_sobrepoem(self) -> None:
        plano = plano_de_montagem([5.0, 5.0, 5.0], "fade")
        assert plano.inicios == [0.0, 4.5, 9.0] and plano.duracao_total_s == 14.0 and plano.transicao == "fade"
        suave = plano_de_montagem([5.0, 5.0], "suave")
        assert suave.inicios == [0.0, 4.1] and suave.duracao_total_s == 9.1 and suave.transicao == "dissolve"

    def test_uma_cena_so_nao_tem_sobreposicao(self) -> None:
        plano = plano_de_montagem([5.0], "fade")
        assert plano.inicios == [0.0] and plano.duracao_total_s == 5.0 and plano.sobreposicao_s == 0.0

    def test_transicao_desconhecida_vira_corte(self) -> None:
        assert plano_de_montagem([3.0, 3.0], "explosao").duracao_total_s == 6.0


class TestFiltros:
    def test_cadeia_de_xfade(self) -> None:
        assert filtro_de_transicoes([5.0, 5.0, 5.0], "fade", 0.5) == (
            "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=4.500[v1];"
            "[v1][2:v]xfade=transition=fade:duration=0.5:offset=9.000[saida]"
        )
        assert (
            filtro_de_transicoes([5.0, 3.0], "dissolve", 0.9)
            == "[0:v][1:v]xfade=transition=dissolve:duration=0.9:offset=4.100[saida]"
        )
        assert filtro_de_transicoes([5.0], "fade", 0.5) == "[0:v]null[saida]"

    def test_volume_em_uma_passada_ou_com_a_medicao(self) -> None:
        assert filtro_de_volume(None) == "loudnorm=I=-14:TP=-1.5:LRA=11"
        medida = {
            "input_i": "-23.1",
            "input_tp": "-4.0",
            "input_lra": "2.5",
            "input_thresh": "-33.2",
            "target_offset": "0.4",
        }
        com = filtro_de_volume(medida)
        assert (
            "measured_I=-23.1" in com
            and "measured_TP=-4.0" in com
            and "offset=0.4" in com
            and com.endswith("linear=true")
        )
        assert filtro_de_volume({"input_i": "-23"}) == "loudnorm=I=-14:TP=-1.5:LRA=11"  # medição incompleta não vale

    def test_ler_a_medicao_no_meio_do_texto_do_ffmpeg(self) -> None:
        saida = 'frame= 0 fps=0.0\n[Parsed_loudnorm_0 @ 0x1] \n{\n\t"input_i" : "-20.50",\n\t"input_tp" : "-3.10",\n\t"input_lra" : "1.20",\n\t"input_thresh" : "-30.9",\n\t"target_offset" : "0.02"\n}\n'
        medida = ler_medicao(saida)
        assert medida is not None and medida["input_i"] == "-20.50" and medida["target_offset"] == "0.02"
        assert ler_medicao("nada de json aqui") is None and ler_medicao('{"input_i": quebrado}') is None

    def test_a_lista_do_concat_escapa_aspas_e_usa_barras(self, tmp_path: Path) -> None:
        clipes = [tmp_path / "a b.mp4", tmp_path / "o'neil.mp4"]
        lista = escrever_lista_de_concatenacao(clipes, tmp_path / "sub" / "l.txt")
        linhas = lista.read_text(encoding="utf-8").splitlines()
        assert len(linhas) == 2 and all(linha.startswith("file '") and "\\\\" not in linha for linha in linhas)
        assert "o'\\''neil.mp4" in linhas[1] and "\\" not in linhas[0]

    def test_argumentos_do_corte_seco_copiam_o_video(self, tmp_path: Path) -> None:
        args = [
            str(a) for a in argumentos_de_corte_seco(tmp_path / "l.txt", tmp_path / "a.wav", tmp_path / "s.mp4", None)
        ]
        assert args[args.index("-c:v") + 1] == "copy" and "-shortest" in args and args[-1].endswith("s.mp4")
        assert args[args.index("-map") + 1] == "0:v:0" and "1:a:0" in args and "concat" in args
        assert any(a.startswith("loudnorm") for a in args) and "aac" in args

    def test_argumentos_com_transicao_reencodam(self, tmp_path: Path) -> None:
        clipes = [tmp_path / f"{i}.mp4" for i in range(3)]
        args = [
            str(a)
            for a in argumentos_com_transicao(
                clipes, [5.0, 5.0, 5.0], "fade", tmp_path / "a.wav", tmp_path / "s.mp4", None
            )
        ]
        assert args.count("-i") == 4 and "libx264" in args and "3:a:0" in args and "[saida]" in args
        assert "xfade" in args[args.index("-filter_complex") + 1]

    def test_sem_clipes_ou_com_contagem_errada(self, tmp_path: Path) -> None:
        with pytest.raises(MotorFalhou, match="Não há clipes"):
            montar_video(
                FfmpegFalso(),
                ContextoDeTeste(),
                [],
                [],
                "corte",
                tmp_path / "a.wav",
                tmp_path / "s.mp4",
                tmp_path,
                None,
            )
        with pytest.raises(MotorFalhou, match="Não há clipes"):
            montar_video(
                FfmpegFalso(),
                ContextoDeTeste(),
                [tmp_path / "a.mp4"],
                [1.0, 2.0],
                "corte",
                tmp_path / "a.wav",
                tmp_path / "s.mp4",
                tmp_path,
                None,
            )

    def test_medir_volume_com_o_ffmpeg_falso_nao_devolve_nada(self, tmp_path: Path) -> None:
        assert medir_volume(FfmpegFalso(), ContextoDeTeste(), tmp_path / "a.wav") is None


class TestFlashes:
    def test_luz_estavel_nao_tem_flash(self) -> None:
        r = contar_flashes([0.5] * 60)
        assert r.maximo_por_segundo == 0 and r.aprovado and r.momento_s is None

    def test_troca_de_cena_de_escuro_para_claro_e_uma_mudanca_so(self) -> None:
        assert contar_flashes([0.1] * 30 + [0.9] * 30).aprovado

    def test_fade_lento_passa(self) -> None:
        assert contar_flashes(list(np.linspace(0.1, 0.9, 60))).aprovado

    def test_pisca_pisca_rapido_reprova(self) -> None:
        serie = [
            0.05 if i % 2 else 0.95 for i in range(48)
        ]  # 12 amostras por segundo, alternando a cada uma: 6 flashes/s
        r = contar_flashes(serie)
        assert not r.aprovado and r.maximo_por_segundo >= 5 and r.momento_s is not None
        assert r.para_api()["passed"] is False and r.para_api()["limit_per_second"] == MAXIMO_DE_FLASHES_POR_SEGUNDO

    def test_tres_flashes_por_segundo_ainda_e_permitido(self) -> None:
        # 3 pares claro/escuro em 1 s (6 inversões): no limite
        um_segundo = [0.9, 0.9, 0.1, 0.1] * 3
        assert contar_flashes(um_segundo + [0.5] * 24).aprovado

    def test_mudancas_pequenas_de_luz_nao_contam(self) -> None:
        serie = [0.5 + (0.04 if i % 2 else -0.04) for i in range(48)]  # variação de 8%: abaixo do critério de 10%
        assert contar_flashes(serie).aprovado

    def test_series_curtas(self) -> None:
        assert contar_flashes([]).aprovado and contar_flashes([0.1, 0.9]).aprovado

    def test_verificar_flashes_usa_a_luminancia_do_ffmpeg(self, tmp_path: Path) -> None:
        ffmpeg = FfmpegFalso()
        video = tmp_path / "v.mp4"
        ffmpeg.luminancias[str(video)] = [0.05 if i % 2 else 0.95 for i in range(48)]
        assert not verificar_flashes(ffmpeg, video).aprovado
        assert verificar_flashes(ffmpeg, tmp_path / "outro.mp4").aprovado


class TestSemelhanca:
    def test_textos_iguais_diferentes_e_vazios(self) -> None:
        a = "Lila brinca no jardim com o Bento e começa a chover"
        assert semelhanca(a, a) == pytest.approx(1.0)
        assert semelhanca(a, "Um dragão simpático voa sobre a montanha de sorvete") < 0.2
        assert semelhanca(a, "") == 0.0 and semelhanca("", "") == 0.0

    def test_ordem_e_acento_nao_importam(self) -> None:
        assert semelhanca("Começou a chover no jardim", "no JARDIM comecou a chover") == pytest.approx(1.0)

    def test_historia_reaproveitada_com_pequenas_mudancas_fica_perto_do_limite(self) -> None:
        base = "Lila e Bento brincam no jardim. Começa a chover. Eles correm para debaixo da árvore e cantam juntos."
        parecida = "Lila e Bento brincam no jardim. Começa a chover forte. Eles correm para debaixo da árvore e cantam."
        assert semelhanca(base, parecida) > 0.8


def _clipe(ffmpeg: Ffmpeg, pasta: Path, nome: str, cor: tuple[int, int, int], duracao: float = 1.0) -> Path:
    fundo = pasta / f"{nome}.png"
    Image.new("RGB", (96, 54), cor).save(fundo)
    cena = CenaDeRender(fundo, duracao, [CamadaDeRender(png_de_personagem(pasta / f"{nome}-p.png"), 0.5, 0.9, 0.5)])
    saida = pasta / f"{nome}.mp4"
    renderizar_cena(ContextoReal(), ffmpeg, cena, saida, largura=96, altura=54, fps=12)
    return saida


def _trilha(pasta: Path, segundos: float, amplitude: float = 0.4) -> Path:
    n = np.arange(int(segundos * TAXA))
    voz = (amplitude * np.sin(2 * np.pi * 220 * n / TAXA) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * n / TAXA))).astype(
        np.float32
    )
    return salvar_wav(pasta / "mix.wav", mixar(segundos, [Fala(0.0, voz)]))


class TestComFfmpegDeVerdade:
    def test_corte_seco_junta_clipes_e_audio_sem_reencodar_o_video(self, tmp_path: Path, ffmpeg_real: Ffmpeg) -> None:
        clipes = [
            _clipe(ffmpeg_real, tmp_path, f"c{i}", cor)
            for i, cor in enumerate([(200, 60, 60), (60, 200, 60), (60, 60, 200)])
        ]
        audio = _trilha(tmp_path, 3.0)
        saida = tmp_path / "final.mp4"
        montar_video(ffmpeg_real, ContextoReal(), clipes, [1.0, 1.0, 1.0], "corte", audio, saida, tmp_path, None)
        sonda = ffmpeg_real.sondar(saida)
        assert sonda.duracao_s == pytest.approx(3.0, abs=0.2) and (sonda.largura, sonda.altura) == (96, 54)
        assert (
            sonda.codec_de_video == "h264"
            and sonda.codec_de_audio == "aac"
            and sonda.canais == 2
            and sonda.taxa_de_audio == 44_100
        )
        assert not list(tmp_path.glob("lista-*"))

    def test_com_crossfade_o_video_fica_mais_curto_pela_sobreposicao(self, tmp_path: Path, ffmpeg_real: Ffmpeg) -> None:
        clipes = [
            _clipe(ffmpeg_real, tmp_path, f"c{i}", cor, 2.0)
            for i, cor in enumerate([(200, 60, 60), (60, 200, 60), (60, 60, 200)])
        ]
        plano = plano_de_montagem([2.0, 2.0, 2.0], "fade")
        assert plano.duracao_total_s == 5.0
        audio = _trilha(tmp_path, plano.duracao_total_s)
        saida = tmp_path / "final.mp4"
        montar_video(ffmpeg_real, ContextoReal(), clipes, [2.0, 2.0, 2.0], "fade", audio, saida, tmp_path, None)
        sonda = ffmpeg_real.sondar(saida)
        assert sonda.duracao_s == pytest.approx(5.0, abs=0.25) and sonda.codec_de_video == "h264" and sonda.tem_audio

    def test_o_volume_medido_e_o_final_ficam_perto_de_menos_14_lufs(self, tmp_path: Path, ffmpeg_real: Ffmpeg) -> None:
        clipes = [_clipe(ffmpeg_real, tmp_path, "c", (200, 200, 60), 3.0)]
        audio = _trilha(tmp_path, 3.0, amplitude=0.12)
        medida = medir_volume(ffmpeg_real, ContextoReal(), audio)
        assert medida is not None and float(medida["input_i"]) < -14  # a mistura crua é mais baixa que o alvo
        saida = tmp_path / "final.mp4"
        montar_video(ffmpeg_real, ContextoReal(), clipes, [3.0], "corte", audio, saida, tmp_path, medida)
        depois = medir_volume(ffmpeg_real, ContextoReal(), saida)
        assert depois is not None and -16.5 <= float(depois["input_i"]) <= -11.5

    def test_luminancia_e_flashes_de_um_video_de_verdade(self, tmp_path: Path, ffmpeg_real: Ffmpeg) -> None:
        def quadros(alternar: bool) -> list[bytes]:
            claro, escuro = bytes([240]) * (96 * 54 * 3), bytes([10]) * (96 * 54 * 3)
            return [claro if (i % 2 and alternar) or (not alternar and i < 12) else escuro for i in range(24)]

        for nome, alternar in (("pisca", True), ("estavel", False)):
            ffmpeg_real.rodar_com_quadros(
                ContextoReal(),
                quadros(alternar),
                largura=96,
                altura=54,
                fps=12,
                total=24,
                saida=tmp_path / f"{nome}.mp4",
            )
        assert not verificar_flashes(ffmpeg_real, tmp_path / "pisca.mp4").aprovado
        assert verificar_flashes(ffmpeg_real, tmp_path / "estavel.mp4").aprovado  # uma única troca de claro para escuro
        serie = ffmpeg_real.extrair_luminancia(tmp_path / "estavel.mp4", 12)
        assert len(serie) in (24, 25) and max(serie) > 0.8 and min(serie) < 0.2

    def test_luminancia_de_arquivo_invalido(self, tmp_path: Path, ffmpeg_real: Ffmpeg) -> None:
        (tmp_path / "x.mp4").write_bytes(b"nao e video")
        with pytest.raises(MotorFalhou, match="luminância"):
            ffmpeg_real.extrair_luminancia(tmp_path / "x.mp4")

    def test_o_wav_da_mistura_e_valido(self, tmp_path: Path) -> None:
        audio = _trilha(tmp_path, 1.0)
        dados, taxa = sf.read(str(audio), always_2d=True)
        assert taxa == TAXA and dados.shape[1] == 2 and abs(dados).max() <= 0.98
