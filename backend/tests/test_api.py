"""API HTTP: saúde, status, máquina, jobs, logs, benchmark e frontend estático."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.container import Servicos, criar_servicos
from app.main import criar_app

from .conftest import esperar, ollama_falso

ID_INEXISTENTE = "0" * 32


def _cliente(sv: Servicos, *, worker: bool = False) -> TestClient:
    return TestClient(criar_app(sv.settings, servicos=sv, iniciar_worker=worker), base_url="http://127.0.0.1:8765")


class TestSistema:
    def test_saude(self, client: TestClient) -> None:
        assert client.get("/api/health").json() == {"status": "ok"}

    def test_meta(self, client: TestClient, servicos: Servicos) -> None:
        dados = client.get("/api/meta").json()
        assert dados["name"] == "Fabulim Studio" and dados["host"] == "127.0.0.1"
        assert dados["port"] == 8765 and dados["data_dir"] == str(servicos.settings.data_dir)
        assert "phase" not in dados  # o número de fase de desenvolvimento não aparece para o usuário

    def test_status_lista_os_servicos_com_estado_e_como_corrigir(self, client: TestClient) -> None:
        dados = client.get("/api/status").json()
        por_id = {s["id"]: s for s in dados["services"]}
        assert {"backend", "database", "queue", "diagnostic", "ollama", "claude", "ffmpeg", "disk"} <= set(por_id)
        assert {"image_engine", "tts_engine", "music_engine", "animation_engine"} <= set(por_id)
        assert por_id["backend"]["state"] == "ok" and por_id["database"]["state"] == "ok"
        assert por_id["ollama"]["state"] == "ok" and "1 modelo" in por_id["ollama"]["summary"]
        assert por_id["ffmpeg"]["state"] == "warning" and por_id["ffmpeg"]["how_to_fix"]
        # a fixture tem o Claude Code logado, mas o app ainda não se conecta ao Claude: não pode aparecer como conectado
        assert por_id["claude"]["state"] == "inactive" and "não conectado" in por_id["claude"]["summary"]
        assert por_id["queue"]["state"] == "error"  # sem worker neste cliente
        assert dados["overall"] == "error" and dados["generated_at"]
        assert all(s["state"] in {"ok", "warning", "error", "inactive"} for s in dados["services"])

    def test_status_com_ollama_fora_do_ar(self, servicos: Servicos, settings: Settings) -> None:
        sv = criar_servicos(settings, ollama=ollama_falso(online=False)[0])
        with _cliente(sv, worker=True) as c:
            ollama = {s["id"]: s for s in c.get("/api/status").json()["services"]}["ollama"]
        assert ollama["state"] == "error" and ollama["summary"] == "Não respondeu"
        assert any("ollama serve" in passo for passo in ollama["how_to_fix"])

    def test_maquina_thinkpad(self, client: TestClient) -> None:
        dados = client.get("/api/machine").json()
        assert dados["exists"] and dados["valid"]
        assert dados["profile"]["letter"] == "C" and dados["profile"]["name"] == "Notebook ou GPU integrada"
        assert dados["hardware"]["gpus"][0]["kind"] == "integrated"
        caps = {c["id"]: c for c in dados["capabilities"]}
        assert caps["animacao_ia"]["state"] == "unavailable" and "GPU dedicada" in caps["animacao_ia"]["reason"]
        assert caps["animacao_cena"]["state"] == "unavailable"  # falta o ffmpeg na máquina de referência
        assert caps["fila_noturna"]["state"] == "available"
        assert any(p["item"] == "ffmpeg" for p in dados["pending"])
        assert dados["changed"] is False and dados["mode"] in {"light", "full"}

    def test_maquina_sem_diagnostico(self, client: TestClient, servicos: Servicos) -> None:
        servicos.settings.hardware_json.unlink()
        dados = client.get("/api/machine").json()
        assert dados == {"exists": False, "valid": False, "errors": [], "capabilities": [], "measurements": {}}

    def test_maquina_com_json_invalido(self, client: TestClient, servicos: Servicos) -> None:
        servicos.settings.hardware_json.write_text('{"schema_version": 99}', encoding="utf-8")
        dados = client.get("/api/machine").json()
        assert dados["exists"] and not dados["valid"] and dados["errors"]

    def test_capacidades_e_arquivo_gerado(self, client: TestClient, servicos: Servicos) -> None:
        caps = client.get("/api/capabilities").json()
        assert len(caps) == 21 and all({"id", "name", "state", "reason"} <= set(c) and "phase" not in c for c in caps)
        assert servicos.hardware.salvar_capacidades()
        assert '"profile": "C"' in servicos.settings.capabilities_json.read_text(encoding="utf-8")

    def test_refazer_diagnostico_cria_job_uma_vez_so(self, client: TestClient) -> None:
        primeiro = client.post("/api/machine/diagnostic")
        assert primeiro.status_code == 202 and primeiro.json()["kind"] == "system.diagnostico"
        assert primeiro.json()["params"] == {"leve": False}
        segundo = client.post("/api/machine/diagnostic?light=true")
        assert segundo.json()["id"] == primeiro.json()["id"]  # já existe um na fila

    def test_benchmark_nao_duplica_enquanto_um_esta_ativo(self, client: TestClient) -> None:
        primeiro = client.post("/api/benchmark/run").json()
        assert primeiro["kind"] == "benchmark.calibracao"
        assert client.post("/api/benchmark/run").json()["id"] == primeiro["id"]

    def test_openapi_existe_e_a_pagina_de_docs_com_cdn_nao(self, client: TestClient) -> None:
        assert client.get("/api/openapi.json").status_code == 200
        assert client.get("/docs").status_code == 404


class TestJobs:
    def test_criar_listar_e_obter(self, client: TestClient) -> None:
        r = client.post("/api/jobs", json={"kind": "demo.sleep", "params": {"seconds": 1}, "priority": 2})
        assert r.status_code == 201
        job = r.json()
        assert job["status"] == "queued" and job["title"] == "Job de demonstração" and job["priority"] == 2
        assert [j["id"] for j in client.get("/api/jobs").json()] == [job["id"]]
        assert client.get(f"/api/jobs/{job['id']}").json()["id"] == job["id"]
        assert client.get("/api/jobs?status=done").json() == []

    def test_titulo_personalizado(self, client: TestClient) -> None:
        r = client.post("/api/jobs", json={"kind": "demo.sleep", "title": "Meu teste"})
        assert r.json()["title"] == "Meu teste"

    def test_validacoes(self, client: TestClient) -> None:
        assert client.post("/api/jobs", json={"kind": "nao.existe"}).status_code == 422
        assert client.post("/api/jobs", json={"kind": ""}).status_code == 422
        assert client.post("/api/jobs", json={"kind": "demo.sleep", "priority": 99}).status_code == 422
        assert client.post("/api/jobs", json={}).status_code == 422
        assert client.get(f"/api/jobs/{ID_INEXISTENTE}").status_code == 404
        assert client.get("/api/jobs/nao-e-um-id").status_code == 422
        assert client.get("/api/jobs/../../etc/passwd").status_code in (404, 422)
        assert client.post("/api/jobs/reorder", json={"ids": []}).status_code == 422

    def test_pausar_retomar_e_cancelar_na_fila(self, client: TestClient) -> None:
        jid = client.post("/api/jobs", json={"kind": "demo.sleep"}).json()["id"]
        assert client.post(f"/api/jobs/{jid}/pause").json()["status"] == "paused"
        assert client.post(f"/api/jobs/{jid}/resume").json()["status"] == "queued"
        assert client.post(f"/api/jobs/{jid}/cancel").json()["status"] == "canceled"
        assert client.post(f"/api/jobs/{ID_INEXISTENTE}/cancel").status_code == 404

    def test_reordenar(self, client: TestClient) -> None:
        ids = [client.post("/api/jobs", json={"kind": "demo.sleep", "title": t}).json()["id"] for t in "abc"]
        r = client.post("/api/jobs/reorder", json={"ids": [ids[2], ids[0], ids[1]]})
        assert [j["id"] for j in r.json()] == [ids[2], ids[0], ids[1]]

    def test_limpar_finalizados(self, client: TestClient) -> None:
        jid = client.post("/api/jobs", json={"kind": "demo.sleep"}).json()["id"]
        client.post(f"/api/jobs/{jid}/cancel")
        assert client.delete("/api/jobs/finished").json() == {"removed": 1}
        assert client.get("/api/jobs").json() == []

    def test_logs_do_job(self, client: TestClient, servicos: Servicos) -> None:
        jid = client.post("/api/jobs", json={"kind": "demo.sleep"}).json()["id"]
        servicos.store.registrar_log(jid, "info", "olá")
        assert [e["message"] for e in client.get(f"/api/jobs/{jid}/logs").json()] == ["olá"]
        assert client.get(f"/api/jobs/{ID_INEXISTENTE}/logs").status_code == 404

    def test_fluxo_completo_com_worker(self, client_com_worker: TestClient) -> None:
        c = client_com_worker
        jid = c.post("/api/jobs", json={"kind": "demo.sleep", "params": {"seconds": 0.4, "steps": 4}}).json()["id"]
        assert esperar(lambda: c.get(f"/api/jobs/{jid}").json()["status"] == "done")
        job = c.get(f"/api/jobs/{jid}").json()
        assert job["progress"] == 1.0 and job["result"] == {"seconds": 0.4, "steps": 4}
        assert {"Iniciado (tentativa 1)", "Concluído"} <= {e["message"] for e in c.get(f"/api/jobs/{jid}/logs").json()}


class TestLogsEBenchmark:
    def test_logs_com_filtros_e_validacao(self, client: TestClient) -> None:
        logging.getLogger("fabulim.teste").warning("aviso de teste")
        logging.getLogger("fabulim.teste").info("info de teste")
        for h in logging.getLogger("fabulim").handlers:
            h.flush()
        todos = client.get("/api/logs?service=teste").json()
        assert [e["msg"] for e in todos] == ["aviso de teste", "info de teste"]
        assert [e["msg"] for e in client.get("/api/logs?service=teste&level=WARNING").json()] == ["aviso de teste"]
        assert client.get("/api/logs?service=../../etc/passwd").status_code == 422
        assert client.get("/api/logs?level=BANANA").status_code == 422
        assert client.get("/api/logs?job_id=xyz").status_code == 422
        assert client.get("/api/logs?limit=0").status_code == 422
        assert client.get("/api/logs?limit=5000").status_code == 422

    def test_benchmark_roda_e_alimenta_a_matriz(self, client_com_worker: TestClient) -> None:
        c = client_com_worker
        antes = {x["id"]: x for x in c.get("/api/capabilities").json()}["llm_local"]
        assert antes["eta_measured"] is False
        job = c.post("/api/benchmark/run").json()
        assert esperar(lambda: c.get(f"/api/jobs/{job['id']}").json()["status"] == "done", timeout=30)
        resultado = c.get("/api/benchmark").json()
        tarefas = {r["task"]: r for r in resultado["results"]}
        assert tarefas["llm_ollama"]["status"] == "ok" and tarefas["image"]["status"] == "ok"
        assert tarefas["tts"]["status"] == tarefas["cutout"]["status"] == "ok"
        assert tarefas["music"]["status"] == tarefas["video"]["status"] == "skipped"
        assert resultado["measurements"]["llm_gen_tok_s"] == 10.0 and resultado["measurements"]["imagem_seg"] == 100.0
        caps = {x["id"]: x for x in c.get("/api/capabilities").json()}
        assert caps["llm_local"]["eta_measured"] is True and "qwen3:4b" in caps["llm_local"]["eta"]
        assert caps["imagem"]["eta_measured"] is True and "≈ 1,7 min" in caps["imagem"]["eta"]
        assert caps["voz"]["eta_measured"] is True and caps["recorte"]["eta_measured"] is True


class TestFrontendEstatico:
    def _dist(self, settings: Settings) -> Path:
        dist = settings.frontend_dist
        dist.mkdir(parents=True)
        (dist / "index.html").write_text("<!doctype html><title>Fabulim</title><app-root></app-root>", encoding="utf-8")
        (dist / "main.js").write_text("console.log('ok')", encoding="utf-8")
        return dist

    def test_serve_o_build_e_cai_no_index_nas_rotas_do_app(self, servicos: Servicos) -> None:
        self._dist(servicos.settings)
        with _cliente(servicos) as c:
            assert "app-root" in c.get("/").text
            assert "app-root" in c.get("/status/maquina").text  # rota do Angular (deep link)
            assert c.get("/main.js").text == "console.log('ok')"
            api = c.get("/api/nao-existe")
            assert api.status_code == 404 and api.headers["content-type"].startswith("application/json")

    def test_nao_vaza_arquivos_fora_da_pasta(self, servicos: Servicos) -> None:
        self._dist(servicos.settings)
        with _cliente(servicos) as c:
            for caminho in (
                "/%2e%2e/%2e%2e/CLAUDE.md",
                "/..%2f..%2fCLAUDE.md",
                "/....//....//CLAUDE.md",
                "/%252e%252e/CLAUDE.md",
            ):
                r = c.get(caminho)
                assert "memória do projeto" not in r.text, caminho

    def test_sem_build_a_raiz_devolve_404(self, client: TestClient) -> None:
        assert client.get("/").status_code == 404
