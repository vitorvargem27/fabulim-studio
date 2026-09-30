"""Motores de IA (imagem, recorte, voz, texto): montagem dos comandos, falhas explicadas, cancelamento e contrato.

Nenhum modelo de verdade roda aqui: o contexto do job é um objeto que anota os comandos e, quando pedido, escreve o
arquivo que o programa real escreveria. Os motores de verdade são medidos na suíte de hardware (``pytest -m hw``).
"""

from __future__ import annotations

import inspect
import json
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from app.config import Settings
from app.ferramentas import detectar
from app.jobs.worker import JobCanceled
from app.motores import interfaces
from app.motores.fabrica import criar_motores, segundos_por_imagem_512
from app.motores.imagem import MotorDeImagemSdCpp
from app.motores.recorte import MotorDeRecorteBiRefNet
from app.motores.texto import SEM_MODELO, SEM_OLLAMA, MotorDeTextoOllama
from app.motores.tipos import ItemDeVoz, MotorFalhou, MotorIndisponivel, PedidoImagem, dimensoes_da_imagem
from app.motores.util import br, e_png, final_da_saida, formatar_duracao, json_da_saida, tempo_do_log
from app.motores.voz import VOZES, MotorDeVozKokoro, lingua_da_voz
from app.services.ollama import OllamaClient

from .conftest import ollama_falso
from .fakes_motores import ContextoDeTeste, ImagemFalsa, RecorteFalso, TextoFalso, VozFalsa, motores_falsos

Escritor = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


class ContextoComProcesso(ContextoDeTeste):
    """Contexto cujo ``executar_processo`` chama uma função do teste (que escreve os arquivos e devolve o resultado)."""

    def __init__(self, escritor: Escritor, cancelar_no_ponto: int | None = None) -> None:
        super().__init__(cancelar_no_ponto)
        self._escritor = escritor
        self.timeouts: list[float] = []
        self.pastas: list[Path | None] = []

    def executar_processo(
        self,
        comando: Sequence[str],
        *,
        timeout: float,
        ao_tick: Callable[[float], None] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self.comandos.append(list(comando))
        self.timeouts.append(timeout)
        self.pastas.append(cwd)
        if ao_tick:
            ao_tick(1.0)
        return self._escritor(comando)


def _resultado(codigo: int = 0, saida: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], codigo, saida, "")


def _escreve_png(caminho: Path, tamanho: tuple[int, int] = (256, 256)) -> None:
    """Um PNG de verdade e grande o bastante para passar na conferência (>= 10 KB), com ruído para não comprimir."""
    import os

    Image.frombytes("RGB", tamanho, os.urandom(tamanho[0] * tamanho[1] * 3)).save(caminho, "PNG")


def _saida_do_comando(comando: Sequence[str]) -> Path:
    return Path(comando[list(comando).index("-o") + 1])


class TestUtil:
    def test_final_da_saida_junta_as_ultimas_linhas_legiveis(self) -> None:
        texto = "a\r\n\r\n  b   c \nd\n\n"
        assert final_da_saida(texto, 2) == "b c | d"
        assert len(final_da_saida("x" * 900)) == 400

    def test_tempo_do_log(self) -> None:
        assert tempo_do_log(r"completed in ([0-9.]+)s", "generate_image completed in 78.25s") == 78.25
        assert tempo_do_log(r"completed in ([0-9.]+)s", "nada") is None

    def test_e_png_confere_tamanho_e_assinatura(self, tmp_path: Path) -> None:
        bom, pequeno, falso, ausente = (tmp_path / n for n in ("bom.png", "p.png", "f.png", "a.png"))
        _escreve_png(bom)
        Image.new("RGB", (4, 4)).save(pequeno, "PNG")
        falso.write_bytes(b"GIF89a" + b"\x00" * 20_000)
        assert e_png(bom) and not e_png(pequeno) and not e_png(falso) and not e_png(ausente)

    def test_json_da_saida_le_a_ultima_linha_com_json(self) -> None:
        assert json_da_saida('ruído da biblioteca\n{"a": 1}\n{"b": 2}\n') == {"b": 2}
        assert json_da_saida('{"a": 1}\nfim sem json') == {"a": 1}
        with pytest.raises(ValueError, match="não devolveu"):
            json_da_saida("nada de json\n{quebrado")

    def test_numeros_e_duracoes_como_o_usuario_le(self) -> None:
        assert br(4.87) == "4,9" and br(3, 0) == "3" and br("x") == "?" and br(None) == "?"
        assert formatar_duracao(45) == "45 s" and formatar_duracao(150) == "2,5 min"


