"""Saúde dos serviços (página Status) e matriz de capacidades por perfil."""

from __future__ import annotations

import json
import shutil
from collections import namedtuple
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.container import Servicos, criar_servicos
from app.hardware.capacidades import calcular, eta_roteiro
from app.hardware.estado import HardwareState
from app.hardware.perfil import classificar
from app.services import status as status_mod
from app.services.status import EstadoServico, coletar_status

from .builders import FIXTURES, aceleracao, carregar_thinkpad, ferramentas, gpu, hw
from .conftest import ollama_falso

Uso = namedtuple("Uso", "total used free")


def _por_id(sv: Servicos) -> dict[str, Any]:
    return {s.id: s for s in coletar_status(sv).services}


class TestStatus:
    def test_ollama_sem_modelos_e_aviso(self, settings: Settings) -> None:
        sv = criar_servicos(settings, ollama=ollama_falso(modelos=[])[0])
        s = _por_id(sv)["ollama"]
        assert s.state == EstadoServico.WARNING and "ollama pull" in s.how_to_fix[0]

    def test_ollama_lista_ate_quatro_nomes(self, settings: Settings) -> None:
        modelos = [(f"m{i}:1b", 1_000_000_000) for i in range(6)]
        sv = criar_servicos(settings, ollama=ollama_falso(modelos=modelos)[0])
        s = _por_id(sv)["ollama"]
        assert s.state == EstadoServico.OK and s.detail is not None and s.detail.endswith("...")

    @pytest.mark.parametrize(
        "livre_gb,esperado",
        [(500, EstadoServico.OK), (99, EstadoServico.WARNING), (61, EstadoServico.WARNING), (19, EstadoServico.ERROR)],
    )
    def test_disco_por_faixa(
        self, servicos: Servicos, monkeypatch: pytest.MonkeyPatch, livre_gb: int, esperado: EstadoServico
    ) -> None:
        gib = 1024**3
        monkeypatch.setattr(
            status_mod.shutil, "disk_usage", lambda _p: Uso(1000 * gib, (1000 - livre_gb) * gib, livre_gb * gib)
        )
        s = _por_id(servicos)["disk"]
        assert s.state == esperado
        if esperado != EstadoServico.OK:
            assert any("FABULIM_DATA_DIR" in passo for passo in s.how_to_fix)

    def test_diagnostico_ausente_e_mudou(self, servicos: Servicos) -> None:
        servicos.settings.hardware_json.unlink()
        assert _por_id(servicos)["diagnostic"].state == EstadoServico.WARNING
        dados = carregar_thinkpad()
        dados["changed_since_last_run"] = True
        servicos.settings.hardware_json.write_text(json.dumps(dados), encoding="utf-8")
        s = _por_id(servicos)["diagnostic"]
        assert s.state == EstadoServico.WARNING and s.summary == "A máquina mudou"
        dados["changed_since_last_run"] = False
        servicos.settings.hardware_json.write_text(json.dumps(dados), encoding="utf-8")
        assert _por_id(servicos)["diagnostic"].state == EstadoServico.OK

    def test_claude_instalado_sem_login_e_ausente(self, servicos: Servicos) -> None:
        dados = carregar_thinkpad()
        dados["tools"]["claude_code"]["logged_in"] = False
        servicos.settings.hardware_json.write_text(json.dumps(dados), encoding="utf-8")
        s = _por_id(servicos)["claude"]
        assert s.state == EstadoServico.INACTIVE and "auth login" in s.how_to_fix[0]
        dados["tools"]["claude_code"] = {"installed": False}
        servicos.settings.hardware_json.write_text(json.dumps(dados), encoding="utf-8")
        assert _por_id(servicos)["claude"].summary == "Não instalado"

    def test_claude_logado_na_maquina_nao_conta_como_conectado_ao_app(self, servicos: Servicos) -> None:
        """Regressão: o Claude Code logado aparecia como "Conectado", mas o app ainda não se conecta (briefing 15.2)."""
        s = _por_id(servicos)["claude"]  # o ThinkPad de referência tem o Claude Code logado (plano pro)
        assert s.state == EstadoServico.INACTIVE
        assert "Conectado" not in s.summary and "não conectado" in s.summary
        assert (
            s.detail is not None and "plano pro" in s.detail and "nesta versão" in s.detail and "Fase" not in s.detail
        )

    def test_ffmpeg_instalado_mostra_codificadores(self, servicos: Servicos) -> None:
        dados = carregar_thinkpad()
        dados["tools"]["ffmpeg"] = {
            "installed": True,
            "version": "7.1",
            "path": "x",
            "encoders": ["libx264", "h264_qsv"],
        }
        servicos.settings.hardware_json.write_text(json.dumps(dados), encoding="utf-8")
        s = _por_id(servicos)["ffmpeg"]
        assert s.state == EstadoServico.OK and s.detail is not None and "h264_qsv" in s.detail

    def test_geral_pega_o_pior_estado_e_ignora_os_inativos(self, servicos: Servicos) -> None:
        assert coletar_status(servicos).overall == EstadoServico.ERROR  # sem worker
        servicos.worker.iniciar()  # type: ignore[union-attr]
        try:
            assert coletar_status(servicos).overall == EstadoServico.WARNING  # ffmpeg ausente
            dados = carregar_thinkpad()
            dados["tools"]["ffmpeg"] = {"installed": True, "version": "7", "path": "x", "encoders": []}
            servicos.settings.hardware_json.write_text(json.dumps(dados), encoding="utf-8")
            assert coletar_status(servicos).overall in (
                EstadoServico.OK,
                EstadoServico.WARNING,
            )  # WARNING só se o disco apertar
        finally:
            servicos.worker.parar()  # type: ignore[union-attr]

    def test_banco_com_problema_vira_erro(self, servicos: Servicos, monkeypatch: pytest.MonkeyPatch) -> None:
        def quebrar(*_a: Any, **_k: Any) -> Any:
            raise RuntimeError("disk I/O error")

        monkeypatch.setattr(servicos.db, "transaction", quebrar)
        s = _por_id(servicos)["database"]
        assert s.state == EstadoServico.ERROR and "disk I/O error" in (s.detail or "")


