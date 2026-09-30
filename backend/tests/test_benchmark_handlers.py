"""Benchmark de calibração, handlers dos jobs e execução do diagnóstico."""

from __future__ import annotations

import sys
import types
from typing import Any

import httpx
import pytest

from app.benchmark.runner import BenchmarkStore, ResultadoBench, medir_llm
from app.container import Servicos
from app.hardware.runner import DiagnosticoIndisponivel, comando_diagnostico
from app.jobs import handlers
from app.jobs.handlers import REGISTRO
from app.jobs.models import JobStatus
from app.jobs.worker import JobWorker
from app.services.ollama import OllamaClient, OllamaIndisponivel

from .conftest import esperar, ollama_falso


class TestMedirLlm:
    def test_escolhe_o_menor_modelo_e_calcula_velocidades(self) -> None:
        cliente, chamadas = ollama_falso(modelos=[("grande:9b", 6_000_000_000), ("pequeno:1b", 1_000_000_000)])
        r = medir_llm(cliente)
        assert r.status == "ok" and r.model == "pequeno:1b"
        assert r.metrics["gen_tok_s"] == 10.0 and r.metrics["prefill_tok_s"] == 40.0
        assert r.metrics["processor"] == "cpu" and r.metrics["prompt_tokens"] == 1046
        assert chamadas.count("POST /api/generate") == 4  # aquece, gera, prefill e descarrega
        assert chamadas[-1] == "POST /api/generate"

    def test_detecta_uso_de_gpu(self) -> None:
        assert medir_llm(ollama_falso(gpu=True)[0]).metrics["processor"] == "gpu"

    def test_respeita_o_modelo_preferido(self) -> None:
        cliente, _ = ollama_falso(modelos=[("a:1b", 1_000_000_000), ("b:9b", 9_000_000_000)])
        assert medir_llm(cliente, "b:9b").model == "b:9b"

    def test_ignora_modelos_de_embedding(self) -> None:
        r = medir_llm(ollama_falso(modelos=[("nomic-embed-text", 100), ("qwen3:4b", 2_000_000_000)])[0])
        assert r.model == "qwen3:4b"

    def test_ollama_fora_do_ar_e_sem_modelos(self) -> None:
        fora = medir_llm(ollama_falso(online=False)[0])
        assert fora.status == "skipped" and "não respondeu" in (fora.detail or "")
        vazio = medir_llm(ollama_falso(modelos=[])[0])
        assert vazio.status == "skipped" and "Nenhum modelo" in (vazio.detail or "")

    def test_erro_no_meio_da_medicao(self) -> None:
        def tratar(req: httpx.Request) -> httpx.Response:
            if req.url.path == "/api/tags":
                return httpx.Response(200, json={"models": [{"name": "m:1b", "size": 1}]})
            return httpx.Response(500)

        r = medir_llm(OllamaClient("http://127.0.0.1:11434", transport=httpx.MockTransport(tratar)))
        assert r.status == "error" and r.model == "m:1b"


class TestBenchmarkStore:
    def test_guarda_a_medicao_mais_recente_de_cada_tarefa(self, servicos: Servicos) -> None:
        loja = BenchmarkStore(servicos.db)
        loja.salvar(ResultadoBench("llm_ollama", "ok", "a", 1.0, {"gen_tok_s": 5.0, "prefill_tok_s": 20.0}), "fp1")
        loja.salvar(
            ResultadoBench(
                "llm_ollama", "ok", "b", 1.0, {"gen_tok_s": 11.0, "prefill_tok_s": 30.0, "processor": "cpu"}
            ),
            "fp2",
        )
        loja.salvar(ResultadoBench("image", "skipped", detail="sem modelo"), "fp2")
        ultimos = {r["task"]: r for r in loja.ultimos()}
        assert ultimos["llm_ollama"]["model"] == "b" and ultimos["image"]["status"] == "skipped"
        medicoes = loja.medicoes()
        assert (
            medicoes["llm_gen_tok_s"] == 11.0 and medicoes["llm_modelo"] == "b" and medicoes["llm_processador"] == "cpu"
        )

    def test_medicao_com_erro_nao_vira_numero(self, servicos: Servicos) -> None:
        loja = BenchmarkStore(servicos.db)
        loja.salvar(ResultadoBench("llm_ollama", "skipped", detail="fora do ar"))
        assert loja.medicoes() == {}