class TestDimensoes:
    @pytest.mark.parametrize(
        ("formato", "qualidade", "esperado"),
        [
            ("16:9", "rascunho", (640, 352)),
            ("16:9", "padrao", (768, 432)),
            ("16:9", "alta", (1024, 576)),
            ("9:16", "rascunho", (352, 640)),
            ("9:16", "padrao", (432, 768)),
            ("1:1", "rascunho", (512, 512)),
            ("1:1", "padrao", (768, 768)),
            ("1:1", "alta", (1024, 1024)),
        ],
    )
    def test_tamanhos(self, formato: str, qualidade: str, esperado: tuple[int, int]) -> None:
        assert dimensoes_da_imagem(formato, qualidade) == esperado

    @pytest.mark.parametrize("formato", ["16:9", "9:16", "1:1"])
    @pytest.mark.parametrize("qualidade", ["rascunho", "padrao", "alta"])
    def test_sempre_multiplos_de_16(self, formato: str, qualidade: str) -> None:
        largura, altura = dimensoes_da_imagem(formato, qualidade)
        assert largura % 16 == 0 and altura % 16 == 0 and min(largura, altura) >= 256


class TestMotorDeImagem:
    def _motor(self, settings: Settings, vulkan: bool = True, medido: float | None = None) -> MotorDeImagemSdCpp:
        return MotorDeImagemSdCpp(settings, lambda: vulkan, lambda: medido)

    def test_indisponivel_diz_o_que_fazer(self, settings: Settings) -> None:
        assert self._motor(settings).indisponivel() is None
        (settings.models_dir / "imagem" / "flux-2-klein-4b-Q4_0.gguf").unlink()
        motivo = self._motor(settings).indisponivel()
        assert motivo is not None and "Modelos" in motivo and "Instalar tudo" in motivo

    def test_estimativa_escala_pelos_pixels_e_pela_referencia(self, settings: Settings) -> None:
        padrao = self._motor(settings)
        assert padrao.estimativa(512, 512) == pytest.approx(120.0)  # sem medição: valor de partida
        assert padrao.estimativa(1024, 512) == pytest.approx(240.0)
        medido = self._motor(settings, medido=80.0)
        assert medido.estimativa(512, 512) == pytest.approx(80.0)
        assert medido.estimativa(512, 512, com_referencia=True) == pytest.approx(104.0)

    def test_comando_com_referencias(self, settings: Settings, tmp_path: Path) -> None:
        pedido = PedidoImagem("um coelho", 768, 432, 42, referencias=(tmp_path / "a.png", tmp_path / "b.png"))
        cmd = self._motor(settings).comando("sd-cpp", pedido, tmp_path / "saida.png")
        assert Path(cmd[0]).name == "sd-cli.exe" and cmd[-2:] == ["-o", str(tmp_path / "saida.png")]
        assert cmd[cmd.index("-p") + 1] == "um coelho"
        assert (cmd[cmd.index("-W") + 1], cmd[cmd.index("-H") + 1], cmd[cmd.index("-s") + 1]) == ("768", "432", "42")
        assert cmd[cmd.index("--steps") + 1] == "4" and cmd[cmd.index("--cfg-scale") + 1] == "1.0"
        assert [cmd[i + 1] for i, a in enumerate(cmd) if a == "-r"] == [
            str(tmp_path / "a.png"),
            str(tmp_path / "b.png"),
        ]
        assert "--diffusion-fa" in cmd and all(isinstance(a, str) for a in cmd)  # lista de argumentos, nunca shell

    def test_o_prompt_vai_como_um_unico_argumento(self, settings: Settings, tmp_path: Path) -> None:
        perigoso = 'x" && del /q * & "'
        cmd = self._motor(settings).comando("sd-cpp", PedidoImagem(perigoso, 512, 512, 1), tmp_path / "s.png")
        assert cmd[cmd.index("-p") + 1] == perigoso

    def test_gera_pelo_vulkan_e_devolve_os_tempos_do_log(self, settings: Settings, tmp_path: Path) -> None:
        saida = tmp_path / "out" / "img.png"

        def escrever(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
            _escreve_png(_saida_do_comando(cmd))
            return _resultado(0, "sampling completed, taking 70.5s\ngenerate_image completed in 78.25s\n")

        ctx = ContextoComProcesso(escrever)
        r = self._motor(settings).gerar(ctx, PedidoImagem("p", 512, 512, 9), saida, faixa=(0.2, 0.6))
        assert saida.is_file() and r.caminho == saida and r.caminho_de_execucao == "vulkan"
        assert (
            r.metricas["generate_s"] == 78.25 and r.metricas["sampling_s"] == 70.5 and r.metricas["fell_back"] is False
        )
        assert "sd-cpp" in ctx.comandos[0][0] and "sd-cpp-cpu" not in ctx.comandos[0][0]
        assert ctx.timeouts == [3600] and ctx.pastas[0] == Path(ctx.comandos[0][0]).parent
        assert ctx.progressos and 0.2 <= ctx.progressos[0][0] <= 0.6  # o andamento fica dentro da faixa pedida

    def test_sem_vulkan_comeca_pelo_processador(self, settings: Settings, tmp_path: Path) -> None:
        def escrever(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
            _escreve_png(_saida_do_comando(cmd))
            return _resultado(0)

        ctx = ContextoComProcesso(escrever)
        r = self._motor(settings, vulkan=False).gerar(ctx, PedidoImagem("p", 512, 512, 1), tmp_path / "i.png")
        assert r.caminho_de_execucao == "cpu" and "sd-cpp-cpu" in ctx.comandos[0][0]

    def test_falha_passageira_na_placa_de_video_se_resolve_na_segunda_tentativa(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        chamadas: list[str] = []

        def escrever(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
            chamadas.append(cmd[0])
            if len(chamadas) == 1:
                return _resultado(1, "sampling for image 1/1 failed after 75.07s\nbackend cleanup failed")
            _escreve_png(_saida_do_comando(cmd))
            return _resultado(0)

        ctx = ContextoComProcesso(escrever)
        r = self._motor(settings).gerar(ctx, PedidoImagem("p", 512, 512, 1), tmp_path / "i.png", faixa=(0.2, 0.6))
        assert r.caminho_de_execucao == "vulkan" and r.metricas["attempts"] == 2 and r.metricas["fell_back"] is True
        assert all("sd-cpp-cpu" not in c for c in chamadas)  # o processador (7x mais lento) nem foi tentado
        assert (0.2, "Tentando de novo pela placa de vídeo...") in ctx.progressos
        assert any(nivel == "WARNING" and "vulkan" in msg for nivel, msg in ctx.logs)

    def test_se_a_placa_de_video_falha_duas_vezes_usa_o_processador(self, settings: Settings, tmp_path: Path) -> None:
        def escrever(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
            if "sd-cpp-cpu" in cmd[0]:
                _escreve_png(_saida_do_comando(cmd))
                return _resultado(0)
            return _resultado(3, "ggml_vulkan: erro\nfalhou")

        ctx = ContextoComProcesso(escrever)
        r = self._motor(settings).gerar(ctx, PedidoImagem("p", 512, 512, 1), tmp_path / "i.png")
        assert r.caminho_de_execucao == "cpu" and r.metricas["fell_back"] is True and r.metricas["attempts"] == 3
        assert [("sd-cpp-cpu" in c[0]) for c in ctx.comandos] == [False, False, True]
        assert any("processador" in (msg or "") for _, msg in ctx.progressos)

    def test_a_barra_de_progresso_do_processador_conta_com_ele_ser_bem_mais_lento(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        def escrever(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
            _escreve_png(_saida_do_comando(cmd))
            return _resultado(0)

        na_placa = ContextoComProcesso(escrever)
        no_processador = ContextoComProcesso(escrever)
        self._motor(settings, vulkan=True).gerar(na_placa, PedidoImagem("p", 512, 512, 1), tmp_path / "a.png")
        self._motor(settings, vulkan=False).gerar(no_processador, PedidoImagem("p", 512, 512, 1), tmp_path / "b.png")
        # o teste avisa "1 s decorrido" em cada um: no processador a fração andada é ~7x menor
        assert na_placa.progressos[0][0] == pytest.approx(7 * no_processador.progressos[0][0], rel=0.01)

    def test_falhando_em_todos_os_caminhos_explica_cada_tentativa(self, settings: Settings, tmp_path: Path) -> None:
        ctx = ContextoComProcesso(lambda cmd: _resultado(1, "ggml_vulkan: out of memory"))
        with pytest.raises(MotorFalhou) as erro:
            self._motor(settings).gerar(ctx, PedidoImagem("p", 512, 512, 1), tmp_path / "i.png")
        mensagem = str(erro.value)
        assert mensagem.count("vulkan: ggml_vulkan: out of memory") == 2 and "cpu: ggml_vulkan" in mensagem
        assert "ficou sem memória" in mensagem and "rascunho" in mensagem  # dica para o usuário
        assert not (tmp_path / "i.png").exists()

    def test_saida_que_nao_e_imagem_conta_como_falha(self, settings: Settings, tmp_path: Path) -> None:
        def escrever(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
            _saida_do_comando(cmd).write_bytes(b"lixo")
            return _resultado(0, "terminou")

        with pytest.raises(MotorFalhou):
            self._motor(settings).gerar(
                ContextoComProcesso(escrever), PedidoImagem("p", 512, 512, 1), tmp_path / "i.png"
            )
        assert not (tmp_path / "i.png").exists()

    def test_estouro_de_tempo_nao_repete_o_mesmo_caminho(self, settings: Settings, tmp_path: Path) -> None:
        chamadas: list[str] = []

        def escrever(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
            chamadas.append(cmd[0])
            if len(chamadas) == 1:
                raise TimeoutError("o processo passou de 3600 s")
            _escreve_png(_saida_do_comando(cmd))
            return _resultado(0)

        r = self._motor(settings).gerar(
            ContextoComProcesso(escrever), PedidoImagem("p", 512, 512, 1), tmp_path / "i.png"
        )
        # travou uma hora na placa de vídeo: repetir na placa gastaria outra hora, então vai direto ao processador
        assert r.caminho_de_execucao == "cpu" and len(chamadas) == 2 and r.metricas["fell_back"] is True

    @pytest.mark.parametrize("tamanho", [(500, 512), (512, 100), (4096, 512), (512, 4112)])
    def test_tamanhos_invalidos_sao_recusados_antes_de_rodar(
        self, settings: Settings, tmp_path: Path, tamanho: tuple[int, int]
    ) -> None:
        ctx = ContextoComProcesso(lambda cmd: _resultado(0))
        with pytest.raises(MotorFalhou, match="Tamanho de imagem"):
            self._motor(settings).gerar(ctx, PedidoImagem("p", *tamanho, 1), tmp_path / "i.png")
        assert ctx.comandos == []

    def test_sem_instalar_nao_roda(self, settings: Settings, tmp_path: Path) -> None:
        (settings.tools_dir / "sd-cpp" / "sd-cli.exe").unlink()
        ctx = ContextoComProcesso(lambda cmd: _resultado(0))
        with pytest.raises(MotorIndisponivel):
            self._motor(settings).gerar(ctx, PedidoImagem("p", 512, 512, 1), tmp_path / "i.png")

    def test_cancelar_no_meio_propaga(self, settings: Settings, tmp_path: Path) -> None:
        def escrever(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
            raise JobCanceled

        with pytest.raises(JobCanceled):
            self._motor(settings).gerar(
                ContextoComProcesso(escrever), PedidoImagem("p", 512, 512, 1), tmp_path / "i.png"
            )


class TestMotorDeRecorte:
    def test_recorta_e_junta_o_json_do_script(self, settings: Settings, tmp_path: Path) -> None:
        origem, saida = tmp_path / "o.png", tmp_path / "s" / "r.png"

        def escrever(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
            _escreve_png(Path(cmd[4]))
            return _resultado(0, 'ruído\n{"width": 200, "height": 300, "infer_s": 12.5}\n')

        ctx = ContextoComProcesso(escrever)
        dados = MotorDeRecorteBiRefNet(settings).recortar(ctx, origem, saida)
        assert dados["width"] == 200 and dados["infer_s"] == 12.5 and "wall_s" in dados
        cmd = ctx.comandos[0]
        assert cmd[1].endswith("recortar_imagem.py") and cmd[3] == str(origem) and cmd[-1] == "--caixa"
        assert "birefnet-lite.onnx" in cmd[2]

    def test_sem_caixa(self, settings: Settings, tmp_path: Path) -> None:
        def escrever(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
            _escreve_png(Path(cmd[4]))
            return _resultado(0)

        ctx = ContextoComProcesso(escrever)
        dados = MotorDeRecorteBiRefNet(settings).recortar(ctx, tmp_path / "o.png", tmp_path / "r.png", caixa=False)
        assert "--caixa" not in ctx.comandos[0] and "wall_s" in dados  # sem JSON na saída: segue só com o tempo

    def test_falha_explica_e_nao_deixa_arquivo(self, settings: Settings, tmp_path: Path) -> None:
        saida = tmp_path / "r.png"
        saida.write_bytes(b"resto")
        ctx = ContextoComProcesso(lambda cmd: _resultado(1, "onnxruntime: modelo corrompido"))
        with pytest.raises(MotorFalhou, match="modelo corrompido"):
            MotorDeRecorteBiRefNet(settings).recortar(ctx, tmp_path / "o.png", saida)
        assert not saida.exists()

    def test_estouro_de_tempo(self, settings: Settings, tmp_path: Path) -> None:
        def escrever(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
            raise TimeoutError("demorou")

        with pytest.raises(MotorFalhou, match="a tempo"):
            MotorDeRecorteBiRefNet(settings).recortar(
                ContextoComProcesso(escrever), tmp_path / "o.png", tmp_path / "r.png"
            )

    def test_indisponivel(self, settings: Settings, tmp_path: Path) -> None:
        (settings.models_dir / "recorte" / "birefnet-lite.onnx").unlink()
        motor = MotorDeRecorteBiRefNet(settings)
        assert motor.indisponivel() and "Modelos" in (motor.indisponivel() or "")
        with pytest.raises(MotorIndisponivel):
            motor.recortar(ContextoComProcesso(lambda c: _resultado()), tmp_path / "o.png", tmp_path / "r.png")


class TestMotorDeVoz:
    def _itens(self, tmp_path: Path) -> list[ItemDeVoz]:
        return [
            ItemDeVoz("Olá, amiguinho!", "pf_dora", 1.0, "pt-br", tmp_path / "voz" / "a.wav"),
            ItemDeVoz("Vamos brincar?", "pm_alex", 0.9, "pt-br", tmp_path / "voz" / "b.wav"),
        ]

    def test_fala_varios_textos_num_processo_so(self, settings: Settings, tmp_path: Path) -> None:
        itens = self._itens(tmp_path)
        vistos: dict[str, Any] = {}

        def escrever(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
            vistos["pedidos"] = json.loads(Path(cmd[-1]).read_text(encoding="utf-8"))
            for item in itens:
                item.saida.write_bytes(b"RIFF")
            return _resultado(0, 'ruído\n{"items": [{"duration_s": 1.5}, {"duration_s": 2.25}]}\n')

        ctx = ContextoComProcesso(escrever)
        resultados = MotorDeVozKokoro(settings).falar(ctx, itens, faixa=(0.1, 0.5))
        assert [r.duracao_s for r in resultados] == [1.5, 2.25] and [r.saida for r in resultados] == [
            i.saida for i in itens
        ]
        assert len(ctx.comandos) == 1 and ctx.comandos[0][1].endswith("sintetizar_voz.py")
        assert vistos["pedidos"][0] == {
            "texto": "Olá, amiguinho!",
            "voz": "pf_dora",
            "velocidade": 1.0,
            "lingua": "pt-br",
            "saida": str(itens[0].saida),
        }
        assert vistos["pedidos"][1]["velocidade"] == 0.9
        assert itens[0].saida.parent.is_dir()

    def test_lista_vazia_nao_roda_nada(self, settings: Settings) -> None:
        ctx = ContextoComProcesso(lambda c: _resultado())
        assert MotorDeVozKokoro(settings).falar(ctx, []) == [] and ctx.comandos == []

    def test_falha_do_processo(self, settings: Settings, tmp_path: Path) -> None:
        ctx = ContextoComProcesso(lambda c: _resultado(1, "espeak não encontrado"))
        with pytest.raises(MotorFalhou, match="espeak"):
            MotorDeVozKokoro(settings).falar(ctx, self._itens(tmp_path))

    def test_estouro_de_tempo(self, settings: Settings, tmp_path: Path) -> None:
        def escrever(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
            raise TimeoutError("demorou")

        with pytest.raises(MotorFalhou, match="a tempo"):
            MotorDeVozKokoro(settings).falar(ContextoComProcesso(escrever), self._itens(tmp_path))

    def test_saida_sem_duracoes_ou_com_quantidade_errada(self, settings: Settings, tmp_path: Path) -> None:
        itens = self._itens(tmp_path)
        with pytest.raises(MotorFalhou, match="durações"):
            MotorDeVozKokoro(settings).falar(ContextoComProcesso(lambda c: _resultado(0, "sem json")), itens)

        def poucos(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
            itens[0].saida.write_bytes(b"x")
            return _resultado(0, '{"items": [{"duration_s": 1.0}]}')

        with pytest.raises(MotorFalhou, match="todos os áudios"):
            MotorDeVozKokoro(settings).falar(ContextoComProcesso(poucos), itens)

    def test_audio_que_nao_apareceu_no_disco(self, settings: Settings, tmp_path: Path) -> None:
        ctx = ContextoComProcesso(lambda c: _resultado(0, '{"items": [{"duration_s": 1}, {"duration_s": 1}]}'))
        with pytest.raises(MotorFalhou, match="todos os áudios"):
            MotorDeVozKokoro(settings).falar(ctx, self._itens(tmp_path))

    def test_indisponivel_sem_a_biblioteca(self, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(detectar, "tem_modulo", lambda nome: nome != "kokoro_onnx")
        motivo = MotorDeVozKokoro(settings).indisponivel()
        assert motivo is not None and "voz" in motivo

    def test_as_vozes_em_portugues_e_ingles(self) -> None:
        assert {v["id"] for v in VOZES["pt-BR"]} == {"pf_dora", "pm_alex", "pm_santa"}
        assert {"af_heart", "am_adam"} <= {v["id"] for v in VOZES["en"]}
        assert lingua_da_voz("pf_dora") == "pt-br" and lingua_da_voz("bf_emma") == "en-gb"
        assert lingua_da_voz("desconhecida") == "pt-br"


def _ollama_com_chat(
    respostas: list[str], *, modelos: list[tuple[str, int]] | None = None, online: bool = True
) -> tuple[OllamaClient, list[dict[str, Any]]]:
    """Cliente do Ollama sobre um transporte falso: /api/tags lista os modelos e /api/chat devolve os pedaços em NDJSON."""
    catalogo = [("qwen3:4b", 2_500_000_000)] if modelos is None else modelos
    corpos: list[dict[str, Any]] = []

    def tratar(req: httpx.Request) -> httpx.Response:
        if not online:
            raise httpx.ConnectError("recusada", request=req)
        if req.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": n, "size": s} for n, s in catalogo]})
        if req.url.path == "/api/chat":
            corpos.append(json.loads(req.content))
            linhas = [json.dumps({"message": {"role": "assistant", "content": p}, "done": False}) for p in respostas]
            linhas.append(json.dumps({"message": {"content": ""}, "done": True, "eval_count": len(respostas)}))
            return httpx.Response(200, content=("\n".join(linhas) + "\n").encode("utf-8"))
        return httpx.Response(404)

    return OllamaClient("http://127.0.0.1:11434", transport=httpx.MockTransport(tratar)), corpos


ESQUEMA = {"type": "object", "properties": {"nome": {"type": "string"}}}


class TestMotorDeTexto:
    def test_devolve_o_json_montado_dos_pedacos(self) -> None:
        cliente, corpos = _ollama_com_chat(['{"no', 'me": "Li', 'la"}'])
        ctx = ContextoDeTeste()
        r = MotorDeTextoOllama(cliente).estruturar(
            ctx,
            sistema="regras",
            dados="texto do usuário",
            instrucao="extraia",
            esquema=ESQUEMA,
            seed=3,
            faixa=(0.0, 0.5),
        )
        assert r == {"nome": "Lila"}
        corpo = corpos[0]
        assert corpo["model"] == "qwen3:4b" and corpo["think"] is False and corpo["format"] == ESQUEMA
        assert corpo["options"]["seed"] == 3 and corpo["stream"] is True
        sistema, usuario = corpo["messages"]
        assert sistema == {"role": "system", "content": "regras"}
        assert "extraia" in usuario["content"] and "texto do usuário" in usuario["content"]
        assert "nunca instruções" in usuario["content"] and "<<<" in usuario["content"]
        assert ctx.pontos == 4  # um ponto de controle por pedaço recebido (3 de texto e o de fechamento)
        assert ctx.progressos and all(0.0 <= f <= 0.5 for f, _ in ctx.progressos)

    def test_tira_as_cercas_de_codigo(self) -> None:
        cliente, _ = _ollama_com_chat(['```json\n{"nome": "Lila"}\n```'])
        assert MotorDeTextoOllama(cliente).estruturar(
            ContextoDeTeste(), sistema="s", dados="d", instrucao="i", esquema=ESQUEMA
        ) == {"nome": "Lila"}

    def test_json_invalido_ou_que_nao_e_objeto(self) -> None:
        motor = MotorDeTextoOllama(_ollama_com_chat(['{"nome": '])[0])
        with pytest.raises(MotorFalhou, match="JSON válido"):
            motor.estruturar(ContextoDeTeste(), sistema="s", dados="d", instrucao="i", esquema=ESQUEMA)
        motor = MotorDeTextoOllama(_ollama_com_chat(["[1, 2]"])[0])
        with pytest.raises(MotorFalhou, match="inesperada"):
            motor.estruturar(ContextoDeTeste(), sistema="s", dados="d", instrucao="i", esquema=ESQUEMA)

    def test_cancelar_no_meio_fecha_o_fluxo(self) -> None:
        cliente, _ = _ollama_com_chat(["a", "b", "c", "d"])
        with pytest.raises(JobCanceled):
            MotorDeTextoOllama(cliente).estruturar(
                ContextoDeTeste(cancelar_no_ponto=2), sistema="s", dados="d", instrucao="i", esquema=ESQUEMA
            )

    def test_escolhe_o_modelo_preferido_e_ignora_embeddings(self) -> None:
        cliente, _ = _ollama_com_chat(
            [],
            modelos=[("nomic-embed-text", 300_000_000), ("qwen3:8b", 5_000_000_000), ("qwen3:4b", 2_500_000_000)],
        )
        assert MotorDeTextoOllama(cliente).modelo() == "qwen3:8b"
        assert MotorDeTextoOllama(cliente, preferido="qwen3:4b").modelo() == "qwen3:4b"

    def test_sem_preferido_usa_o_maior_que_cabe(self) -> None:
        cliente, _ = _ollama_com_chat(
            [], modelos=[("a:1b", 1_000_000_000), ("b:7b", 4_700_000_000), ("c:70b", 40_000_000_000)]
        )
        assert MotorDeTextoOllama(cliente).modelo() == "b:7b"
        so_grande, _ = _ollama_com_chat([], modelos=[("c:70b", 40_000_000_000)])
        assert MotorDeTextoOllama(so_grande).modelo() == "c:70b"

    def test_sem_ollama_e_sem_modelo(self) -> None:
        fora = MotorDeTextoOllama(_ollama_com_chat([], online=False)[0])
        assert fora.indisponivel() == SEM_OLLAMA
        vazio = MotorDeTextoOllama(_ollama_com_chat([], modelos=[])[0])
        assert vazio.indisponivel() == SEM_MODELO
        with pytest.raises(MotorIndisponivel):
            fora.estruturar(ContextoDeTeste(), sistema="s", dados="d", instrucao="i", esquema=ESQUEMA)
        assert MotorDeTextoOllama(_ollama_com_chat([])[0]).indisponivel() is None

    def test_ollama_que_cai_no_meio_da_resposta(self) -> None:
        def tratar(req: httpx.Request) -> httpx.Response:
            if req.url.path == "/api/tags":
                return httpx.Response(200, json={"models": [{"name": "qwen3:4b", "size": 1}]})
            raise httpx.ReadError("conexão perdida", request=req)

        cliente = OllamaClient("http://127.0.0.1:11434", transport=httpx.MockTransport(tratar))
        with pytest.raises(MotorIndisponivel, match="Ollama"):
            MotorDeTextoOllama(cliente).estruturar(
                ContextoDeTeste(), sistema="s", dados="d", instrucao="i", esquema=ESQUEMA
            )


class TestFabrica:
    def test_segundos_por_imagem_de_512(self) -> None:
        assert segundos_por_imagem_512({"imagem_seg": 100.0, "imagem_lado": 512}) == pytest.approx(100.0)
        assert segundos_por_imagem_512({"imagem_seg": 200.0, "imagem_lado": 1024}) == pytest.approx(50.0)
        assert segundos_por_imagem_512({"imagem_seg": 90.0}) == pytest.approx(90.0)
        assert segundos_por_imagem_512({}) is None and segundos_por_imagem_512({"imagem_seg": True}) is None
        assert segundos_por_imagem_512({"imagem_seg": -3}) is None

    def test_monta_os_quatro_motores_reais(self, settings: Settings) -> None:
        cliente, _ = ollama_falso()
        motores = criar_motores(settings, cliente, lambda: {"imagem_seg": 50.0, "imagem_lado": 512}, lambda: True)
        assert isinstance(motores.imagem, MotorDeImagemSdCpp) and isinstance(motores.texto, MotorDeTextoOllama)
        assert motores.imagem.estimativa(512, 512) == pytest.approx(50.0)
        assert motores.indisponiveis() == {}

    def test_indisponiveis_lista_o_que_falta_com_o_motivo(self, settings: Settings) -> None:
        cliente, _ = ollama_falso(online=False)
        (settings.models_dir / "voz" / "kokoro-v1.0.onnx").unlink()
        motores = criar_motores(settings, cliente, lambda: {}, lambda: True)
        assert set(motores.indisponiveis()) == {"voice", "text"}


class TestContrato:
    """Os motores de verdade e os falsos cumprem a mesma interface (nomes, tipos de parâmetro e padrões)."""

    @staticmethod
    def _assinatura(funcao: Callable[..., Any]) -> list[tuple[str, Any, bool]]:
        params = [p for n, p in inspect.signature(funcao).parameters.items() if n != "self"]
        return [(p.name, p.kind, p.default is not inspect.Parameter.empty) for p in params]

    @pytest.mark.parametrize(
        ("protocolo", "implementacoes"),
        [
            (interfaces.MotorDeImagem, [MotorDeImagemSdCpp, ImagemFalsa]),
            (interfaces.MotorDeRecorte, [MotorDeRecorteBiRefNet, RecorteFalso]),
            (interfaces.MotorDeVoz, [MotorDeVozKokoro, VozFalsa]),
            (interfaces.MotorDeTexto, [MotorDeTextoOllama, TextoFalso]),
        ],
    )
    def test_mesmas_assinaturas(self, protocolo: type, implementacoes: list[type]) -> None:
        metodos = [n for n, v in vars(protocolo).items() if callable(v) and not n.startswith("_")]
        assert metodos
        for classe in implementacoes:
            for nome in metodos:
                esperado = self._assinatura(getattr(protocolo, nome))
                assert self._assinatura(getattr(classe, nome)) == esperado, f"{classe.__name__}.{nome}"

    def test_o_contexto_da_fila_cumpre_o_contrato_do_contexto(self) -> None:
        from app.jobs.worker import JobContext
        from app.motores.tipos import Contexto

        for nome in ("progresso", "log", "ponto_de_controle", "executar_processo"):
            assert self._assinatura(getattr(JobContext, nome)) == self._assinatura(getattr(Contexto, nome)), nome
            assert self._assinatura(getattr(ContextoDeTeste, nome)) == self._assinatura(getattr(Contexto, nome)), nome

    def test_os_falsos_geram_arquivos_de_verdade(self, tmp_path: Path) -> None:
        motores = motores_falsos()
        ctx = ContextoDeTeste()
        r = motores.imagem.gerar(ctx, PedidoImagem("p", 320, 192, 5), tmp_path / "i.png")
        with Image.open(r.caminho) as imagem:
            assert imagem.size == (320, 192)
        motores.recorte.recortar(ctx, r.caminho, tmp_path / "r.png")
        with Image.open(tmp_path / "r.png") as recorte:
            assert "A" in recorte.getbands()
        falas = motores.voz.falar(ctx, [ItemDeVoz("Olá", "pf_dora", 1.0, "pt-br", tmp_path / "v.wav")])
        assert falas[0].duracao_s == pytest.approx(0.4) and falas[0].saida.is_file()
        assert motores.texto.indisponivel() is None and motores.indisponiveis() == {}