class TestCapacidades:
    def _caps(self, dados: dict[str, Any], **medicoes: Any) -> dict[str, Any]:
        return {c.id: c for c in calcular(dados, classificar(dados), medicoes)}

    def test_funcionalidades_com_ids_unicos_e_campos(self) -> None:
        caps = calcular(carregar_thinkpad(), classificar(carregar_thinkpad()))
        assert len(caps) == 21 and len({c.id for c in caps}) == 21
        for c in caps:
            d = c.para_dict()
            assert set(d) == {"id", "name", "section", "state", "reason", "eta", "eta_measured"}
            assert d["state"] in {"available", "slow", "unavailable"} and d["reason"]
            assert "Fase" not in d["reason"]  # a interface é de produto: nada de "chega na Fase N"

    def test_perfil_c_no_thinkpad(self) -> None:
        caps = self._caps(carregar_thinkpad())
        estados = {i: c.estado for i, c in caps.items()}
        assert estados["imagem"] == "slow" and estados["llm_local"] == "slow"
        assert (
            estados["animacao_ia"] == estados["musica_cantada"] == "unavailable"
        )  # sem vídeo por IA; sem música cantada
        assert (
            estados["consistencia_camadas"] == estados["recorte"] == estados["voz"] == estados["musica"] == "available"
        )
        assert (
            estados["animacao_cena"] == estados["clipe_rapido"] == "unavailable"
        )  # falta o ffmpeg na máquina de referência
        assert estados["efeitos_legendas"] == "available"  # gerados por código, sem ffmpeg
        assert "notebook" in caps["animacao_ia"].motivo and "desktop" in caps["animacao_ia"].motivo
        assert caps["claude"].estado == "available" and "pro" in caps["claude"].motivo

    def test_com_o_ffmpeg_o_clipe_rapido_e_a_animacao_de_cena_funcionam_no_notebook(self) -> None:
        dados = carregar_thinkpad()
        dados["tools"]["ffmpeg"] = {"installed": True, "version": "7", "path": "x", "encoders": []}
        caps = self._caps(dados)
        assert caps["animacao_cena"].estado == "available" and caps["clipe_rapido"].estado == "slow"
        assert "cenário" in caps["clipe_rapido"].motivo.lower() and "por código" in caps["clipe_rapido"].motivo
        assert caps["animacao_ia"].estado == "unavailable"  # o vídeo por IA continua sendo do desktop
        medido = self._caps(dados, imagem_seg=100.0)["clipe_rapido"]
        assert medido.eta is not None and "≈ 3,2 min" in medido.eta  # 100 s x 1,3 + 60 s de animação

    def test_desktop_sem_bateria_fala_computador(self) -> None:
        dados = hw(gpus=[gpu("intel", "Intel(R) UHD Graphics", dedicated_mb=128)], tools=ferramentas())
        motivo = self._caps(dados)["animacao_ia"].motivo
        assert "computador" in motivo and "outra máquina" in motivo

    def test_ffmpeg_ausente_bloqueia_o_que_depende_dele(self) -> None:
        caps = self._caps(hw(tools=ferramentas(ffmpeg={"installed": False})))
        for i in ("montagem", "animacao_cena", "continuar", "clipe_rapido"):
            assert caps[i].estado == "unavailable" and "ffmpeg" in caps[i].motivo, i
        for i in ("efeitos_legendas", "musica"):  # gerados por código: não dependem do ffmpeg
            assert caps[i].estado == "available", i

    def test_o_node_nao_e_necessario_para_animar(self) -> None:
        caps = self._caps(hw(tools=ferramentas(node={"installed": False})))
        assert caps["animacao_cena"].estado == "available" and "Node" not in caps["animacao_cena"].motivo

    def test_perfil_a_tudo_disponivel_inclusive_animacao_ia(self) -> None:
        dados = hw(gpus=[gpu("nvidia", "NVIDIA GeForce RTX 4090", dedicated_mb=24_564)], accel=aceleracao(cuda=True))
        caps = self._caps(dados)
        assert caps["imagem"].estado == caps["animacao_ia"].estado == caps["llm_local"].estado == "available"

    def test_perfil_b_animacao_ia_so_clipes_curtos(self) -> None:
        dados = hw(gpus=[gpu("amd", "AMD Radeon RX 6750 XT", dedicated_mb=12_288)], accel=aceleracao(vulkan=True))
        caps = self._caps(dados)
        assert caps["animacao_ia"].estado == "slow" and "curtos" in caps["animacao_ia"].motivo
        assert caps["imagem"].estado == "available"

    def test_perfil_d_so_planejamento(self) -> None:
        caps = self._caps(hw(ram_mb=8_000))
        assert caps["prompts"].estado == "available" and caps["fila_noturna"].estado == "available"
        for i in ("imagem", "voz", "recorte", "animacao_cena", "animacao_ia", "clipe_rapido", "visao_local"):
            assert caps[i].estado == "unavailable", i
        assert caps["musica"].estado == "available"  # gerada por código: leve em qualquer perfil
        assert caps["llm_local"].estado == "slow"

    def test_eta_do_llm_vem_da_medicao(self) -> None:
        eta, medido = eta_roteiro({"llm_gen_tok_s": 10.0, "llm_prefill_tok_s": 40.0, "llm_modelo": "qwen3:4b"})
        assert medido and eta is not None and "≈ 2,9 min" in eta and "qwen3:4b" in eta  # 150 s + 25 s
        assert eta_roteiro({}) == (None, False)
        assert eta_roteiro({"llm_gen_tok_s": 0}) == (None, False)
        caps = self._caps(carregar_thinkpad(), llm_gen_tok_s=10.0, llm_prefill_tok_s=40.0, llm_modelo="qwen3:4b")
        assert caps["llm_local"].eta_medido is True and caps["llm_local"].estado == "slow"
        assert self._caps(carregar_thinkpad())["llm_local"].eta_medido is False  # sem medição: estimativa

    def test_segundos_viram_minutos_so_acima_de_90(self) -> None:
        eta, _ = eta_roteiro({"llm_gen_tok_s": 100.0, "llm_prefill_tok_s": 1000.0})  # 15 s + 1 s
        assert eta is not None and "≈ 16 s" in eta

    def test_claude_logado_e_reforco_possivel_mas_nao_conectado(self) -> None:
        motivo = self._caps(carregar_thinkpad())["claude"].motivo
        assert "Conectado" not in motivo and "quando você conectar" in motivo and "nesta versão" in motivo

    def test_claude_sem_login_ou_ausente(self) -> None:
        sem_login = ferramentas()
        sem_login["claude_code"] = {"installed": True, "logged_in": False}
        assert "sem login" in self._caps(hw(tools=sem_login))["claude"].motivo
        assert (
            "não está instalado" in self._caps(hw(tools=ferramentas(claude_code={"installed": False})))["claude"].motivo
        )


