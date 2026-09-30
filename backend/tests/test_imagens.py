"""Gerar imagem avulsa: estimativa, prompt técnico, pedido, conferências e o job que salva na biblioteca."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.container import Servicos, criar_servicos
from app.erros import ErroParaOUsuario
from app.imagens.servico import ParametrosDeImagem, estimar, prompt_tecnico_da_ficha, sementes
from app.jobs.servico import enfileirar
from app.jobs.worker import JobCanceled
from app.prompts.formatos import FichaImagem
from app.tarefas.imagens import gerar_imagens

from .conftest import MedidoresFalsos, esperar, ollama_falso
from .fakes_motores import ContextoDeTeste, ImagemFalsa, motores_falsos

FORM: dict[str, Any] = {"kind": "cenario", "style": "2D", "format": "16:9", "description": "um jardim florido"}


def _imagem(sv: Servicos) -> ImagemFalsa:
    return cast(ImagemFalsa, sv.motores.imagem)


def _personagem_com_imagem(sv: Servicos, tmp_path: Path, nome: str = "Lila") -> str:
    personagem = sv.personagens.criar(nome, "2D", {"name": nome})
    origem = tmp_path / f"{nome}.png"
    Image.new("RGB", (64, 64), (255, 255, 255)).save(origem, "PNG")
    midia = sv.midias.adotar(origem, tipo="imagem", papel="escolhida", dono_tipo="personagem", dono_id=personagem.id)
    sv.personagens.definir_imagem_principal(personagem.id, midia.id)
    return personagem.id


def _esperar_job(c: TestClient, job_id: str, estado: str = "done") -> dict[str, Any]:
    assert esperar(lambda: c.get(f"/api/jobs/{job_id}").json()["status"] == estado), c.get(f"/api/jobs/{job_id}").json()
    job: dict[str, Any] = c.get(f"/api/jobs/{job_id}").json()
    return job


class TestEstimativaEPromptTecnico:
    def test_estimativa_por_formato_qualidade_e_quantidade(self, client: TestClient) -> None:
        r = client.get("/api/images/estimate").json()
        assert (r["width"], r["height"]) == (768, 432) and r["total_seconds"] == r["per_image_seconds"]
        quatro = client.get("/api/images/estimate", params={"count": 4}).json()
        assert quatro["total_seconds"] == pytest.approx(r["per_image_seconds"] * 4, abs=0.5)
        vertical = client.get("/api/images/estimate", params={"format": "9:16", "quality": "rascunho"}).json()
        assert (vertical["width"], vertical["height"]) == (352, 640)
        com_ref = client.get("/api/images/estimate", params={"references": 1}).json()
        assert com_ref["per_image_seconds"] == pytest.approx(r["per_image_seconds"] * 1.3, abs=0.5)
        assert r["total_label"].endswith(("s", "min"))

    def test_estimativa_valida_os_parametros(self, client: TestClient) -> None:
        for params in ({"format": "4:3"}, {"quality": "ultra"}, {"count": 5}, {"count": 0}, {"references": 9}):
            assert client.get("/api/images/estimate", params=params).status_code == 422

    def test_a_estimativa_usa_o_motor_de_verdade(self, servicos: Servicos) -> None:
        e = estimar(servicos.motores.imagem, "1:1", "rascunho", 2, False)
        assert (e.largura, e.altura) == (512, 512) and e.total_s == pytest.approx(e.por_imagem_s * 2)

    def test_prompt_tecnico_para_a_tela(self, client: TestClient) -> None:
        r = client.post("/api/images/technical-prompt", json={"form": {**FORM, "style": "3D"}}).json()
        assert "3D animated" in r["technical_prompt"] and "um jardim florido" in r["technical_prompt"]
        assert "scary" in r["negative_prompt"]

    def test_prompt_tecnico_com_personagem_cita_o_nome_e_a_referencia(
        self, client: TestClient, servicos: Servicos, tmp_path: Path
    ) -> None:
        pid = _personagem_com_imagem(servicos, tmp_path)
        r = client.post(
            "/api/images/technical-prompt", json={"form": {**FORM, "kind": "livre"}, "character_ids": [pid]}
        ).json()
        assert "Characters in the scene: Lila" in r["technical_prompt"] and "reference image" in r["technical_prompt"]

    def test_prompt_tecnico_com_personagem_sem_imagem(self, client: TestClient, servicos: Servicos) -> None:
        personagem = servicos.personagens.criar("Bento", "2D", {"name": "Bento"})
        r = client.post("/api/images/technical-prompt", json={"form": FORM, "character_ids": [personagem.id]})
        assert r.status_code == 422 and "Bento" in r.json()["detail"] and "escolhida" in r.json()["detail"]

    def test_sementes_previsiveis_quando_informadas(self) -> None:
        assert sementes(100, 3) == [100, 100 + 7919, 100 + 2 * 7919]
        assert sementes(None, 1)[0] > 0 and len(set(sementes(None, 4))) == 4

    def test_prompt_da_ficha(self) -> None:
        ficha = FichaImagem(kind="objeto", description="uma bola")
        assert "Single object" in prompt_tecnico_da_ficha(ficha, [])


class TestPedirImagem:
    def _pedir(self, client: TestClient, **campos: Any) -> Any:
        corpo = {"form": FORM, **campos}
        return client.post("/api/images", json=corpo)

    def test_enfileira_o_job_com_os_parametros_validados(self, client: TestClient) -> None:
        r = self._pedir(client, quality="rascunho", count=3, seed=7)
        assert r.status_code == 202
        job = r.json()
        assert (
            job["kind"] == "imagem.gerar" and job["title"] == "Gerar imagem (3 imagens)" and job["status"] == "queued"
        )
        assert job["params"]["count"] == 3 and job["params"]["seed"] == 7 and job["params"]["form"]["style"] == "2D"
        assert self._pedir(client).json()["title"] == "Gerar imagem (1 imagem)"

    @pytest.mark.parametrize(
        "campos",
        [
            {"count": 5},
            {"count": 0},
            {"quality": "ultra"},
            {"seed": -1},
            {"character_ids": ["a", "b", "c", "d"]},
            {"based_on": "../../x"},
            {"form": {**FORM, "format": "4:3"}},
            {"form": {**FORM, "kind": "video"}},
            {"technical_prompt": "x" * 4001},
        ],
    )
    def test_rejeita_pedido_invalido(self, client: TestClient, campos: dict[str, Any]) -> None:
        assert self._pedir(client, **campos).status_code == 422

    def test_pede_uma_descricao(self, client: TestClient) -> None:
        r = self._pedir(client, form={**FORM, "description": "  "})
        assert r.status_code == 422 and "Descreva" in r.json()["detail"]

    def test_o_prompt_tecnico_editado_vale_no_lugar_da_descricao(self, client: TestClient) -> None:
        r = self._pedir(client, form={**FORM, "description": ""}, technical_prompt="a red ball on green grass")
        assert r.status_code == 202

    def test_filtro_de_conteudo_no_formulario_e_no_prompt_tecnico(self, client: TestClient) -> None:
        r = self._pedir(client, form={**FORM, "description": "a Peppa Pig no jardim"})
        assert r.status_code == 422 and "peppa" in r.json()["detail"]
        r = self._pedir(client, technical_prompt="a scary monster made of blood")
        assert r.status_code == 422 and "Reescreva" in r.json()["detail"]
        r = self._pedir(client, form={**FORM, "notes": "com muito terror"})
        assert r.status_code == 422

    def test_sem_motor_de_imagem_diz_o_que_fazer(self, client: TestClient, servicos: Servicos) -> None:
        servicos.motores.imagem = ImagemFalsa(indisponivel="O motor de imagens ainda não está instalado")
        r = self._pedir(client)
        assert r.status_code == 503 and "instalado" in r.json()["detail"]

    def test_personagem_inexistente_ou_sem_imagem(self, client: TestClient, servicos: Servicos) -> None:
        r = self._pedir(client, character_ids=["0" * 32])
        assert r.status_code == 422 and "não existe" in r.json()["detail"]
        sem = servicos.personagens.criar("Sol", "2D", {"name": "Sol"})
        r = self._pedir(client, character_ids=[sem.id])
        assert r.status_code == 422 and "Sol" in r.json()["detail"]

    def test_imagem_base_que_sumiu(self, client: TestClient) -> None:
        r = self._pedir(client, based_on="0" * 32)
        assert r.status_code == 422 and "base" in r.json()["detail"]

    def test_outro_site_nao_consegue_pedir(self, client: TestClient) -> None:
        r = client.post("/api/images", json={"form": FORM}, headers={"Origin": "http://site-malicioso.example"})
        assert r.status_code == 403


class TestJobDeImagem:
    def test_gera_as_variacoes_e_guarda_cada_uma_na_biblioteca(
        self, client_com_worker: TestClient, servicos: Servicos, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        eventos: list[tuple[str, dict[str, Any]]] = []
        original = servicos.bus.publicar
        monkeypatch.setattr(
            servicos.bus, "publicar", lambda tipo, dados: (eventos.append((tipo, dados)), original(tipo, dados))
        )
        r = client_com_worker.post("/api/images", json={"form": FORM, "count": 3, "seed": 100, "quality": "rascunho"})
        job = _esperar_job(client_com_worker, r.json()["id"])
        assert job["progress"] == 1.0 and len(job["result"]["media_ids"]) == 3
        assert (job["result"]["width"], job["result"]["height"]) == (640, 352)
        assert [p.seed for p in _imagem(servicos).pedidos] == [100, 100 + 7919, 100 + 2 * 7919]
        assert all((p.largura, p.altura) == (640, 352) for p in _imagem(servicos).pedidos)
        midias = servicos.midias.listar(mais_antigas_primeiro=True)
        assert [m.id for m in midias] == job["result"]["media_ids"]
        primeira = midias[0]
        assert (
            primeira.papel == "cenario"
            and primeira.estilo == "2D"
            and primeira.seed == 100
            and primeira.modelo == "falso"
        )
        assert primeira.prompt == "um jardim florido" and "um jardim florido" in (primeira.prompt_tecnico or "")
        assert primeira.negativo and primeira.job_id == job["id"]
        assert primeira.metadados["count"] == 3 and primeira.metadados["quality"] == "rascunho"
        assert primeira.metadados["group"] == midias[2].metadados["group"] == job["result"]["group"]
        assert [m.metadados["index"] for m in midias] == [0, 1, 2]
        assert [dados["id"] for tipo, dados in eventos if tipo == "media.created"] == job["result"]["media_ids"]
        with Image.open(servicos.midias.caminho_absoluto(primeira)) as arquivo:
            assert arquivo.size == (640, 352)
        assert list(servicos.settings.temp_dir.glob("img-*")) == []  # nenhum temporário sobrando

    def test_o_prompt_tecnico_editado_e_o_que_vai_para_o_modelo_e_para_a_biblioteca(
        self, client_com_worker: TestClient, servicos: Servicos
    ) -> None:
        r = client_com_worker.post("/api/images", json={"form": FORM, "technical_prompt": "  a red ball  "})
        _esperar_job(client_com_worker, r.json()["id"])
        assert _imagem(servicos).pedidos[0].prompt == "a red ball"
        assert servicos.midias.listar()[0].prompt_tecnico == "a red ball"

    def test_com_personagens_usa_a_imagem_deles_como_referencia(
        self, client_com_worker: TestClient, servicos: Servicos, tmp_path: Path
    ) -> None:
        pid = _personagem_com_imagem(servicos, tmp_path)
        r = client_com_worker.post("/api/images", json={"form": {**FORM, "kind": "livre"}, "character_ids": [pid]})
        job = _esperar_job(client_com_worker, r.json()["id"])
        pedido = _imagem(servicos).pedidos[0]
        principal = servicos.personagens.obter(pid)
        assert principal is not None and principal.imagem_principal_id
        da_referencia = servicos.midias.obter(principal.imagem_principal_id)
        assert da_referencia is not None
        esperado = servicos.midias.caminho_absoluto(da_referencia)
        assert pedido.referencias == (esperado,) and "Characters in the scene: Lila" in pedido.prompt
        salvo = servicos.midias.obter(job["result"]["media_ids"][0])
        assert salvo is not None and salvo.metadados["characters"] == [{"id": pid, "name": "Lila"}]

    def test_parecida_com_esta_usa_a_imagem_como_base(self, client_com_worker: TestClient, servicos: Servicos) -> None:
        primeira = client_com_worker.post("/api/images", json={"form": FORM}).json()
        base_id = _esperar_job(client_com_worker, primeira["id"])["result"]["media_ids"][0]
        segunda = client_com_worker.post("/api/images", json={"form": FORM, "based_on": base_id}).json()
        job = _esperar_job(client_com_worker, segunda["id"])
        filha = servicos.midias.obter(job["result"]["media_ids"][0])
        assert filha is not None and filha.pai_id == base_id
        assert (
            len(_imagem(servicos).pedidos[1].referencias) == 1
            and "reference image" in _imagem(servicos).pedidos[1].prompt
        )

    def test_descarrega_o_modelo_de_texto_antes_de_gerar(self, settings: Settings) -> None:
        cliente, chamadas = ollama_falso(gpu=True)
        sv = criar_servicos(settings, ollama=cliente, medidores=MedidoresFalsos(), motores=motores_falsos())
        gerar_imagens(
            ContextoDeTeste(servicos=sv), ParametrosDeImagem(form=FichaImagem(description="um lago")).model_dump()
        )
        assert (
            "GET /api/ps" in chamadas and "POST /api/generate" in chamadas
        )  # listou o que estava carregado e descarregou
        assert chamadas.index("GET /api/ps") < chamadas.index("POST /api/generate")

    def test_cancelar_no_meio_mantem_as_imagens_que_ja_sairam(self, servicos: Servicos) -> None:
        ctx = ContextoDeTeste(cancelar_no_ponto=5, servicos=servicos)  # 2 pontos por imagem: cancela ao começar a 3ª
        params = ParametrosDeImagem(form=FichaImagem(description="um lago"), count=3).model_dump()
        with pytest.raises(JobCanceled):
            gerar_imagens(ctx, params)
        assert servicos.midias.contar() == 2 and len(_imagem(servicos).pedidos) == 2

    def test_falha_do_motor_aparece_em_portugues_sem_nome_de_classe(
        self, client_com_worker: TestClient, servicos: Servicos
    ) -> None:
        servicos.motores.imagem = ImagemFalsa(falhar="Não consegui gerar a imagem. vulkan: sem memória")
        r = client_com_worker.post("/api/images", json={"form": FORM})
        job = _esperar_job(client_com_worker, r.json()["id"], "failed")
        assert job["error"] == "Não consegui gerar a imagem. vulkan: sem memória"
        assert servicos.midias.contar() == 0

    def test_o_job_confere_o_filtro_de_novo_mesmo_sem_passar_pela_api(
        self, client_com_worker: TestClient, servicos: Servicos
    ) -> None:
        params = {"form": {**FORM, "description": "igual ao Mickey"}}
        job = enfileirar(servicos, "imagem.gerar", params)
        resultado = _esperar_job(client_com_worker, job.id, "failed")
        assert "mickey" in resultado["error"] and _imagem(servicos).pedidos == []

    def test_parametros_invalidos_no_job(self, servicos: Servicos) -> None:
        with pytest.raises(ErroParaOUsuario, match="incompleto"):
            gerar_imagens(ContextoDeTeste(servicos=servicos), {"form": {"kind": "video"}})
