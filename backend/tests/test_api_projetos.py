"""API de projetos: criar a partir do enredo, etapas com aprovação, cenas com versões e o fluxo completo até o vídeo montado."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.container import Servicos
from app.projetos.servico import duracao_alvo_em_segundos

from .builders_projetos import dar_cenario, personagem_pronto
from .conftest import esperar
from .fakes_motores import FfmpegFalso, ImagemFalsa, TextoFalso

pytestmark = pytest.mark.usefixtures("resolucoes_pequenas")

FORM: dict[str, Any] = {
    "title": "A chuva do jardim",
    "format": "short",
    "target_duration": "30 s",
    "language": "pt-BR",
    "style": "2D",
    "characters": ["Lila", "Bento"],
    "theme": "dividir é bom",
    "settings": "jardim, casa",
    "story": "Lila brinca no jardim. Começa a chover. Bento chega com um guarda-chuva. Os dois cantam juntos.",
    "music": "cantiga da chuva",
}


@pytest.fixture
def elenco(servicos: Servicos, tmp_path: Path) -> list[Any]:
    return [
        personagem_pronto(servicos, tmp_path, "Lila"),
        personagem_pronto(servicos, tmp_path, "Bento", species="urso"),
    ]


def _criar(client: TestClient, **campos: Any) -> dict[str, Any]:
    r = client.post(
        "/api/projects", json={"form": {**FORM, **campos}, "original_prompt": "### ENREDO\nTítulo: A chuva"}
    )
    assert r.status_code == 201, r.text
    corpo: dict[str, Any] = r.json()
    return corpo


def _esperar_job(c: TestClient, job_id: str, estado: str = "done") -> dict[str, Any]:
    assert esperar(lambda: c.get(f"/api/jobs/{job_id}").json()["status"] == estado, timeout=90, passo=0.2), c.get(
        f"/api/jobs/{job_id}"
    ).json()
    job: dict[str, Any] = c.get(f"/api/jobs/{job_id}").json()
    return job


def _detalhes(c: TestClient, pid: str) -> dict[str, Any]:
    d: dict[str, Any] = c.get(f"/api/projects/{pid}").json()
    return d


class TestDuracaoAlvo:
    @pytest.mark.parametrize(
        ("texto", "formato", "esperado"),
        [
            ("60 s", "short", 60),
            ("45", "short", 45),
            ("90 segundos", "short", 60),  # Short passa de 60 s? fica em 60
            ("10 s", "short", 15),  # muito curto sobe para o mínimo
            ("3 min", "longo", 180),
            ("2,5 minutos", "longo", 150),
            ("1:30", "longo", 90),
            ("10 minutos", "longo", 300),
            ("", "short", 45),
            ("", "longo", 120),
            ("sem número", "longo", 120),
        ],
    )
    def test_conversoes(self, texto: str, formato: str, esperado: int) -> None:
        assert duracao_alvo_em_segundos(texto, formato) == esperado


class TestCriar:
    def test_reconhece_os_personagens_do_enredo_e_avisa_dos_que_faltam(
        self, client: TestClient, elenco: list[Any]
    ) -> None:
        r = _criar(client, characters=["Lila", "bento", "Sol"])
        projeto = r["project"]
        assert projeto["title"] == "A chuva do jardim" and projeto["format"] == "short" and projeto["aspect"] == "9:16"
        assert projeto["character_ids"] == [elenco[0].id, elenco[1].id] and r["missing_characters"] == ["Sol"]
        assert projeto["target_duration_s"] == 30 and projeto["stage"] == "enredo" and projeto["approvals"] == {}
        assert (
            projeto["story"]["original_prompt"].startswith("### ENREDO")
            and projeto["story"]["theme"] == "dividir é bom"
        )
        assert r["style_warnings"] == []

    def test_personagens_escolhidos_na_grade_tambem_valem(self, client: TestClient, elenco: list[Any]) -> None:
        r = client.post(
            "/api/projects", json={"form": {**FORM, "characters": []}, "character_ids": [elenco[1].id]}
        ).json()
        assert r["project"]["character_ids"] == [elenco[1].id] and r["missing_characters"] == []

    def test_avisa_quando_o_personagem_e_de_outro_estilo(self, client: TestClient, elenco: list[Any]) -> None:
        r = _criar(client, style="3D", characters=["Lila"])
        assert [w["name"] for w in r["style_warnings"]] == ["Lila"]
        assert (
            "Crie a versão 3D" in r["style_warnings"][0]["message"]
            and r["style_warnings"][0]["character_style"] == "2D"
        )

    def test_duracao_e_formato_longo(self, client: TestClient, elenco: list[Any]) -> None:
        r = _criar(client, format="longo", target_duration="3 min")["project"]
        assert (r["aspect"], r["target_duration_s"]) == ("16:9", 180)
        assert (
            client.post("/api/projects", json={"form": FORM, "target_duration_s": 90}).json()["project"][
                "target_duration_s"
            ]
            == 60
        )

    def test_validacoes(self, client: TestClient, elenco: list[Any]) -> None:
        r = client.post("/api/projects", json={"form": {**FORM, "story": "  "}})
        assert r.status_code == 422 and "Escreva a história" in r.json()["detail"]
        assert (
            client.post("/api/projects", json={"form": {**FORM, "story": "Lila e a Peppa Pig brincam."}}).status_code
            == 422
        )
        assert (
            client.post("/api/projects", json={"form": FORM, "original_prompt": "um monstro assustador"}).status_code
            == 422
        )
        assert client.post("/api/projects", json={"form": FORM, "character_ids": ["0" * 32]}).status_code == 422
        assert client.post("/api/projects", json={"form": {**FORM, "format": "quadrado"}}).status_code == 422
        assert client.post("/api/projects", json={"form": FORM, "target_duration_s": 5}).status_code == 422
        assert client.post("/api/projects", json={}).status_code == 422

    def test_sem_titulo_ganha_um_nome(self, client: TestClient, elenco: list[Any]) -> None:
        assert _criar(client, title="  ")["project"]["title"] == "Meu vídeo"

    def test_outro_site_nao_consegue_criar(self, client: TestClient) -> None:
        r = client.post("/api/projects", json={"form": FORM}, headers={"Origin": "http://site-malicioso.example"})
        assert r.status_code == 403


class TestListarEDetalhar:
    def test_lista_com_resumo(self, client: TestClient, elenco: list[Any]) -> None:
        pid = _criar(client)["project"]["id"]
        lista = client.get("/api/projects").json()
        assert lista["total"] == 1 and lista["items"][0]["id"] == pid
        item = lista["items"][0]
        assert item["scene_count"] == 0 and item["has_final"] is False and item["thumb_url"] is None
        assert item["characters"] == ["Lila", "Bento"] and "story" not in item

    def test_detalhes_completos(self, client: TestClient, elenco: list[Any]) -> None:
        pid = _criar(client)["project"]["id"]
        d = _detalhes(client, pid)
        assert set(d) == {
            "project",
            "scenes",
            "characters",
            "missing_character_ids",
            "style_warnings",
            "stages",
            "files",
            "metadata",
            "quality",
            "active_jobs",
            "variants",
        }
        assert (
            [p["name"] for p in d["characters"]] == ["Lila", "Bento"]
            and d["scenes"] == []
            and d["files"]["final"] is None
        )
        assert [e["id"] for e in d["stages"]["stages"]] == [
            "enredo",
            "roteiro",
            "storyboard",
            "animacao",
            "audio",
            "montagem",
            "revisao",
        ]
        assert d["stages"]["current"] == "enredo" and d["stages"]["stages"][0]["ready"] is True
        assert client.get(f"/api/projects/{'0' * 32}").status_code == 404
        assert client.get("/api/projects/nao-e-id").status_code == 422

    def test_opcoes_para_a_interface(self, client: TestClient) -> None:
        o = client.get("/api/projects/options").json()
        assert "pular" in o["actions"] and "zoom_in" in o["cameras"] and "crescer" in o["entrances"]
        assert {m["id"] for m in o["music_styles"]} == {"alegre", "calma", "aventura"}
        assert {t["id"] for t in o["transitions"]} == {"corte", "fade", "suave"} and "pt-BR" in o["voices"]
        assert o["action_labels"]["pular"] == "Pulando"


class TestEditarEApagar:
    def test_editar_titulo_duracao_e_personagens(self, client: TestClient, elenco: list[Any]) -> None:
        pid = _criar(client)["project"]["id"]
        d = client.patch(
            f"/api/projects/{pid}",
            json={"title": "Novo título", "target_duration_s": 45, "character_ids": [elenco[0].id]},
        ).json()
        assert d["project"]["title"] == "Novo título" and d["project"]["target_duration_s"] == 45
        assert d["project"]["character_ids"] == [elenco[0].id]
        assert (
            client.patch(f"/api/projects/{pid}", json={"target_duration_s": 200}).json()["project"]["target_duration_s"]
            == 60
        )  # Short

    def test_musica_e_ajustes_validados(self, client: TestClient, elenco: list[Any]) -> None:
        pid = _criar(client)["project"]["id"]
        d = client.patch(
            f"/api/projects/{pid}",
            json={
                "music": {"style": "calma", "volume": 0.9, "enabled": False, "seed": 7},
                "settings": {"fps": 30, "transition": "fade", "narrator": {"id": "pf_dora"}},
            },
        ).json()["project"]
        assert d["music"] == {"style": "calma", "volume": 0.6, "enabled": False, "seed": 7}
        assert (
            d["settings"]["fps"] == 30
            and d["settings"]["transition"] == "fade"
            and d["settings"]["narrator"]["id"] == "pf_dora"
        )
        for corpo in (
            {"music": {"style": "heavy metal"}},
            {"music": {"seed": "x"}},
            {"settings": {"fps": 5}},
            {"settings": {"transition": "explosão"}},
            {"settings": {"narrator": {"id": "voz-x"}}},
            {"settings": {"cor": "azul"}},
            {"title": ""},
            {"character_ids": ["0" * 32]},
        ):
            assert client.patch(f"/api/projects/{pid}", json=corpo).status_code == 422, corpo

    def test_editar_a_historia_reabre_tudo(self, client: TestClient, elenco: list[Any]) -> None:
        pid = _criar(client)["project"]["id"]
        client.post(f"/api/projects/{pid}/stages/enredo/approve", json={})
        d = client.patch(f"/api/projects/{pid}", json={"story": {"story": "Uma história nova e curta."}}).json()
        assert d["project"]["story"]["story"] == "Uma história nova e curta." and d["project"]["approvals"] == {}
        assert d["project"]["story"]["original_prompt"].startswith("### ENREDO")
        assert client.patch(f"/api/projects/{pid}", json={"story": {"story": ""}}).status_code == 422
        assert client.patch(f"/api/projects/{pid}", json={"story": {"format": "longo"}}).status_code == 422
        assert (
            client.patch(f"/api/projects/{pid}", json={"story": {"story": "Com sangue e terror."}}).status_code == 422
        )

    def test_apagar_leva_cenas_e_midias_e_solta_as_variantes(
        self, client: TestClient, servicos: Servicos, elenco: list[Any], tmp_path: Path
    ) -> None:
        pid = _criar(client)["project"]["id"]
        cena = client.post(f"/api/projects/{pid}/scenes", json={"data": {"title": "a"}}).json()["scene"]
        servicos.projetos.criar("Variante", "short", "en", "2D", 30, {}, [], origem_id=pid)
        antes = servicos.midias.contar()
        from app.projetos.repositorio import Cena

        cena_db = servicos.projetos.cena(cena["id"])
        assert isinstance(cena_db, Cena)
        dar_cenario(servicos, tmp_path, cena_db)
        assert servicos.midias.contar() == antes + 1
        r = client.delete(f"/api/projects/{pid}")
        assert r.json() == {"deleted": True, "media_removed": 1} and servicos.midias.contar() == antes
        assert client.get(f"/api/projects/{pid}").status_code == 404
        variante = servicos.projetos.listar()[0]
        assert variante.configuracoes["origin_deleted"] is True
        assert client.delete(f"/api/projects/{pid}").status_code == 404


class TestEtapas:
    def test_o_enredo_precisa_de_historia_e_a_etapa_seguinte_de_aprovacao(
        self, client: TestClient, elenco: list[Any]
    ) -> None:
        pid = _criar(client)["project"]["id"]
        assert client.post(f"/api/projects/{pid}/script", json={}).status_code == 409
        assert (
            "Aprove a etapa «Enredo e personagens»"
            in client.post(f"/api/projects/{pid}/script", json={}).json()["detail"]
        )
        d = client.post(f"/api/projects/{pid}/stages/enredo/approve", json={}).json()
        assert d["project"]["approvals"] == {"enredo": True} and d["project"]["stage"] == "roteiro"
        assert d["stages"]["current"] == "roteiro"

    def test_nao_pula_etapas(self, client: TestClient, elenco: list[Any]) -> None:
        pid = _criar(client)["project"]["id"]
        r = client.post(f"/api/projects/{pid}/stages/storyboard/approve", json={})
        assert r.status_code == 409 and "Aprove a etapa «Roteiro»" in r.json()["detail"]
        assert client.post(f"/api/projects/{pid}/stages/voar/approve", json={}).status_code == 404
        client.post(f"/api/projects/{pid}/stages/enredo/approve", json={})
        r = client.post(f"/api/projects/{pid}/stages/roteiro/approve", json={})
        assert r.status_code == 409 and "gere o roteiro" in r.json()["detail"]

    def test_gera_o_roteiro_e_aprova_cena_a_cena_ou_todas(
        self, client_com_worker: TestClient, elenco: list[Any]
    ) -> None:
        c = client_com_worker
        pid = _criar(c)["project"]["id"]
        c.post(f"/api/projects/{pid}/stages/enredo/approve", json={})
        job = c.post(f"/api/projects/{pid}/script", json={"mode": "simples"})
        assert job.status_code == 202 and job.json()["kind"] == "projeto.roteiro"
        _esperar_job(c, job.json()["id"])
        d = _detalhes(c, pid)
        assert len(d["scenes"]) >= 2 and d["project"]["stage"] == "roteiro"
        assert d["stages"]["stages"][1]["scenes_approved"] == 0
        r = c.post(f"/api/projects/{pid}/stages/roteiro/approve", json={})
        assert r.status_code == 409 and "Aprove todas as cenas" in r.json()["detail"]
        primeira = d["scenes"][0]["id"]
        assert c.post(f"/api/projects/{pid}/scenes/{primeira}/approve", json={"stage": "roteiro"}).json()["scene"][
            "data"
        ]["approved"]["roteiro"]
        r = c.post(f"/api/projects/{pid}/stages/roteiro/approve", json={"approve_all": True}).json()
        assert r["project"]["approvals"]["roteiro"] is True and r["project"]["stage"] == "storyboard"
        assert all(s["data"]["approved"]["roteiro"] for s in r["scenes"])

    def test_pedir_o_mesmo_job_de_novo_devolve_o_que_ja_esta_na_fila(
        self, client: TestClient, elenco: list[Any]
    ) -> None:
        pid = _criar(client)["project"]["id"]
        client.post(f"/api/projects/{pid}/stages/enredo/approve", json={})
        a = client.post(f"/api/projects/{pid}/script", json={"mode": "simples"}).json()
        b = client.post(f"/api/projects/{pid}/script", json={"mode": "simples"}).json()
        assert a["id"] == b["id"] and len(_detalhes(client, pid)["active_jobs"]) == 1

    def test_roteiro_por_ia_sem_o_modelo_local_diz_o_que_fazer(
        self, client: TestClient, servicos: Servicos, elenco: list[Any]
    ) -> None:
        servicos.motores.texto = TextoFalso(indisponivel="O Ollama não está no ar")
        pid = _criar(client)["project"]["id"]
        client.post(f"/api/projects/{pid}/stages/enredo/approve", json={})
        r = client.post(f"/api/projects/{pid}/script", json={"mode": "ia"})
        assert r.status_code == 503 and "Ollama" in r.json()["detail"]
        assert client.post(f"/api/projects/{pid}/script", json={"mode": "simples"}).status_code == 202

    def test_reabrir_volta_as_etapas_seguintes(self, client: TestClient, elenco: list[Any]) -> None:
        pid = _criar(client)["project"]["id"]
        client.post(f"/api/projects/{pid}/stages/enredo/approve", json={})
        d = client.post(f"/api/projects/{pid}/stages/enredo/reopen").json()
        assert d["project"]["approvals"] == {} and d["project"]["stage"] == "enredo"
        assert client.post(f"/api/projects/{pid}/stages/voar/reopen").status_code == 404

    def test_storyboard_animacao_audio_e_montagem_seguem_a_ordem(
        self, client: TestClient, servicos: Servicos, elenco: list[Any]
    ) -> None:
        pid = _criar(client)["project"]["id"]
        for caminho, corpo, etapa in (
            ("storyboard", {}, "Roteiro"),
            ("animate", {}, "Storyboard"),
            ("audio", {}, "Animação"),
            ("assemble", {}, "Áudio"),
        ):
            r = client.post(f"/api/projects/{pid}/{caminho}", json=corpo)
            assert r.status_code == 409 and f"«{etapa}»" in r.json()["detail"], caminho

    def test_storyboard_avisa_do_personagem_sem_recorte_antes_de_gastar_tempo(
        self, client: TestClient, servicos: Servicos, tmp_path: Path
    ) -> None:
        sem = personagem_pronto(servicos, tmp_path, "Sol", slots=())
        pid = client.post("/api/projects", json={"form": {**FORM, "characters": []}, "character_ids": [sem.id]}).json()[
            "project"
        ]["id"]
        servicos.projetos.criar_cena(pid, {"title": "a", "characters": [sem.id]})
        servicos.projetos.atualizar(pid, aprovacoes={"enredo": True, "roteiro": True})
        r = client.post(f"/api/projects/{pid}/storyboard", json={})
        assert r.status_code == 409 and "PNG transparente" in r.json()["detail"]
        assert cast(ImagemFalsa, servicos.motores.imagem).pedidos == []


class TestCenas:
    def _projeto(self, client: TestClient, servicos: Servicos, elenco: list[Any]) -> tuple[str, list[str]]:
        pid = _criar(client)["project"]["id"]
        ids = [
            client.post(
                f"/api/projects/{pid}/scenes",
                json={
                    "data": {"title": t, "duration_s": 5.0, "narration": f"Texto {t}.", "characters": [elenco[0].id]}
                },
            ).json()["scene"]["id"]
            for t in ("um", "dois", "tres")
        ]
        return pid, ids

    def test_criar_e_posicionar(self, client: TestClient, servicos: Servicos, elenco: list[Any]) -> None:
        pid, ids = self._projeto(client, servicos, elenco)
        r = client.post(f"/api/projects/{pid}/scenes", json={"data": {"title": "meio"}, "position": 2})
        assert r.status_code == 201 and r.json()["scene"]["order"] == 2 and r.json()["scene"]["version"] == 1
        assert [s["data"]["title"] for s in _detalhes(client, pid)["scenes"]] == ["um", "meio", "dois", "tres"]
        assert r.json()["stages"]["stages"][1]["scenes_total"] == 4
        assert ids

    def test_criar_valida(self, client: TestClient, servicos: Servicos, elenco: list[Any]) -> None:
        pid, _ = self._projeto(client, servicos, elenco)
        assert client.post(f"/api/projects/{pid}/scenes", json={"data": {"duration_s": 99}}).status_code == 422
        assert client.post(f"/api/projects/{pid}/scenes", json={"data": {"characters": ["0" * 32]}}).status_code == 422
        assert (
            client.post(f"/api/projects/{pid}/scenes", json={"data": {"narration": "com muito sangue"}}).status_code
            == 422
        )
        assert client.post(f"/api/projects/{pid}/scenes", json={"data": {}, "position": 0}).status_code == 422

    def test_uma_cena_pode_usar_um_personagem_que_ainda_nao_estava_no_projeto(
        self, client: TestClient, servicos: Servicos, elenco: list[Any], tmp_path: Path
    ) -> None:
        pid = client.post(
            "/api/projects", json={"form": {**FORM, "characters": []}, "character_ids": [elenco[0].id]}
        ).json()["project"]["id"]
        novo = personagem_pronto(servicos, tmp_path, "Sol")
        r = client.post(f"/api/projects/{pid}/scenes", json={"data": {"characters": [novo.id]}})
        assert r.status_code == 201 and novo.id in _detalhes(client, pid)["project"]["character_ids"]

    def test_editar_guarda_versao_e_pede_nova_aprovacao(
        self, client: TestClient, servicos: Servicos, elenco: list[Any]
    ) -> None:
        pid, ids = self._projeto(client, servicos, elenco)
        client.post(f"/api/projects/{pid}/scenes/{ids[0]}/approve", json={"stage": "roteiro"})
        r = client.patch(
            f"/api/projects/{pid}/scenes/{ids[0]}", json={"changes": {"narration": "Outra frase.", "emotion": "feliz"}}
        )
        assert r.status_code == 200
        cena = r.json()["scene"]
        assert (
            cena["version"] == 2
            and cena["data"]["narration"] == "Outra frase."
            and cena["data"]["approved"]["roteiro"] is False
        )
        assert (
            client.patch(
                f"/api/projects/{pid}/scenes/{ids[0]}", json={"changes": {"narration": "Outra frase."}}
            ).json()["scene"]["version"]
            == 2
        )  # igual: nada muda

    def test_editar_valida(self, client: TestClient, servicos: Servicos, elenco: list[Any]) -> None:
        pid, ids = self._projeto(client, servicos, elenco)
        url = f"/api/projects/{pid}/scenes/{ids[0]}"
        assert client.patch(url, json={"changes": {"duration_s": 99}}).status_code == 422
        assert client.patch(url, json={"changes": {"background": {"media_id": "x"}}}).status_code == 422
        assert client.patch(url, json={"changes": {"narration": "cena de terror"}}).status_code == 422
        assert (
            client.patch(
                url, json={"changes": {"dialogue": [{"character_id": None, "text": "vou pegar a faca"}]}}
            ).status_code
            == 422
        )
        assert client.patch(url, json={"changes": {"characters": ["0" * 32]}}).status_code == 422
        assert client.patch(url, json={"changes": {}}).status_code == 422
        assert (
            client.patch(f"/api/projects/{pid}/scenes/{'0' * 32}", json={"changes": {"title": "x"}}).status_code == 404
        )

    def test_a_cena_e_de_um_projeto_so(self, client: TestClient, servicos: Servicos, elenco: list[Any]) -> None:
        _, ids = self._projeto(client, servicos, elenco)
        outro = _criar(client, title="Outro")["project"]["id"]
        assert (
            client.patch(f"/api/projects/{outro}/scenes/{ids[0]}", json={"changes": {"title": "x"}}).status_code == 404
        )
        assert client.delete(f"/api/projects/{outro}/scenes/{ids[0]}").status_code == 404

    def test_apagar_e_reordenar(self, client: TestClient, servicos: Servicos, elenco: list[Any]) -> None:
        pid, ids = self._projeto(client, servicos, elenco)
        d = client.post(f"/api/projects/{pid}/scenes/reorder", json={"ids": [ids[2], ids[0], ids[1]]}).json()
        assert [s["data"]["title"] for s in d["scenes"]] == ["tres", "um", "dois"]
        assert client.post(f"/api/projects/{pid}/scenes/reorder", json={"ids": ids[:2]}).status_code == 422
        r = client.delete(f"/api/projects/{pid}/scenes/{ids[1]}")
        assert r.json()["deleted"] is True and r.json()["stages"]["stages"][1]["scenes_total"] == 2
        assert [s["order"] for s in _detalhes(client, pid)["scenes"]] == [1, 2]

    def test_versoes_e_voltar(self, client: TestClient, servicos: Servicos, elenco: list[Any]) -> None:
        pid, ids = self._projeto(client, servicos, elenco)
        url = f"/api/projects/{pid}/scenes/{ids[0]}"
        client.patch(url, json={"changes": {"narration": "Segunda versão."}})
        client.patch(url, json={"changes": {"narration": "Terceira versão."}})
        v = client.get(f"{url}/versions").json()
        assert v["current"] == 3 and [x["version"] for x in v["versions"]] == [3, 2, 1]
        assert v["versions"][2]["data"]["narration"] == "Texto um." and v["versions"][2]["reason"] == "criada"
        r = client.post(f"{url}/restore", json={"version": 1})
        assert (
            r.status_code == 200
            and r.json()["scene"]["data"]["narration"] == "Texto um."
            and r.json()["scene"]["version"] == 4
        )
        assert [x["version"] for x in client.get(f"{url}/versions").json()["versions"]] == [
            4,
            3,
            2,
            1,
        ]  # nada se perdeu
        assert client.post(f"{url}/restore", json={"version": 99}).status_code == 404
        assert client.post(f"{url}/restore", json={"version": 0}).status_code == 422

    def test_voltar_versao_descarta_o_que_aponta_para_midia_que_sumiu(
        self, client: TestClient, servicos: Servicos, elenco: list[Any], tmp_path: Path
    ) -> None:
        pid, ids = self._projeto(client, servicos, elenco)
        cena = servicos.projetos.cena(ids[0])
        assert cena is not None
        fundo = dar_cenario(servicos, tmp_path, cena)
        servicos.projetos.atualizar_cena(ids[0], servicos.projetos.cena(ids[0]).dados, "com cenário")  # type: ignore[union-attr]
        servicos.midias.remover(fundo)
        r = client.post(f"/api/projects/{pid}/scenes/{ids[0]}/restore", json={"version": 2})
        dados = r.json()["scene"]["data"]
        assert dados["background"] is None and dados["candidates"] == [] and dados["approved"] == {}

    def test_aprovar_exige_o_que_a_etapa_precisa(
        self, client: TestClient, servicos: Servicos, elenco: list[Any]
    ) -> None:
        pid, ids = self._projeto(client, servicos, elenco)
        url = f"/api/projects/{pid}/scenes/{ids[0]}/approve"
        assert client.post(url, json={"stage": "storyboard"}).status_code == 409
        assert client.post(url, json={"stage": "animacao"}).status_code == 409
        assert client.post(url, json={"stage": "voar"}).status_code == 422
        assert client.post(url, json={"stage": "roteiro"}).json()["scene"]["data"]["approved"]["roteiro"] is True
        assert (
            client.post(url, json={"stage": "roteiro", "approved": False}).json()["scene"]["data"]["approved"][
                "roteiro"
            ]
            is False
        )

    def test_escolher_o_cenario_entre_as_variacoes(
        self, client: TestClient, servicos: Servicos, elenco: list[Any], tmp_path: Path
    ) -> None:
        pid, ids = self._projeto(client, servicos, elenco)
        cena = servicos.projetos.cena(ids[0])
        assert cena is not None
        primeiro = dar_cenario(servicos, tmp_path, cena, "a")
        segundo = servicos.midias.adotar(
            tmp_path / "a-x.png" if (tmp_path / "a-x.png").exists() else _png(tmp_path / "b.png"),
            tipo="imagem",
            papel="fundo",
            dono_tipo="cena",
            dono_id=ids[0],
            seed=9,
            metadados={"quality": "alta"},
        )
        url = f"/api/projects/{pid}/scenes/{ids[0]}/choose-background"
        r = client.post(url, json={"media_id": segundo.id})
        assert r.status_code == 200
        dados = r.json()["scene"]["data"]
        assert dados["background"]["media_id"] == segundo.id and dados["background"]["quality"] == "alta"
        assert set(dados["candidates"]) == {primeiro, segundo.id} and dados["keyframe_media_id"] is not None
        assert r.json()["scene"]["keyframe"]["role"] == "quadro"
        assert client.post(url, json={"media_id": "0" * 32}).status_code == 422
        outra = servicos.midias.adotar(
            _png(tmp_path / "c.png"), tipo="imagem", papel="fundo", dono_tipo="cena", dono_id=ids[1]
        )
        assert client.post(url, json={"media_id": outra.id}).status_code == 422  # é o cenário de outra cena

    def test_layout_dos_personagens_e_recompor(
        self, client: TestClient, servicos: Servicos, elenco: list[Any], tmp_path: Path
    ) -> None:
        pid, ids = self._projeto(client, servicos, elenco)
        cena = servicos.projetos.cena(ids[0])
        assert cena is not None
        dar_cenario(servicos, tmp_path, cena)
        assert client.post(f"/api/projects/{pid}/scenes/{ids[0]}/recompose").status_code == 200
        antes = _detalhes(client, pid)["scenes"][0]["keyframe"]["id"]
        r = client.put(
            f"/api/projects/{pid}/scenes/{ids[0]}/layout",
            json={
                "items": [
                    {
                        "personagem_id": elenco[0].id,
                        "x": 0.25,
                        "base_y": 0.9,
                        "altura": 0.4,
                        "espelhar": True,
                        "pose": "lado",
                        "acao": "pular",
                    }
                ]
            },
        )
        assert r.status_code == 200
        cena_api = r.json()["scene"]
        assert (
            cena_api["layout"][0]["x"] == 0.25
            and cena_api["layout"][0]["pose"] == "lado"
            and cena_api["data"]["keyframe_media_id"] != antes
        )
        assert client.get(f"/api/media/{antes}").status_code == 404  # a imagem antiga foi trocada
        assert client.put(f"/api/projects/{pid}/scenes/{ids[0]}/layout", json={"items": [{"x": 1}]}).status_code == 422

    def test_recompor_sem_cenario(self, client: TestClient, servicos: Servicos, elenco: list[Any]) -> None:
        pid, ids = self._projeto(client, servicos, elenco)
        assert client.post(f"/api/projects/{pid}/scenes/{ids[0]}/recompose").status_code == 409


def _png(caminho: Path) -> Path:
    from PIL import Image

    Image.new("RGB", (320, 180), (100, 100, 100)).save(caminho)
    return caminho


class TestResolverPersonagens:
    def test_achados_faltando_e_de_outro_estilo(
        self, client: TestClient, servicos: Servicos, tmp_path: Path, elenco: list[Any]
    ) -> None:
        personagem_pronto(servicos, tmp_path, "Maya", estilo="3D")
        r = client.post(
            "/api/characters/resolve", json={"names": ["Lila", "bênto", "Maya", "Sol", "lila"], "style": "2D"}
        ).json()
        assert [p["name"] for p in r["found"]] == ["Lila", "Bento"] and r["missing"] == ["Sol"]
        assert [(o["name"], o["available_style"]) for o in r["other_style"]] == [("Maya", "3D")]
        assert r["found"][0]["has_cutout"] is True
        assert [
            p["name"] for p in client.post("/api/characters/resolve", json={"names": ["Maya"]}).json()["found"]
        ] == ["Maya"]
        assert client.post("/api/characters/resolve", json={"names": []}).status_code == 422


class TestFluxoCompletoPelaApi:
    def test_do_enredo_ao_video_montado_com_aprovacao_em_cada_etapa(
        self, client_com_worker: TestClient, servicos: Servicos, elenco: list[Any]
    ) -> None:
        c = client_com_worker
        pid = _criar(c)["project"]["id"]

        def rodar(caminho: str, corpo: dict[str, Any] | None = None) -> dict[str, Any]:
            r = c.post(f"/api/projects/{pid}/{caminho}", json=corpo or {})
            assert r.status_code == 202, r.text
            return _esperar_job(c, r.json()["id"])

        def aprovar(etapa: str) -> dict[str, Any]:
            r = c.post(f"/api/projects/{pid}/stages/{etapa}/approve", json={"approve_all": True})
            assert r.status_code == 200, r.text
            corpo: dict[str, Any] = r.json()
            return corpo

        aprovar("enredo")
        assert rodar("script", {"mode": "simples"})["result"]["origin"] == "simples"
        aprovar("roteiro")
        rodar("storyboard", {"quality": "rascunho"})
        d = _detalhes(c, pid)
        assert all(s["data"]["background"] and s["keyframe"] for s in d["scenes"])
        assert d["scenes"][0]["keyframe"]["thumb_url"]
        aprovar("storyboard")
        rodar("animate", {"draft": True})
        d = _detalhes(c, pid)
        assert all(s["clip_media"] and s["effective_duration_s"] >= 3 for s in d["scenes"])
        aprovar("animacao")
        rodar("audio")
        d = _detalhes(c, pid)
        assert d["files"]["mix"] and d["files"]["subtitles"] and d["files"]["music"]
        aprovar("audio")
        rodar("assemble")
        d = _detalhes(c, pid)
        assert d["files"]["final"]["role"] == "video_final" and d["project"]["stage"] == "montagem"
        assert d["stages"]["stages"][5]["ready"] is True
        d = aprovar("montagem")
        assert d["project"]["stage"] == "revisao" and d["stages"]["stages"][6]["available"] is True
        revisao = c.get(f"/api/projects/{pid}/review").json()
        estados = {i["id"]: i["status"] for i in revisao["checklist"]}
        assert (
            estados["conteudo"] == "ok"
            and estados["flashes"] == "ok"
            and estados["legendas"] == "ok"
            and estados["logo"] == "ok"
        )
        assert revisao["files"]["final"] and "conteúdo para crianças" in revisao["reminder"]
        resumo = c.get("/api/projects").json()["items"][0]
        assert resumo["has_final"] is True and resumo["thumb_url"] and resumo["scene_count"] >= 2
        assert cast(FfmpegFalso, servicos.motores.ffmpeg).renders  # os quadros foram desenhados de verdade

    def test_editar_o_cenario_depois_de_aprovar_reabre_o_storyboard(
        self, client_com_worker: TestClient, servicos: Servicos, elenco: list[Any]
    ) -> None:
        c = client_com_worker
        pid = _criar(c)["project"]["id"]
        c.post(f"/api/projects/{pid}/stages/enredo/approve", json={})
        _esperar_job(c, c.post(f"/api/projects/{pid}/script", json={"mode": "simples"}).json()["id"])
        c.post(f"/api/projects/{pid}/stages/roteiro/approve", json={"approve_all": True})
        _esperar_job(c, c.post(f"/api/projects/{pid}/storyboard", json={"quality": "rascunho"}).json()["id"])
        c.post(f"/api/projects/{pid}/stages/storyboard/approve", json={"approve_all": True})
        primeira = _detalhes(c, pid)["scenes"][0]["id"]
        r = c.patch(f"/api/projects/{pid}/scenes/{primeira}", json={"changes": {"visual": "uma praia ensolarada"}})
        aprovacoes = _detalhes(c, pid)["project"]["approvals"]
        assert r.status_code == 200 and "storyboard" not in aprovacoes and "roteiro" in aprovacoes
        cena = r.json()["scene"]["data"]
        assert cena["approved"]["storyboard"] is False and cena["approved"]["roteiro"] is False