class TestRunnerDoDiagnostico:
    class _Cfg:
        hardware_json = "C:/x/hardware.json"

        class scripts_dir:
            @staticmethod
            def __truediv__(n: str) -> str:
                return n

    def test_comando_no_windows(self, servicos: Servicos, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.hardware.runner.shutil.which", lambda n: "C:/ps/powershell.exe" if n == "powershell" else None
        )
        cmd = comando_diagnostico(servicos.settings, leve=True, plataforma="win32")
        assert cmd[0] == "C:/ps/powershell.exe" and "-Leve" in cmd and "-SemPerfil" in cmd and "-Silencioso" in cmd
        assert cmd[cmd.index("-Saida") + 1] == str(servicos.settings.hardware_json)
        assert cmd[cmd.index("-File") + 1].endswith("diagnostico.ps1")
        assert "-Leve" not in comando_diagnostico(servicos.settings, leve=False, plataforma="win32")

    def test_comando_no_linux_e_macos(self, servicos: Servicos, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.hardware.runner.shutil.which", lambda n: "/usr/bin/bash")
        for so in ("linux", "darwin"):
            cmd = comando_diagnostico(servicos.settings, leve=True, plataforma=so)
            assert cmd[0] == "/usr/bin/bash" and cmd[1].endswith("diagnostico.sh") and "--leve" in cmd
            assert "--sem-perfil" in cmd and all(isinstance(p, str) for p in cmd)  # lista de argumentos, sem shell

    def test_sem_interpretador(self, servicos: Servicos, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.hardware.runner.shutil.which", lambda n: None)
        for so in ("win32", "linux"):
            with pytest.raises(DiagnosticoIndisponivel):
                comando_diagnostico(servicos.settings, leve=False, plataforma=so)


@pytest.fixture
def com_worker(servicos: Servicos) -> Any:
    w = JobWorker(servicos.store, servicos.bus, servicos, REGISTRO, intervalo=0.02)
    servicos.worker = w
    w.iniciar()
    yield servicos
    w.parar(timeout=5)


def _esperar_fim(sv: Servicos, job_id: str) -> Any:
    assert esperar(
        lambda: (sv.store.obter(job_id) or sys.exit()).status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELED),
        timeout=30,
    )
    job = sv.store.obter(job_id)
    assert job is not None
    return job


class TestHandlers:
    def test_demo_sleep_conclui(self, com_worker: Servicos) -> None:
        job = com_worker.store.criar("demo.sleep", "d", {"seconds": 0.2, "steps": 4})
        final = _esperar_fim(com_worker, job.id)
        assert final.status == JobStatus.DONE and final.result == {"seconds": 0.2, "steps": 4}

    def test_demo_sleep_falha_quando_pedido(self, com_worker: Servicos) -> None:
        job = com_worker.store.criar("demo.sleep", "d", {"seconds": 0.2, "steps": 4, "fail_at": 2})
        final = _esperar_fim(com_worker, job.id)
        assert final.status == JobStatus.FAILED and "fail_at" in (final.error or "")

    def test_demo_sleep_limita_e_ignora_parametros_invalidos(
        self, com_worker: Servicos, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # sem esperar os 10 s do padrão (e sem a corrida entre criar e cancelar, que dependia da pressa do worker)
        monkeypatch.setattr(handlers, "time", types.SimpleNamespace(sleep=lambda _s: None))
        job = com_worker.store.criar("demo.sleep", "d", {"seconds": "abc", "steps": -5})
        final = _esperar_fim(com_worker, job.id)
        assert final.status == JobStatus.DONE and final.result == {"seconds": 10.0, "steps": 1}
        assert handlers._numero("x", 3.0, 1, 5) == 3.0
        assert handlers._numero(999, 3.0, 1, 5) == 5 and handlers._numero(-1, 3.0, 1, 5) == 1

    def test_diagnostico_conclui_e_atualiza_a_matriz(
        self, com_worker: Servicos, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            handlers, "comando_diagnostico", lambda *_a, **_k: [sys.executable, "-c", "print('coletado')"]
        )
        job = com_worker.store.criar("system.diagnostico", "d", {"leve": True})
        final = _esperar_fim(com_worker, job.id)
        assert final.status == JobStatus.DONE and final.result is not None
        assert final.result["profile"] == "C"
        assert com_worker.settings.capabilities_json.exists()

    def test_diagnostico_com_codigo_de_erro(self, com_worker: Servicos, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            handlers,
            "comando_diagnostico",
            lambda *_a, **_k: [sys.executable, "-c", "print('quebrou feio'); raise SystemExit(3)"],
        )
        final = _esperar_fim(com_worker, com_worker.store.criar("system.diagnostico", "d", {}).id)
        assert (
            final.status == JobStatus.FAILED
            and "código 3" in (final.error or "")
            and "quebrou feio" in (final.error or "")
        )

    def test_diagnostico_que_gera_json_invalido(self, com_worker: Servicos, monkeypatch: pytest.MonkeyPatch) -> None:
        com_worker.settings.hardware_json.write_text('{"schema_version": 99}', encoding="utf-8")
        monkeypatch.setattr(handlers, "comando_diagnostico", lambda *_a, **_k: [sys.executable, "-c", "pass"])
        final = _esperar_fim(com_worker, com_worker.store.criar("system.diagnostico", "d", {}).id)
        assert final.status == JobStatus.FAILED and "inválido" in (final.error or "")

    def test_diagnostico_avisa_quando_esta_na_bateria(
        self, com_worker: Servicos, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import json

        dados = json.loads(com_worker.settings.hardware_json.read_text(encoding="utf-8"))
        dados["system"]["battery"]["on_ac"] = False
        com_worker.settings.hardware_json.write_text(json.dumps(dados), encoding="utf-8")
        monkeypatch.setattr(handlers, "comando_diagnostico", lambda *_a, **_k: [sys.executable, "-c", "pass"])
        job = com_worker.store.criar("system.diagnostico", "d", {})
        _esperar_fim(com_worker, job.id)
        assert any(e.level == "WARNING" and "bateria" in e.message for e in com_worker.store.logs(job.id))

    def test_calibracao_grava_medicoes_e_capacidades(self, com_worker: Servicos) -> None:
        final = _esperar_fim(com_worker, com_worker.store.criar("benchmark.calibracao", "b").id)
        assert final.status == JobStatus.DONE and final.result is not None
        assert final.result["gen_tok_s"] == 10.0 and final.result["model"] == "qwen3:4b"
        assert (final.result["voice"], final.result["cutout"], final.result["image"]) == ("ok", "ok", "ok")
        assert com_worker.medidores.chamadas == ["voz", "recorte", "imagem"]  # type: ignore[attr-defined]
        gravado = com_worker.settings.capabilities_json.read_text(encoding="utf-8")
        assert "com o qwen3:4b" in gravado and "≈ 1,7 min por imagem de 512 px" in gravado

    def test_calibracao_com_ollama_fora_do_ar_nao_falha(self, com_worker: Servicos) -> None:
        com_worker.ollama = ollama_falso(online=False)[0]
        final = _esperar_fim(com_worker, com_worker.store.criar("benchmark.calibracao", "b").id)
        assert final.status == JobStatus.DONE and final.result is not None and final.result["llm"] == "skipped"

    def test_registro_tem_os_tres_tipos_da_fase_1(self) -> None:
        assert {"demo.sleep", "system.diagnostico", "benchmark.calibracao"} <= set(REGISTRO)


class TestOllamaClient:
    def test_erros_viram_ollama_indisponivel(self) -> None:
        cliente, _ = ollama_falso(online=False)
        with pytest.raises(OllamaIndisponivel):
            cliente.versao()
        lixo = OllamaClient(
            "http://127.0.0.1:11434", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[1, 2]))
        )
        with pytest.raises(OllamaIndisponivel, match="inesperada"):
            lixo.versao()
        html = OllamaClient(
            "http://127.0.0.1:11434", transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>"))
        )
        with pytest.raises(OllamaIndisponivel):
            html.modelos()

    def test_requisicao_de_geracao_e_deterministica_e_sem_thinking(self) -> None:
        capturado: dict[str, Any] = {}

        def tratar(req: httpx.Request) -> httpx.Response:
            import json

            capturado.update(json.loads(req.content))
            return httpx.Response(200, json={})

        OllamaClient("http://127.0.0.1:11434", transport=httpx.MockTransport(tratar)).gerar("m", "oi", num_predict=8)
        assert capturado["think"] is False and capturado["stream"] is False
        assert capturado["options"] == {"temperature": 0, "num_predict": 8, "seed": 1}
