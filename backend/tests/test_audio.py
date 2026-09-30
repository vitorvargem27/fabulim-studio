"""Áudio do vídeo: música e efeitos sintetizados, mixagem com ducking e legendas SRT."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from app.audio.legendas import LARGURA_DA_LINHA, formatar_tempo, gerar_srt, quebrar_em_partes
from app.audio.mixagem import Efeito, Fala, carregar_mono, ganho_de_ducking, mixar, salvar_wav
from app.audio.musica import (
    ACORDES,
    EFEITOS,
    ESTILOS,
    PENTATONICA,
    TAXA,
    acorde_de_violao,
    corda_dedilhada,
    duracao_do_padrao,
    efeito_do_texto,
    gerar_efeito,
    gerar_musica,
    melodia,
    nota_de_baixo,
    nota_de_caixinha,
    nota_de_marimba,
)
from app.audio.musica import _frequencia as frequencia


def _dominante(onda: np.ndarray, faixa: tuple[float, float] = (50, 3000)) -> float:
    """A frequência mais forte da onda (FFT)."""
    janela = np.hanning(len(onda))
    espectro = np.abs(np.fft.rfft(onda * janela))
    freqs = np.fft.rfftfreq(len(onda), 1 / TAXA)
    dentro = (freqs >= faixa[0]) & (freqs <= faixa[1])
    return float(freqs[dentro][np.argmax(espectro[dentro])])


def _rms(onda: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(onda.astype(np.float64)))))


class TestNotas:
    def test_frequencias_midi(self) -> None:
        assert frequencia(69) == pytest.approx(440.0)
        assert frequencia(60) == pytest.approx(261.63, abs=0.01) and frequencia(81) == pytest.approx(880.0)

    def test_marimba_toca_a_nota_pedida_e_apaga(self) -> None:
        onda = nota_de_marimba(60, 1.0)
        assert len(onda) == TAXA and onda.dtype == np.float32 and np.isfinite(onda).all()
        assert _dominante(onda) == pytest.approx(261.6, abs=2.0)
        assert 0.3 < np.abs(onda).max() <= 1.2 and abs(float(onda.mean())) < 0.01
        assert _rms(onda[: TAXA // 10]) > 5 * _rms(onda[-TAXA // 10 :])  # o som morre

    def test_caixinha_soa_uma_oitava_acima(self) -> None:
        assert _dominante(nota_de_caixinha(60, 1.0)) == pytest.approx(523.3, abs=3.0)

    def test_corda_de_violao_pelo_karplus_strong(self) -> None:
        corda = corda_dedilhada(48, 1.0)
        # o tom de uma corda é o período em que ela se repete (autocorrelação): 44100 / 130,8 Hz ≈ 337 amostras
        trecho = corda[TAXA // 10 : TAXA // 2].astype(np.float64)
        auto = np.correlate(trecho, trecho, mode="full")[len(trecho) - 1 :]
        periodo = 200 + int(np.argmax(auto[200:500]))
        assert len(corda) == TAXA and TAXA / periodo == pytest.approx(130.8, abs=3.0)
        assert _rms(corda[: TAXA // 5]) > _rms(corda[-TAXA // 5 :]) > 0  # decai devagar, sem sumir de uma vez
        assert np.array_equal(corda_dedilhada(48, 0.5), corda_dedilhada(48, 0.5))  # sempre igual

    @pytest.mark.parametrize("acorde", sorted(ACORDES))
    def test_acordes_de_violao_cabem_sem_estourar(self, acorde: str) -> None:
        for para_baixo in (True, False):
            onda = acorde_de_violao(acorde, 0.9, para_baixo)
            assert len(onda) == int(TAXA * 0.9) and np.abs(onda).max() < 1.0 and np.abs(onda).max() > 0.05

    def test_baixo_e_grave(self) -> None:
        assert _dominante(nota_de_baixo(48, 1.0), (30, 300)) == pytest.approx(65.4, abs=2.0)


class TestMelodia:
    def test_so_usa_notas_da_escala_e_termina_na_tonica(self) -> None:
        for estilo in ESTILOS.values():
            notas = melodia(estilo, 8, semente=3)
            assert notas and all(n in PENTATONICA for _, n, _ in notas)
            assert all(0 <= inicio < 32 for inicio, _, _ in notas)
            assert notas[-1][1] == 72 and notas[-1][2] >= 2.0
            assert [n[0] for n in notas] == sorted(n[0] for n in notas)

    def test_mesma_semente_mesma_musica_e_outra_semente_outra(self) -> None:
        alegre = ESTILOS["alegre"]
        assert melodia(alegre, 8, 1) == melodia(alegre, 8, 1)
        assert melodia(alegre, 8, 1) != melodia(alegre, 8, 2)

    def test_a_frase_se_repete_como_numa_cantiga(self) -> None:
        notas = melodia(ESTILOS["alegre"], 16, semente=5)

        def ritmo_dos_compassos(primeiro: int) -> list[tuple[float, float]]:
            return [
                (round(i - primeiro * 4, 3), d) for i, _, d in notas if primeiro * 4 <= i < (primeiro + 4) * 4 - 0.001
            ]

        assert ritmo_dos_compassos(0) == ritmo_dos_compassos(8)  # A ... A
        # B ... B (a última nota da música é sempre a tônica, mais longa: fica fora da comparação)
        assert ritmo_dos_compassos(4)[:-1] == ritmo_dos_compassos(12)[:-1]

    def test_ninar_tem_pausas(self) -> None:
        calma = melodia(ESTILOS["calma"], 8, semente=2)
        alegre = melodia(ESTILOS["alegre"], 8, semente=2)
        assert len(calma) < len(alegre)


class TestTrilha:
    def test_duracao_exata_volume_seguro_e_fades(self) -> None:
        trilha = gerar_musica(10.0, "alegre", semente=1)
        assert len(trilha) == 10 * TAXA and trilha.dtype == np.float32 and np.isfinite(trilha).all()
        assert np.abs(trilha).max() <= 0.86
        meio = _rms(trilha[4 * TAXA : 6 * TAXA])
        assert meio > 0.02
        assert _rms(trilha[: TAXA // 10]) < 0.4 * meio  # entrada suave
        assert _rms(trilha[-TAXA // 10 :]) < 0.1 * meio  # o final apaga

    def test_e_previsivel_e_a_semente_muda_a_musica(self) -> None:
        assert np.array_equal(gerar_musica(6.0, "alegre", 7), gerar_musica(6.0, "alegre", 7))
        assert not np.array_equal(gerar_musica(6.0, "alegre", 7), gerar_musica(6.0, "alegre", 8))

    @pytest.mark.parametrize("estilo", sorted(ESTILOS))
    def test_todos_os_estilos_soam_e_seguem_o_andamento(self, estilo: str) -> None:
        trilha = gerar_musica(14.0, estilo, semente=1, entrada_s=0.2, saida_s=0.2)
        assert _rms(trilha) > 0.02
        # o andamento: o envelope de energia se repete a cada batida (autocorrelação)
        quadro = TAXA // 100
        energia = np.abs(trilha[: len(trilha) // quadro * quadro]).reshape(-1, quadro).mean(axis=1)
        energia = energia - energia.mean()
        auto = np.correlate(energia, energia, mode="full")[len(energia) - 1 :]
        batida = 60.0 / ESTILOS[estilo].bpm
        lags = np.arange(len(auto)) / 100
        candidatos = (lags > batida * 0.8) & (lags < batida * 2.3)
        melhor = float(lags[candidatos][np.argmax(auto[candidatos])])
        assert min(abs(melhor - batida * k) for k in (1, 2)) < 0.05, (estilo, melhor, batida)

    def test_musica_curta_demais_ganha_um_minimo(self) -> None:
        assert len(gerar_musica(0.1)) == int(TAXA * 0.5)

    def test_estilo_desconhecido_cai_no_padrao(self) -> None:
        assert np.array_equal(gerar_musica(3.0, "inexistente", 4), gerar_musica(3.0, "alegre", 4))

    def test_duracao_do_padrao(self) -> None:
        assert duracao_do_padrao("alegre") == pytest.approx(8 * 4 * 60 / 104)
        assert duracao_do_padrao("calma", 4) == pytest.approx(4 * 4 * 60 / 76)


class TestEfeitos:
    @pytest.mark.parametrize("nome", sorted(EFEITOS))
    def test_cada_efeito_e_um_som_curto_e_limpo(self, nome: str) -> None:
        som = gerar_efeito(nome)
        assert som.dtype == np.float32 and np.isfinite(som).all()
        assert 0.1 < len(som) / TAXA < 3.5 and 0.05 < np.abs(som).max() <= 1.0
        assert np.array_equal(som, gerar_efeito(nome))  # sempre igual

    def test_efeito_desconhecido(self) -> None:
        with pytest.raises(KeyError):
            gerar_efeito("apito-de-trem")

    @pytest.mark.parametrize(
        ("texto", "esperado"),
        [
            ("o coelho pula alto", "boing"),
            ("ele cai na poça d'água", "splash"),
            ("as estrelas brilham no céu", "brilho"),
            ("está chovendo forte", "chuva"),
            ("o vento sopra as folhas", "whoosh"),
            ("toca o sino da escola", "ding"),
            ("ela anda devagar", "passos"),
            ("uma bolha estoura", "pop"),
            ("pop", "pop"),
            ("bom dia amigos", None),
            ("", None),
        ],
    )
    def test_efeito_do_texto(self, texto: str, esperado: str | None) -> None:
        assert efeito_do_texto(texto) == esperado


def _voz(duracao_s: float, taxa: int = TAXA, amplitude: float = 0.5) -> np.ndarray:
    n = np.arange(int(duracao_s * taxa))
    return (amplitude * np.sin(2 * np.pi * 200 * n / taxa)).astype(np.float32)


class TestMixagem:
    def test_carregar_mono_reamostra_para_44100(self, tmp_path: Path) -> None:
        estereo = np.stack([_voz(1.0, 24_000), _voz(1.0, 24_000)], axis=1)
        sf.write(str(tmp_path / "a.wav"), estereo, 24_000)
        mono = carregar_mono(tmp_path / "a.wav")
        assert mono.ndim == 1 and abs(len(mono) - TAXA) <= 1 and _dominante(mono) == pytest.approx(200, abs=3)
        sf.write(str(tmp_path / "b.wav"), _voz(1.0), TAXA)
        assert len(carregar_mono(tmp_path / "b.wav")) == TAXA

    def test_ducking_baixa_rapido_e_volta_devagar(self) -> None:
        voz = np.zeros(4 * TAXA, dtype=np.float32)
        voz[TAXA : 2 * TAXA] = _voz(1.0)
        ganho = ganho_de_ducking(voz)
        assert ganho.shape == voz.shape and ganho.dtype == np.float32
        assert ganho[int(0.9 * TAXA)] == pytest.approx(1.0, abs=0.01)  # antes da fala: música inteira
        assert ganho[int(1.6 * TAXA)] < 0.36  # durante: ~ -11 dB (0,28)
        assert 0.28 < ganho[int(2.1 * TAXA)] < 0.7  # a música ainda está voltando
        assert ganho[int(3.9 * TAXA)] > 0.95  # depois de um tempo, volta ao normal
        assert ganho.min() >= 0.27 and ganho.max() <= 1.0

    def test_a_musica_abaixa_quando_ha_fala(self) -> None:
        musica = _voz(6.0, amplitude=0.6)
        falas = [Fala(2.0, _voz(1.5, amplitude=0.5))]
        com = mixar(6.0, falas, musica=musica)
        sem = mixar(6.0, [], musica=musica)
        so_voz = mixar(6.0, falas)
        parte_da_musica = com[:, 0] - so_voz[:, 0]
        durante = _rms(parte_da_musica[int(2.4 * TAXA) : int(3.3 * TAXA)])
        antes = _rms(parte_da_musica[int(0.5 * TAXA) : int(1.5 * TAXA)])
        assert durante < 0.42 * antes and antes == pytest.approx(
            _rms(sem[int(0.5 * TAXA) : int(1.5 * TAXA), 0]), rel=0.05
        )

    def test_formato_estereo_e_duracao_exata(self) -> None:
        trilha = mixar(3.0, [Fala(0.5, _voz(1.0))])
        assert trilha.shape == (3 * TAXA, 2) and trilha.dtype == np.float32
        assert np.array_equal(trilha[:, 0], trilha[:, 1])

    def test_a_voz_entra_no_instante_certo(self) -> None:
        trilha = mixar(3.0, [Fala(1.0, _voz(0.5))])[:, 0]
        assert not trilha[: TAXA - 10].any() and np.abs(trilha[TAXA + 100 : TAXA + 5000]).max() > 0.3
        assert not trilha[int(1.5 * TAXA) + 10 :].any()

    def test_efeitos_com_ganho(self) -> None:
        alto = mixar(2.0, [], [Efeito(0.5, _voz(0.3), ganho=1.0)])
        baixo = mixar(2.0, [], [Efeito(0.5, _voz(0.3), ganho=0.25)])
        assert np.abs(alto).max() == pytest.approx(4 * np.abs(baixo).max(), rel=0.01)

    def test_nunca_estoura(self) -> None:
        trilha = mixar(2.0, [Fala(0.0, _voz(2.0, amplitude=0.9)), Fala(0.0, _voz(2.0, amplitude=0.9))])
        assert np.abs(trilha).max() <= 0.98 + 1e-6

    def test_som_fora_do_tempo_e_musica_de_tamanho_diferente(self) -> None:
        longa = mixar(1.0, [Fala(0.5, _voz(3.0))], musica=_voz(5.0))
        curta = mixar(3.0, [], musica=_voz(1.0))
        assert longa.shape[0] == TAXA and curta.shape[0] == 3 * TAXA
        assert not curta[int(1.2 * TAXA) :].any()  # a música acabou: o resto é silêncio
        assert mixar(1.0, [Fala(9.0, _voz(1.0))], [Efeito(-5.0, _voz(0.1))]).shape[0] == TAXA

    def test_salvar_wav(self, tmp_path: Path) -> None:
        trilha = mixar(1.0, [Fala(0.0, _voz(1.0))])
        caminho = salvar_wav(tmp_path / "sub" / "mix.wav", trilha)
        dados, taxa = sf.read(str(caminho), always_2d=True)
        assert taxa == TAXA and dados.shape == (TAXA, 2) and np.abs(dados).max() > 0.3


class TestLegendas:
    @pytest.mark.parametrize(
        ("segundos", "esperado"),
        [
            (0, "00:00:00,000"),
            (3661.5, "01:01:01,500"),
            (59.9996, "00:01:00,000"),
            (-4, "00:00:00,000"),
            (0.0014, "00:00:00,001"),
        ],
    )
    def test_formatar_tempo(self, segundos: float, esperado: str) -> None:
        assert formatar_tempo(segundos) == esperado

    def test_quebra_de_textos_longos(self) -> None:
        assert quebrar_em_partes("") == [] and quebrar_em_partes("   ") == []
        assert quebrar_em_partes("Olá!") == ["Olá!"]
        longo = " ".join(["Lila brinca no jardim com os amigos."] * 6)
        partes = quebrar_em_partes(longo)
        assert len(partes) > 1 and all(len(p) <= 2 * LARGURA_DA_LINHA for p in partes)
        assert " ".join(partes).split() == longo.split()  # nenhuma palavra se perde nem se parte

    def test_srt_valido_numerado_e_sem_sobreposicao(self) -> None:
        srt = gerar_srt([(4.0, 6.0, "Segunda fala."), (0.5, 2.0, "Olá, eu sou a Lila!")])
        blocos = srt.strip().split("\n\n")
        assert len(blocos) == 2 and blocos[0].startswith("1\n00:00:00,500 --> 00:00:02,000\nOlá, eu sou a Lila!")
        assert blocos[1].startswith("2\n00:00:04,000 --> 00:00:06,000\nSegunda fala.")
        assert srt.endswith("\n") and gerar_srt([]) == "" and gerar_srt([(0, 1, "  ")]) == ""

    def test_fala_curta_ganha_duracao_minima_mas_nao_invade_a_proxima(self) -> None:
        srt = gerar_srt([(0.0, 0.2, "Oi!"), (0.5, 2.0, "Tudo bem?")])
        tempos = re.findall(r"(\d\d:\d\d:\d\d,\d{3}) --> (\d\d:\d\d:\d\d,\d{3})", srt)
        assert tempos[0][1] <= tempos[1][0]  # a primeira acaba quando a segunda entra
        assert tempos[0] == ("00:00:00,000", "00:00:00,500")

    def test_texto_longo_vira_varias_legendas_repartindo_o_tempo(self) -> None:
        texto = " ".join(["Era uma vez um coelho muito curioso que adorava explorar o jardim."] * 3)
        srt = gerar_srt([(1.0, 13.0, texto)])
        legendas = [b for b in srt.strip().split("\n\n")]
        assert len(legendas) >= 3
        tempos = re.findall(r"(\d\d):(\d\d):(\d\d),(\d{3}) --> (\d\d):(\d\d):(\d\d),(\d{3})", srt)
        segundos = [
            (int(a) * 3600 + int(b) * 60 + int(c) + int(d) / 1000, int(e) * 3600 + int(f) * 60 + int(g) + int(h) / 1000)
            for a, b, c, d, e, f, g, h in tempos
        ]
        assert segundos[0][0] == pytest.approx(1.0) and segundos[-1][1] == pytest.approx(13.0, abs=0.01)
        assert all(fim > ini for ini, fim in segundos) and all(
            segundos[i][1] <= segundos[i + 1][0] + 1e-6 for i in range(len(segundos) - 1)
        )
        for legenda in legendas:
            linhas = legenda.split("\n")[2:]
            assert 1 <= len(linhas) <= 2 and all(len(linha) <= LARGURA_DA_LINHA for linha in linhas)
