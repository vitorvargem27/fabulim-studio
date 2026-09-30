"""Medição real dos motores (voz, recorte de fundo e imagem) e o que o benchmark faz com ela."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import types
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.benchmark import medidor_recorte, medidor_voz
from app.benchmark.medidores import (
    ASSINATURA_PNG,
    NAO_INSTALADO,
    PASTA,
    SEM_BIBLIOTECA,
    MedidoresReais,
    _e_png,
    _final_da_saida,
    _json_da_saida,
    _tempo,
)
from app.benchmark.resultado import ResultadoBench
from app.benchmark.runner import PENDENTES, BenchmarkRunner, BenchmarkStore
from app.config import Settings
from app.container import Servicos
from app.hardware.capacidades import calcular, eta_imagem, eta_personagem, eta_recorte, eta_voz, formatar_duracao
from app.hardware.perfil import classificar
from app.jobs.worker import JobCanceled

from .builders import carregar_thinkpad
from .conftest import MedidoresFalsos, ollama_falso

LOG_DO_SD = (
    "[INFO] image.cpp:529  - get_learned_condition completed, taking 21.82s\n"
    "  |####| 4/4 - 13.94s/it\r  |####| 4/4 - 13.94s/it\n"
    "[INFO] image.cpp:899  - sampling completed, taking 63.57s\n"
    "[INFO] image.cpp:624  - decode_first_stage completed, taking 13.76s\n"
    "[INFO] image.cpp:1050 - generate_image completed in 99.19s\n"
)


class CtxFalso:
    """O que o medidor usa do job: progresso, log, ponto de controle e subprocesso (aqui, respostas prontas)."""

    def __init__(self, responder: Callable[[Sequence[str]], subprocess.CompletedProcess[str] | Exception]) -> None:
        self._responder = responder
        self.comandos: list[list[str]] = []
        self.cwds: list[Path | None] = []
        self.progressos: list[float] = []
        self.logs: list[tuple[str, str]] = []

    def progresso(self, fracao: float, mensagem: str | None = None) -> None:
        self.progressos.append(fracao)

    def log(self, mensagem: str, nivel: str = "INFO") -> None:
        self.logs.append((nivel, mensagem))

    def ponto_de_controle(self) -> None:
        return None

    def executar_processo(
        self,
        comando: Sequence[str],
        *,
        timeout: float,
        ao_tick: Callable[[float], None] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self.comandos.append(list(comando))
        self.cwds.append(cwd)
        if ao_tick:
            ao_tick(3.0)
        resposta = self._responder(comando)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


def concluido(saida: str, codigo: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], codigo, saida, "")


def escrever_png(comando: Sequence[str]) -> None:
    """Faz o papel do sd-cli: grava uma imagem (assinatura de PNG e corpo) no caminho pedido em ``-o``."""
    destino = Path(comando[list(comando).index("-o") + 1])
    destino.write_bytes(ASSINATURA_PNG + b"\x00" * 20_000)


def medidores(settings: Settings, *, vulkan: bool = True) -> MedidoresReais:
    return MedidoresReais(settings, lambda: vulkan)


FAIXA = (0.4, 0.9)


class TestAuxiliares:
    def test_json_da_ultima_linha_ignora_o_ruido(self) -> None:
        texto = 'aviso do onnx\n{"nao": "e o ultimo"}\nmais ruido\n{"rtf": 0.5}\n'
        assert _json_da_saida(texto) == {"rtf": 0.5}

    def test_sem_json_ou_json_quebrado_e_erro(self) -> None:
        for texto in ("", "so texto", '{"quebrado": ', "{nao e json}", "[1, 2]"):
            with pytest.raises(ValueError, match="não devolveu"):
                _json_da_saida(texto)

    def test_final_da_saida_junta_as_ultimas_linhas_e_ignora_barras_de_progresso(self) -> None:
        assert _final_da_saida("a\nb\r\nc\n\nd\n", linhas=2) == "c | d"
        assert len(_final_da_saida("x" * 1000)) == 400

    def test_tempos_do_log_do_sd(self) -> None:
        assert _tempo(r"generate_image completed in ([0-9.]+)s", LOG_DO_SD) == 99.19
        assert _tempo(r"sampling completed, taking ([0-9.]+)s", LOG_DO_SD) == 63.57
        assert _tempo(r"nao existe ([0-9.]+)", LOG_DO_SD) is None

    def test_e_png(self, tmp_path: Path) -> None:
        bom = tmp_path / "bom.png"
        bom.write_bytes(ASSINATURA_PNG + b"\x00" * 20_000)
        pequeno = tmp_path / "pequeno.png"
        pequeno.write_bytes(ASSINATURA_PNG)
        falso = tmp_path / "falso.png"
        falso.write_bytes(b"GIF89a" + b"\x00" * 20_000)
        assert _e_png(bom) and not _e_png(pequeno) and not _e_png(falso) and not _e_png(tmp_path / "nada.png")

    def test_formatar_duracao(self) -> None:
        assert (
            formatar_duracao(45) == "45 s" and formatar_duracao(99.2) == "1,7 min" and formatar_duracao(89.4) == "89 s"
        )


class TestVoz:
    def test_motor_ausente_ensina_onde_instalar(self, settings: Settings) -> None:
        (settings.models_dir / "voz" / "kokoro-v1.0.onnx").unlink()
        ctx = CtxFalso(lambda _c: concluido(""))
        r = medidores(settings).voz(ctx, FAIXA)  # type: ignore[arg-type]
        assert (r.task, r.status, r.detail) == ("tts", "skipped", NAO_INSTALADO)
        assert ctx.comandos == []  # nem tenta rodar

    def test_falta_a_biblioteca_python(self, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.ferramentas.detectar.tem_modulo", lambda nome: nome != "kokoro_onnx")
        r = medidores(settings).voz(CtxFalso(lambda _c: concluido("")), FAIXA)  # type: ignore[arg-type]
        assert r.status == "skipped" and r.detail == SEM_BIBLIOTECA

    def test_mede_e_conta_quantos_segundos_leva_cada_minuto_de_fala(self, settings: Settings) -> None:
        saida = (
            'ruído das bibliotecas\n{"load_s": 2.6, "synth_s": 2.5, "audio_s": 5.0, "rtf": 0.5, "sample_rate": 24000}\n'
        )
        ctx = CtxFalso(lambda _c: concluido(saida))
        r = medidores(settings).voz(ctx, FAIXA)  # type: ignore[arg-type]
        assert r.status == "ok" and r.task == "tts" and r.model == "Kokoro 82M"
        assert r.metrics["rtf"] == 0.5 and "≈ 30 s para cada minuto de fala" in (r.detail or "")
        assert "Falou 5,0 s de áudio em 2,5 s" in (r.detail or "")  # vírgula decimal, como o usuário lê
        comando = ctx.comandos[0]  # lista de argumentos (nunca shell), com o Python do próprio app
        assert comando[0] == sys.executable and comando[1] == str(PASTA / "medidor_voz.py")
        assert comando[2].endswith("kokoro-v1.0.onnx") and comando[3].endswith("voices-v1.0.bin")
        assert ctx.cwds == [PASTA] and all(FAIXA[0] <= p <= FAIXA[1] for p in ctx.progressos)

    def test_processo_que_falha_vira_erro_com_o_motivo(self, settings: Settings) -> None:
        ctx = CtxFalso(lambda _c: concluido("Traceback...\nOSError: modelo corrompido", 1))
        r = medidores(settings).voz(ctx, FAIXA)  # type: ignore[arg-type]
        assert r.status == "error" and "código 1" in (r.detail or "") and "modelo corrompido" in (r.detail or "")

    def test_saida_sem_resultado_e_erro(self, settings: Settings) -> None:
        r = medidores(settings).voz(CtxFalso(lambda _c: concluido("nada útil")), FAIXA)  # type: ignore[arg-type]
        assert r.status == "error" and "não devolveu o resultado" in (r.detail or "")

    def test_passou_do_tempo(self, settings: Settings) -> None:
        r = medidores(settings).voz(CtxFalso(lambda _c: TimeoutError("o processo passou de 600 s")), FAIXA)  # type: ignore[arg-type]
        assert r.status == "error" and "Não terminou a tempo" in (r.detail or "")

    def test_cancelar_o_job_interrompe_a_medicao(self, settings: Settings) -> None:
        with pytest.raises(JobCanceled):
            medidores(settings).voz(CtxFalso(lambda _c: JobCanceled()), FAIXA)  # type: ignore[arg-type]


class TestRecorte:
    def test_motor_ausente(self, settings: Settings) -> None:
        (settings.models_dir / "recorte" / "birefnet-lite.onnx").unlink()
        r = medidores(settings).recorte(CtxFalso(lambda _c: concluido("")), FAIXA)  # type: ignore[arg-type]
        assert (r.task, r.status, r.detail) == ("cutout", "skipped", NAO_INSTALADO)

    def test_mede_a_inferencia(self, settings: Settings) -> None:
        saida = '{"load_s": 13.6, "infer_s": 20.4, "size": 1024, "output_shape": [1, 1, 1024, 1024], "provider": "cpu"}'
        ctx = CtxFalso(lambda _c: concluido(saida))
        r = medidores(settings).recorte(ctx, FAIXA)  # type: ignore[arg-type]
        assert r.status == "ok" and r.model == "BiRefNet lite" and r.metrics["infer_s"] == 20.4
        assert "≈ 20 s por imagem de 1024 px" in (r.detail or "")
        assert ctx.comandos[0][1] == str(PASTA / "medidor_recorte.py") and ctx.comandos[0][2].endswith(
            "birefnet-lite.onnx"
        )

    def test_resultado_sem_o_tempo_ainda_e_um_resultado(self, settings: Settings) -> None:
        r = medidores(settings).recorte(CtxFalso(lambda _c: concluido('{"load_s": 1}')), FAIXA)  # type: ignore[arg-type]
        assert r.status == "ok" and r.detail == "Medido."

    def test_falha(self, settings: Settings) -> None:
        r = medidores(settings).recorte(CtxFalso(lambda _c: concluido("sem memória", 3)), FAIXA)  # type: ignore[arg-type]
        assert r.status == "error" and "sem memória" in (r.detail or "")


class TestImagem:
    def _ctx(self, respostas: list[subprocess.CompletedProcess[str] | Exception], gravar: bool = True) -> CtxFalso:
        fila = list(respostas)

        def responder(comando: Sequence[str]) -> subprocess.CompletedProcess[str] | Exception:
            resposta = fila.pop(0)
            if gravar and not isinstance(resposta, Exception) and resposta.returncode == 0:
                escrever_png(comando)
            return resposta

        return CtxFalso(responder)

    def test_motor_ausente(self, settings: Settings) -> None:
        (settings.models_dir / "imagem" / "flux-2-klein-4b-Q4_0.gguf").unlink()
        ctx = self._ctx([])
        r = medidores(settings).imagem(ctx, FAIXA)  # type: ignore[arg-type]
        assert (r.task, r.status, r.detail) == ("image", "skipped", NAO_INSTALADO) and ctx.comandos == []

    def test_gera_de_verdade_pela_placa_de_video_e_le_os_tempos_do_log(self, settings: Settings) -> None:
        ctx = self._ctx([concluido(LOG_DO_SD)])
        r = medidores(settings, vulkan=True).imagem(ctx, FAIXA)  # type: ignore[arg-type]
        assert r.status == "ok" and r.task == "image" and r.model == "FLUX.2 klein 4B (Q4_0)"
        m = r.metrics
        assert m["backend"] == "vulkan" and m["size"] == 512 and m["steps"] == 4 and m["fell_back"] is False
        assert (m["generate_s"], m["text_s"], m["sampling_s"], m["decode_s"]) == (99.19, 21.82, 63.57, 13.76)
        assert "512 px (4 passos), com a placa de vídeo (Vulkan)" in (r.detail or "")

    def test_o_comando_e_uma_lista_de_argumentos_com_o_modelo_certo(self, settings: Settings) -> None:
        ctx = self._ctx([concluido(LOG_DO_SD)])
        medidores(settings).imagem(ctx, FAIXA)  # type: ignore[arg-type]
        cmd = ctx.comandos[0]
        assert cmd[0].replace("\\", "/").endswith("sd-cpp/sd-cli.exe") and ctx.cwds == [Path(cmd[0]).parent]
        opcoes = {
            cmd[i]: cmd[i + 1]
            for i in range(1, len(cmd) - 1)
            if cmd[i].startswith("-") and not cmd[i + 1].startswith("-")
        }
        assert opcoes["--diffusion-model"].endswith("flux-2-klein-4b-Q4_0.gguf")
        assert opcoes["--vae"].endswith("flux2-vae.safetensors") and opcoes["--llm"].endswith("Qwen3-4B-Q4_K_M.gguf")
        assert (opcoes["-W"], opcoes["-H"], opcoes["--steps"], opcoes["--cfg-scale"]) == ("512", "512", "4", "1.0")
        assert "--diffusion-fa" in cmd and Path(opcoes["-o"]).name == "imagem.png"
        assert all(isinstance(parte, str) for parte in cmd)

    def test_sem_vulkan_usa_o_programa_de_processador(self, settings: Settings) -> None:
        ctx = self._ctx([concluido(LOG_DO_SD)])
        r = medidores(settings, vulkan=False).imagem(ctx, FAIXA)  # type: ignore[arg-type]
        assert ctx.comandos[0][0].replace("\\", "/").endswith("sd-cpp-cpu/sd-cli.exe")
        assert r.metrics["backend"] == "cpu" and "no processador" in (r.detail or "")

    def test_se_a_placa_de_video_falha_refaz_no_processador(self, settings: Settings) -> None:
        ctx = self._ctx([concluido("ggml_vulkan: erro de memória", 1), concluido(LOG_DO_SD)])
        r = medidores(settings).imagem(ctx, FAIXA)  # type: ignore[arg-type]
        assert r.status == "ok" and r.metrics["backend"] == "cpu" and r.metrics["fell_back"] is True
        assert "A placa de vídeo falhou" in (r.detail or "")
        assert any(nivel == "WARNING" and "erro de memória" in msg for nivel, msg in ctx.logs)
        assert len(ctx.comandos) == 2

    def test_falha_nos_dois_caminhos_e_erro(self, settings: Settings) -> None:
        ctx = self._ctx([concluido("falha A", 1), concluido("falha B", 2)])
        r = medidores(settings).imagem(ctx, FAIXA)  # type: ignore[arg-type]
        assert r.status == "error" and "vulkan: falha A" in (r.detail or "") and "cpu: falha B" in (r.detail or "")

    def test_processo_que_termina_sem_gerar_imagem_conta_como_falha(self, settings: Settings) -> None:
        ctx = self._ctx([concluido("ok mas sem arquivo"), concluido("de novo sem arquivo")], gravar=False)
        assert medidores(settings).imagem(ctx, FAIXA).status == "error"  # type: ignore[arg-type]

    def test_passou_do_tempo_no_primeiro_e_funciona_no_segundo(self, settings: Settings) -> None:
        ctx = self._ctx([TimeoutError("o processo passou de 1800 s"), concluido(LOG_DO_SD)])
        r = medidores(settings).imagem(ctx, FAIXA)  # type: ignore[arg-type]
        assert r.status == "ok" and r.metrics["fell_back"] is True

    def test_apaga_a_imagem_de_teste(self, settings: Settings) -> None:
        medidores(settings).imagem(self._ctx([concluido(LOG_DO_SD)]), FAIXA)  # type: ignore[arg-type]
        assert list(settings.data_dir.glob("benchmark-*")) == []

    def test_o_andamento_fica_dentro_da_faixa_do_job(self, settings: Settings) -> None:
        ctx = self._ctx([concluido(LOG_DO_SD)])
        medidores(settings).imagem(ctx, FAIXA)  # type: ignore[arg-type]
        assert ctx.progressos and all(FAIXA[0] <= p <= FAIXA[1] for p in ctx.progressos)

    def test_sem_nenhum_programa_de_imagem_no_disco_fica_como_nao_instalado(self, settings: Settings) -> None:
        for pasta in ("sd-cpp", "sd-cpp-cpu"):  # o motor "existia" na checagem, mas os programas sumiram no meio
            (settings.tools_dir / pasta / "sd-cli.exe").unlink()
        r = medidores(settings)._tentativas_de_imagem()
        assert r == []


class _CtxDoRunner:
    def __init__(self, cancelar_em: int | None = None) -> None:
        self.progressos: list[tuple[float, str | None]] = []
        self.logs: list[str] = []
        self._pontos = 0
        self._cancelar_em = cancelar_em

    def progresso(self, fracao: float, mensagem: str | None = None) -> None:
        self.progressos.append((fracao, mensagem))

    def log(self, mensagem: str, nivel: str = "INFO") -> None:
        self.logs.append(mensagem)

    def ponto_de_controle(self) -> None:
        self._pontos += 1
        if self._cancelar_em is not None and self._pontos >= self._cancelar_em:
            raise JobCanceled


class TestRunner:
    def _runner(self, servicos: Servicos, medidores_: Any) -> BenchmarkRunner:
        return BenchmarkRunner(ollama_falso()[0], servicos.benchmarks, "fp", medidores_)

    def test_mede_tudo_na_ordem_e_guarda_cada_resultado(self, servicos: Servicos) -> None:
        falsos = MedidoresFalsos()
        ctx = _CtxDoRunner()
        r = self._runner(servicos, falsos).executar(ctx)  # type: ignore[arg-type]
        assert falsos.chamadas == ["voz", "recorte", "imagem"]
        assert (r["llm"], r["voice"], r["cutout"], r["image"]) == ("ok", "ok", "ok", "ok")
        tarefas = {t["task"]: t for t in servicos.benchmarks.ultimos()}
        assert set(tarefas) == {"llm_ollama", "tts", "cutout", "image", "music", "video"}
        assert tarefas["image"]["status"] == "ok" and tarefas["image"]["metrics"]["wall_s"] == 100.0
        fracoes = [f for f, _ in ctx.progressos]
        assert fracoes == sorted(fracoes) and fracoes[-1] == 1.0
        assert any("imagem" in (m or "").lower() for _, m in ctx.progressos)

    def test_o_que_ainda_nao_pode_ser_medido_fica_como_nao_medido_sem_falar_de_fase(self, servicos: Servicos) -> None:
        self._runner(servicos, MedidoresFalsos()).executar(_CtxDoRunner())  # type: ignore[arg-type]
        tarefas = {t["task"]: t for t in servicos.benchmarks.ultimos()}
        for nome, _motivo in PENDENTES:
            assert tarefas[nome]["status"] == "skipped" and "Fase" not in tarefas[nome]["detail"], nome

    def test_motor_nao_instalado_fica_registrado_como_nao_medido(self, servicos: Servicos) -> None:
        class SemMotor:
            def voz(self, ctx: Any, faixa: Any) -> ResultadoBench:
                return ResultadoBench("tts", "skipped", detail=NAO_INSTALADO)

            def recorte(self, ctx: Any, faixa: Any) -> ResultadoBench:
                return ResultadoBench("cutout", "skipped", detail=NAO_INSTALADO)

            def imagem(self, ctx: Any, faixa: Any) -> ResultadoBench:
                return ResultadoBench("image", "skipped", detail=NAO_INSTALADO)

        ctx = _CtxDoRunner()
        r = self._runner(servicos, SemMotor()).executar(ctx)  # type: ignore[arg-type]
        assert (r["voice"], r["cutout"], r["image"]) == ("skipped", "skipped", "skipped")
        assert servicos.benchmarks.medicoes().keys() == {
            "llm_gen_tok_s",
            "llm_prefill_tok_s",
            "llm_modelo",
            "llm_processador",
            "llm_medido_em",
        }
        assert any("Ainda não instalado" in linha for linha in ctx.logs)

    def test_cancelar_no_meio_para_sem_gravar_o_que_faltava(self, servicos: Servicos) -> None:
        falsos = MedidoresFalsos()
        with pytest.raises(JobCanceled):
            self._runner(servicos, falsos).executar(_CtxDoRunner(cancelar_em=3))  # type: ignore[arg-type]
        assert falsos.chamadas == ["voz"]  # o 1º ponto é antes do LLM, o 2º antes da voz e o 3º antes do recorte

    def test_medicoes_novas_alimentam_a_matriz(self, servicos: Servicos) -> None:
        self._runner(servicos, MedidoresFalsos()).executar(_CtxDoRunner())  # type: ignore[arg-type]
        m = servicos.benchmarks.medicoes()
        assert m["voz_rtf"] == 0.5 and m["recorte_seg"] == 12.0 and m["imagem_seg"] == 100.0
        assert (m["imagem_lado"], m["imagem_passos"], m["imagem_backend"]) == (512, 4, "vulkan")
        assert m["imagem_modelo"] == "FLUX.2 klein 4B (Q4_0)"

    def test_medicao_com_erro_nao_vira_numero(self, servicos: Servicos) -> None:
        loja = BenchmarkStore(servicos.db)
        for tarefa in ("tts", "cutout", "image"):
            loja.salvar(ResultadoBench(tarefa, "error", detail="quebrou"))
        assert loja.medicoes() == {}


class TestCapacidadesMedidas:
    def _caps(self, **medicoes: Any) -> dict[str, Any]:
        dados = carregar_thinkpad()
        return {c.id: c for c in calcular(dados, classificar(dados), medicoes)}

    def test_imagem_medida_troca_a_estimativa(self) -> None:
        sem = self._caps()["imagem"]
        assert sem.eta == "2 a 8 min por imagem" and sem.eta_medido is False
        com = self._caps(imagem_seg=112.0, imagem_lado=512, imagem_passos=4, imagem_backend="vulkan")["imagem"]
        assert com.eta_medido is True and com.eta == "≈ 1,9 min por imagem de 512 px (4 passos, com a placa de vídeo)"

    def test_personagem_e_calculado_a_partir_da_imagem_medida_e_continua_estimativa(self) -> None:
        cap = self._caps(imagem_seg=112.0)["variacoes_folha"]
        assert cap.eta == "≈ 18,7 min por personagem (10 imagens)" and cap.eta_medido is False
        assert self._caps()["variacoes_folha"].eta == "30 a 60 min por personagem"

    def test_voz_medida(self) -> None:
        rapida = self._caps(voz_rtf=0.74)["voz"]
        assert rapida.eta == "≈ 44 s para cada minuto de fala" and rapida.eta_medido is True
        assert "mais rápido que o tempo real" in rapida.motivo
        lenta = self._caps(voz_rtf=1.6)["voz"]
        assert "mais devagar que o tempo real" in lenta.motivo and lenta.eta == "≈ 1,6 min para cada minuto de fala"
        assert self._caps()["voz"].eta == "6 a 20 s por minuto de fala" and self._caps()["voz"].eta_medido is False

    def test_recorte_medido(self) -> None:
        cap = self._caps(recorte_seg=20.4)["recorte"]
        assert cap.eta == "≈ 20 s por imagem de 1024 px" and cap.eta_medido is True

    def test_valores_invalidos_sao_ignorados(self) -> None:
        for lixo in (None, 0, -3, "rápido", True):
            assert eta_imagem({"imagem_seg": lixo}) == (None, False)
            assert eta_voz({"voz_rtf": lixo}) == (None, False)
            assert eta_recorte({"recorte_seg": lixo}) == (None, False)
            assert eta_personagem({"imagem_seg": lixo}) is None

    def test_nenhum_tempo_estimado_repete_a_palavra_estimado(self) -> None:
        # a tela já escreve "(estimado)" ou "(medido)" ao lado; o texto não repete
        for cap in self._caps().values():
            assert "estimado" not in (cap.eta or ""), cap.id

    def test_o_que_nao_existe_em_modelos_nao_manda_instalar(self) -> None:
        dados = carregar_thinkpad()
        caps = {c.id: c for c in calcular(dados, classificar(dados), {}, {"imagem", "voz", "recorte"})}
        assert caps["musica"].estado == "available" and caps["musica_cantada"].estado == "unavailable"
        assert "Modelos" not in caps["musica_cantada"].motivo and "ACE-Step" in caps["musica_cantada"].motivo
        assert caps["voz_propria"].estado == caps["visao_local"].estado == "unavailable"
        assert "Modelos" not in caps["voz_propria"].motivo + caps["visao_local"].motivo
        sem_imagem = {c.id: c for c in calcular(dados, classificar(dados), {}, {"voz", "recorte"})}
        assert "abra Modelos" in sem_imagem["imagem"].motivo and sem_imagem["imagem"].eta is None
        assert "abra Modelos" in sem_imagem["clipe_rapido"].motivo  # o clipe rápido também precisa do motor de imagens


def _modulo_falso(nome: str, **atributos: Any) -> types.ModuleType:
    modulo = types.ModuleType(nome)
    for chave, valor in atributos.items():
        setattr(modulo, chave, valor)
    return modulo


class TestMedidoresDeUmProcesso:
    """Os scripts que rodam à parte, testados aqui por dentro com bibliotecas falsas (o real fica na suíte `hw`)."""

    def test_voz_mede_carga_sintese_e_fator_de_tempo_real(self, monkeypatch: pytest.MonkeyPatch) -> None:
        chamadas: dict[str, Any] = {}

        class Kokoro:
            def __init__(self, modelo: str, vozes: str) -> None:
                chamadas["carga"] = (modelo, vozes)

            def create(self, texto: str, *, voice: str, speed: float, lang: str) -> tuple[np.ndarray[Any, Any], int]:
                chamadas["fala"] = (texto, voice, speed, lang)
                chamadas["falas"] = chamadas.get("falas", 0) + 1
                return np.zeros(48_000, dtype=np.float32), 24_000  # 2 s de áudio

        monkeypatch.setitem(sys.modules, "kokoro_onnx", _modulo_falso("kokoro_onnx", Kokoro=Kokoro))
        dados = medidor_voz.medir("m.onnx", "v.bin")
        assert chamadas["carga"] == ("m.onnx", "v.bin")
        assert chamadas["fala"][1:] == ("pf_dora", 1.0, "pt-br") and "Bolinho" in chamadas["fala"][0]  # a última fala
        assert chamadas["falas"] == 2  # uma de aquecimento, que não conta, e a medida
        assert dados["audio_s"] == 2.0 and dados["sample_rate"] == 24_000 and dados["voice"] == "pf_dora"
        assert set(dados) == {"load_s", "warmup_s", "synth_s", "audio_s", "rtf", "sample_rate", "voice"}

    def test_voz_audio_vazio_nao_divide_por_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class Kokoro:
            def __init__(self, modelo: str, vozes: str) -> None:
                pass

            def create(self, *args: Any, **kwargs: Any) -> tuple[np.ndarray[Any, Any], int]:
                return np.zeros(0, dtype=np.float32), 24_000

        monkeypatch.setitem(sys.modules, "kokoro_onnx", _modulo_falso("kokoro_onnx", Kokoro=Kokoro))
        assert medidor_voz.medir("m", "v")["rtf"] is None

    def test_voz_main_imprime_o_json_na_ultima_linha(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(medidor_voz, "medir", lambda modelo, vozes: {"rtf": 0.7, "modelo": modelo})
        assert medidor_voz.main(["medidor_voz.py", "m.onnx", "v.bin"]) == 0
        assert json.loads(capsys.readouterr().out.strip().splitlines()[-1]) == {"rtf": 0.7, "modelo": "m.onnx"}
        assert medidor_voz.main(["medidor_voz.py"]) == 2
        assert "uso:" in capsys.readouterr().err

    def test_recorte_mede_carga_e_inferencia(self, monkeypatch: pytest.MonkeyPatch) -> None:
        capturado: dict[str, Any] = {}

        class Sessao:
            def __init__(self, modelo: str, providers: list[str]) -> None:
                capturado["carga"] = (modelo, providers)

            def get_inputs(self) -> list[Any]:
                return [types.SimpleNamespace(name="input_image")]

            def run(self, saidas: Any, entradas: dict[str, Any]) -> list[Any]:
                capturado["forma"] = entradas["input_image"].shape
                capturado["passadas"] = capturado.get("passadas", 0) + 1
                return [np.zeros((1, 1, 8, 8), dtype=np.float32)]

        monkeypatch.setitem(sys.modules, "onnxruntime", _modulo_falso("onnxruntime", InferenceSession=Sessao))
        dados = medidor_recorte.medir("b.onnx")
        assert capturado["carga"] == ("b.onnx", ["CPUExecutionProvider"]) and capturado["forma"] == (1, 3, 1024, 1024)
        assert capturado["passadas"] == 2 and {"first_s", "infer_s"} <= set(dados)  # a 1ª aquece, a 2ª é a que vale
        assert dados["size"] == 1024 and dados["output_shape"] == [1, 1, 8, 8] and dados["provider"] == "cpu"

    def test_recorte_main(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        monkeypatch.setattr(medidor_recorte, "medir", lambda modelo: {"infer_s": 1.5})
        assert medidor_recorte.main(["medidor_recorte.py", "b.onnx"]) == 0
        assert json.loads(capsys.readouterr().out.strip()) == {"infer_s": 1.5}
        assert medidor_recorte.main(["medidor_recorte.py"]) == 2

    def test_os_scripts_rodam_sozinhos_sem_importar_o_app(self) -> None:
        # rodam com `python medidor_x.py`, fora do pacote: nenhum `import app` nem import relativo
        for nome in ("medidor_voz.py", "medidor_recorte.py"):
            arvore = ast.parse((PASTA / nome).read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if isinstance(no, ast.ImportFrom):
                    assert no.level == 0 and not (no.module or "").startswith("app"), nome
                elif isinstance(no, ast.Import):
                    assert not any(a.name.startswith("app") for a in no.names), nome

    def test_os_scripts_terminam_com_o_json_quando_rodados_de_verdade(self, tmp_path: Path) -> None:
        # sem as bibliotecas de IA de verdade: o erro de uso (2) prova que o script inicia e responde sozinho
        r = subprocess.run([sys.executable, str(PASTA / "medidor_voz.py")], capture_output=True, text=True, timeout=60)
        assert r.returncode == 2 and "uso:" in r.stderr


@pytest.mark.hw
class TestMedidoresNaMaquinaReal:
    """Roda os motores instalados de verdade (voz ~10 s, recorte ~40 s, imagem ~2 min). Pulado se não estiverem."""

    class _CtxReal(CtxFalso):
        def __init__(self) -> None:
            super().__init__(lambda _c: concluido(""))

        def executar_processo(
            self,
            comando: Sequence[str],
            *,
            timeout: float,
            ao_tick: Callable[[float], None] | None = None,
            cwd: Path | None = None,
        ) -> subprocess.CompletedProcess[str]:
            proc = subprocess.run(list(comando), capture_output=True, text=True, timeout=timeout, cwd=cwd)
            return subprocess.CompletedProcess(list(comando), proc.returncode, proc.stdout + proc.stderr, "")

    @pytest.fixture
    def real(self) -> MedidoresReais:
        from app.config import carregar_configuracao
        from app.hardware.estado import HardwareState
        from app.hardware.perfil import obter

        settings = carregar_configuracao()
        estado = HardwareState(settings)
        return MedidoresReais(settings, lambda: bool(obter(estado.carregar() or {}, "acceleration.vulkan.available")))

    def test_voz_de_verdade(self, real: MedidoresReais) -> None:
        r = real.voz(self._CtxReal(), FAIXA)  # type: ignore[arg-type]
        if r.status == "skipped":
            pytest.skip(r.detail or "voz não instalada")
        assert r.status == "ok", r.detail
        assert r.metrics["audio_s"] > 2 and 0 < r.metrics["rtf"] < 20

    def test_recorte_de_verdade(self, real: MedidoresReais) -> None:
        r = real.recorte(self._CtxReal(), FAIXA)  # type: ignore[arg-type]
        if r.status == "skipped":
            pytest.skip(r.detail or "recorte não instalado")
        assert r.status == "ok", r.detail
        assert r.metrics["output_shape"] == [1, 1, 1024, 1024] and r.metrics["infer_s"] > 0

    def test_imagem_de_verdade(self, real: MedidoresReais) -> None:
        r = real.imagem(self._CtxReal(), FAIXA)  # type: ignore[arg-type]
        if r.status == "skipped":
            pytest.skip(r.detail or "motor de imagem não instalado")
        assert r.status == "ok", r.detail
        assert r.metrics["wall_s"] > 5 and r.metrics["size"] == 512