class TestEstadoDoHardware:
    def test_salvar_capacidades_grava_json_valido(self, servicos: Servicos) -> None:
        assert servicos.hardware.salvar_capacidades() is True
        dados = json.loads(servicos.settings.capabilities_json.read_text(encoding="utf-8"))
        assert dados["profile"] == "C" and len(dados["capabilities"]) == 21

    def test_sem_hardware_nao_grava(self, servicos: Servicos) -> None:
        servicos.settings.hardware_json.unlink()
        assert servicos.hardware.salvar_capacidades() is False
        assert not servicos.settings.capabilities_json.exists()

    def test_aceita_json_com_bom_e_rejeita_lixo(self, settings: Settings, tmp_path: Path) -> None:
        estado = HardwareState(settings)
        settings.hardware_json.write_bytes(b"\xef\xbb\xbf" + (FIXTURES / "thinkpad_t14_gen2i.json").read_bytes())
        assert estado.carregar() is not None
        settings.hardware_json.write_text("[1, 2]", encoding="utf-8")
        assert estado.carregar() is None
        settings.hardware_json.write_text("não é json", encoding="utf-8")
        assert estado.carregar() is None

    def test_notebook_na_bateria(self, settings: Settings) -> None:
        estado = HardwareState(settings)
        assert estado.notebook_na_bateria() is False  # o ThinkPad da fixture está na tomada
        dados = carregar_thinkpad()
        dados["system"]["battery"]["on_ac"] = False
        settings.hardware_json.write_text(json.dumps(dados), encoding="utf-8")
        assert estado.notebook_na_bateria() is True

    def test_medicoes_entram_no_snapshot(self, settings: Settings) -> None:
        shutil.copy(FIXTURES / "thinkpad_t14_gen2i.json", settings.hardware_json)
        estado = HardwareState(settings, lambda: {"llm_gen_tok_s": 12.5, "llm_modelo": "x"})
        snap = estado.snapshot()
        assert snap["measurements"]["llm_gen_tok_s"] == 12.5
        assert {c["id"]: c for c in snap["capabilities"]}["llm_local"]["eta_measured"] is True
