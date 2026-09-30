"""Personagens: biblioteca, regras de voz, rotas e jobs (variações, escolha, recorte, folha, voz de teste, 2D↔3D, envio)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.container import Servicos
from app.erros import ErroParaOUsuario
from app.midias.repositorio import Midia
from app.personagens.repositorio import NomeEmUso, RepositorioPersonagens
from app.personagens.servico import (
    PersonagemSemImagem,
    ficha_do_personagem,
    imagem_principal,
    referencias,
    voz_sugerida,
    voz_valida,
)
from app.prompts.formatos import FichaPersonagem
from app.tarefas.personagens import falar_frase_de_teste, gerar_variacoes

from .conftest import esperar
from .fakes_motores import ContextoDeTeste, FfmpegFalso, ImagemFalsa, RecorteFalso, VozFalsa

FICHA: dict[str, Any] = {
    "name": "Lila",
    "style": "2D",
    "species": "coelha",
    "appearance": "pelo lilás macio e olhos grandes",
    "clothing": "vestido amarelo",
    "voice": "aguda e calma",
}


def _png_bytes(tamanho: tuple[int, int] = (64, 64)) -> bytes:
    saida = io.BytesIO()
    Image.new("RGB", tamanho, (240, 240, 240)).save(saida, "PNG")
    return saida.getvalue()


def _criar(client: TestClient, **campos: Any) -> dict[str, Any]:
    r = client.post(
        "/api/characters", json={"form": {**FICHA, **campos}, "original_prompt": "### PERSONAGEM\nNome: Lila"}
    )
    assert r.status_code == 201, r.text
    criado: dict[str, Any] = r.json()
    return criado


def _com_imagem(
    sv: Servicos, tmp_path: Path, personagem_id: str, papel: str = "variacao", nome: str = "v.png"
) -> Midia:
    origem = tmp_path / nome
    origem.write_bytes(_png_bytes())
    return sv.midias.adotar(
        origem,
        tipo="imagem",
        papel=papel,
        dono_tipo="personagem",
        dono_id=personagem_id,
        metadados={"character_version": 1},
    )


def _com_principal(client: TestClient, sv: Servicos, tmp_path: Path, **campos: Any) -> tuple[str, Midia]:
    personagem = _criar(client, **campos)
    midia = _com_imagem(sv, tmp_path, personagem["id"])
    sv.personagens.definir_imagem_principal(personagem["id"], midia.id)
    sv.personagens.definir_estado(personagem["id"], "escolhido")
    return cast(str, personagem["id"]), midia


def _esperar_job(c: TestClient, job_id: str, estado: str = "done") -> dict[str, Any]:
    assert esperar(lambda: c.get(f"/api/jobs/{job_id}").json()["status"] == estado), c.get(f"/api/jobs/{job_id}").json()
    job: dict[str, Any] = c.get(f"/api/jobs/{job_id}").json()
    return job


def _imagem(sv: Servicos) -> ImagemFalsa:
    return cast(ImagemFalsa, sv.motores.imagem)


def _recorte(sv: Servicos) -> RecorteFalso:
    return cast(RecorteFalso, sv.motores.recorte)


def _ffmpeg(sv: Servicos) -> FfmpegFalso:
    return cast(FfmpegFalso, sv.motores.ffmpeg)


class TestRepositorio:
    @pytest.fixture
    def repo(self, servicos: Servicos) -> RepositorioPersonagens:
        return servicos.personagens

    def test_criar_e_obter(self, repo: RepositorioPersonagens) -> None:
        p = repo.criar("Lila", "2D", {"name": "Lila"}, prompt_original="texto", prompt_tecnico="tech")
        assert p.estado == "rascunho" and p.versao == 1 and p.voz["id"] == "pf_dora" and p.origem == "prompt"
        lido = repo.obter(p.id)
        assert lido == p and repo.obter("0" * 32) is None
        api = p.para_api()
        assert api["name"] == "Lila" and api["style"] == "2D" and api["main_image_url"] is None and api["version"] == 1

    def test_o_mesmo_nome_vale_nos_dois_estilos_mas_nao_repete_no_mesmo(self, repo: RepositorioPersonagens) -> None:
        repo.criar("Lila", "2D", {})
        repo.criar("lila", "3D", {})
        with pytest.raises(NomeEmUso, match="LILA"):
            repo.criar("LILA", "2D", {})
        assert repo.contar() == 2

    def test_obter_por_nome_prefere_o_estilo_pedido(self, repo: RepositorioPersonagens) -> None:
        d2 = repo.criar("Lila", "2D", {})
        d3 = repo.criar("Lila", "3D", {})
        assert repo.obter_por_nome("lila", "3D") == d3 and repo.obter_por_nome("LILA", "2D") == d2
        assert repo.obter_por_nome("Lila") is not None and repo.obter_por_nome("Bento") is None

    def test_listar_com_busca_e_filtro(self, repo: RepositorioPersonagens) -> None:
        repo.criar("Lila", "2D", {})
        repo.criar("Bento", "3D", {})
        repo.criar("100%_Bicho", "2D", {})
        assert {p.nome for p in repo.listar()} == {"Lila", "Bento", "100%_Bicho"}
        assert [p.nome for p in repo.listar(estilo="3D")] == ["Bento"]
        assert [p.nome for p in repo.listar(busca="lil")] == ["Lila"]
        assert [p.nome for p in repo.listar(busca="100%")] == ["100%_Bicho"]
        assert repo.listar(busca="%") == [p for p in repo.listar() if "%" in p.nome]
        assert repo.listar(busca="x'; DROP TABLE personagens;--") == [] and repo.contar() == 3

    def test_editar_a_ficha_sobe_a_versao(self, repo: RepositorioPersonagens) -> None:
        p = repo.criar("Lila", "2D", {"name": "Lila"}, prompt_tecnico="antigo")
        novo = repo.atualizar_ficha(p.id, {"name": "Lila", "appearance": "nova"}, nome="Lila", prompt_tecnico="novo")
        assert novo is not None and novo.versao == 2 and novo.ficha["appearance"] == "nova"
        assert novo.prompt_tecnico == "novo" and novo.atualizado_em >= p.atualizado_em
        assert repo.atualizar_ficha("0" * 32, {}, nome="X") is None

    def test_renomear_para_um_nome_que_ja_existe_e_recusado(self, repo: RepositorioPersonagens) -> None:
        repo.criar("Lila", "2D", {})
        outro = repo.criar("Bento", "2D", {})
        with pytest.raises(NomeEmUso):
            repo.atualizar_ficha(outro.id, {}, nome="lila")
        assert repo.obter(outro.id) is not None and repo.obter(outro.id).nome == "Bento"  # type: ignore[union-attr]

    def test_estado_voz_e_prompt_tecnico(self, repo: RepositorioPersonagens) -> None:
        p = repo.criar("Lila", "2D", {})
        repo.definir_estado(p.id, "escolhido")
        repo.definir_voz(p.id, {"id": "pm_alex", "speed": 1.1, "pitch": 0.9})
        repo.definir_prompt_tecnico(p.id, "novo prompt")
        atual = repo.obter(p.id)
        assert atual is not None and atual.estado == "escolhido" and atual.voz["id"] == "pm_alex"
        assert atual.prompt_tecnico == "novo prompt"
        with pytest.raises(ValueError, match="estado desconhecido"):
            repo.definir_estado(p.id, "voando")

    def test_remover(self, repo: RepositorioPersonagens) -> None:
        p = repo.criar("Lila", "2D", {})
        assert repo.remover(p.id) is True and repo.remover(p.id) is False and repo.contar() == 0


class TestVoz:
    def test_voz_valida_normaliza_e_limita(self) -> None:
        voz = voz_valida({"id": "pm_alex", "speed": "1.05", "pitch": 0.9})
        assert voz == {"id": "pm_alex", "speed": 1.05, "pitch": 0.9, "language": "pt-BR", "lang_code": "pt-br"}
        assert (
            voz_valida({"id": "bf_emma"})["language"] == "en" and voz_valida({"id": "bf_emma"})["lang_code"] == "en-gb"
        )

    @pytest.mark.parametrize(
        ("voz", "trecho"),
        [
            ({"id": "voz-inventada"}, "desconhecida"),
            ({}, "desconhecida"),
            ({"id": "pf_dora", "speed": 3}, "velocidade"),
            ({"id": "pf_dora", "pitch": 0.2}, "tom"),
            ({"id": "pf_dora", "pitch": "agudo"}, "números"),
        ],
    )
    def test_voz_invalida(self, voz: dict[str, Any], trecho: str) -> None:
        with pytest.raises(ValueError, match=trecho):
            voz_valida(voz)

    @pytest.mark.parametrize(
        ("ficha", "id_", "tom", "velocidade"),
        [
            ({"name": "Lila", "species": "coelha", "voice": "aguda e calma"}, "pf_dora", 1.15, 0.9),
            ({"name": "Bento", "species": "urso", "voice": "grave"}, "pm_alex", 0.88, 1.0),
            ({"name": "Sol", "voice": "animada, rápida"}, "pf_dora", 1.0, 1.1),
            ({"name": "Max", "species": "menino", "voice": "en-US"}, "am_adam", 1.0, 1.0),
            ({"name": "Amy", "species": "menina", "voice": "english"}, "af_heart", 1.0, 1.0),
            ({"name": "Toby", "species": "cachorro", "appearance": "menino sorridente"}, "pm_alex", 1.0, 1.0),
            ({"name": "X"}, "pf_dora", 1.0, 1.0),
        ],
    )
    def test_voz_sugerida_a_partir_da_ficha(
        self, ficha: dict[str, Any], id_: str, tom: float, velocidade: float
    ) -> None:
        voz = voz_sugerida(FichaPersonagem.model_validate(ficha))
        assert (voz["id"], voz["pitch"], voz["speed"]) == (id_, tom, velocidade)


class TestServico:
    def test_ficha_do_personagem_usa_o_nome_e_o_estilo_da_linha(self, servicos: Servicos) -> None:
        p = servicos.personagens.criar("Lila", "3D", {"name": "Outro", "style": "2D", "species": "coelha"})
        ficha = ficha_do_personagem(p)
        assert (ficha.name, ficha.style, ficha.species) == ("Lila", "3D", "coelha")

    def test_ficha_quebrada_no_banco_nao_derruba(self, servicos: Servicos) -> None:
        p = servicos.personagens.criar("Lila", "3D", {"name": "Lila", "appearance": "x" * 5000})
        ficha = ficha_do_personagem(p)
        assert ficha.name == "Lila" and ficha.style == "3D" and ficha.appearance == ""

    def test_imagem_principal(self, servicos: Servicos, tmp_path: Path) -> None:
        p = servicos.personagens.criar("Lila", "2D", {})
        with pytest.raises(PersonagemSemImagem, match="ainda não tem"):
            imagem_principal(servicos, p)
        midia = _com_imagem(servicos, tmp_path, p.id)
        servicos.personagens.definir_imagem_principal(p.id, midia.id)
        atual = servicos.personagens.obter(p.id)
        assert atual is not None and imagem_principal(servicos, atual) == servicos.midias.caminho_absoluto(midia)
        servicos.midias.caminho_absoluto(midia).unlink()
        with pytest.raises(PersonagemSemImagem, match="sumiu"):
            imagem_principal(servicos, atual)

    def test_referencias_de_varios_personagens(self, servicos: Servicos, tmp_path: Path) -> None:
        a = servicos.personagens.criar("A", "2D", {})
        b = servicos.personagens.criar("B", "2D", {})
        for p in (a, b):
            servicos.personagens.definir_imagem_principal(
                p.id, _com_imagem(servicos, tmp_path, p.id, nome=f"{p.nome}.png").id
            )
        quem, caminhos = referencias(servicos, [a.id, b.id])
        assert [p.nome for p in quem] == ["A", "B"] and len(caminhos) == 2
        with pytest.raises(PersonagemSemImagem, match="não existe"):
            referencias(servicos, ["0" * 32])


class TestCriarEListar:
    def test_cria_com_prompt_tecnico_e_voz_sugerida(self, client: TestClient) -> None:
        p = _criar(client)
        assert p["name"] == "Lila" and p["style"] == "2D" and p["state"] == "rascunho" and p["version"] == 1
        assert "flat 2D cartoon" in p["technical_prompt"] and "pelo lilás macio" in p["technical_prompt"]
        assert p["voice"]["id"] == "pf_dora" and p["voice"]["pitch"] == 1.15  # "aguda e calma"
        assert p["original_prompt"].startswith("### PERSONAGEM") and p["has_cutout"] is False
        assert p["form"]["clothing"] == "vestido amarelo" and p["cutout_slots"] == []

    def test_exige_nome_e_aparencia(self, client: TestClient) -> None:
        assert client.post("/api/characters", json={"form": {**FICHA, "name": "  "}}).status_code == 422
        r = client.post("/api/characters", json={"form": {**FICHA, "appearance": ""}})
        assert r.status_code == 422 and "aparência" in r.json()["detail"]
        assert client.post("/api/characters", json={}).status_code == 422
        assert client.post("/api/characters", json={"form": {**FICHA, "style": "aquarela"}}).status_code == 422

    def test_filtro_de_conteudo(self, client: TestClient) -> None:
        r = client.post("/api/characters", json={"form": {**FICHA, "appearance": "igual à Peppa Pig"}})
        assert r.status_code == 422 and "peppa" in r.json()["detail"]
        r = client.post("/api/characters", json={"form": FICHA, "original_prompt": "uma coelha com uma faca"})
        assert r.status_code == 422 and "Reescreva" in r.json()["detail"]
        r = client.post("/api/characters", json={"form": {**FICHA, "name": "Bluey"}})
        assert r.status_code == 422

    def test_nome_repetido_no_mesmo_estilo_devolve_o_id_do_existente(self, client: TestClient) -> None:
        primeiro = _criar(client)
        r = client.post("/api/characters", json={"form": FICHA})
        assert r.status_code == 409 and r.json()["existing_id"] == primeiro["id"] and "Lila" in r.json()["detail"]
        assert client.post("/api/characters", json={"form": {**FICHA, "style": "3D"}}).status_code == 201

    def test_o_nome_e_aparado(self, client: TestClient) -> None:
        assert _criar(client, name="  Sol  ")["name"] == "Sol"

    def test_listar_buscar_e_filtrar(self, client: TestClient) -> None:
        _criar(client)
        _criar(client, name="Bento", style="3D", species="urso", appearance="urso marrom")
        todos = client.get("/api/characters").json()
        assert todos["total"] == 2 and {p["name"] for p in todos["items"]} == {"Lila", "Bento"}
        assert [p["name"] for p in client.get("/api/characters", params={"style": "3D"}).json()["items"]] == ["Bento"]
        assert [p["name"] for p in client.get("/api/characters", params={"q": "lil"}).json()["items"]] == ["Lila"]
        assert client.get("/api/characters", params={"style": "4D"}).status_code == 422
        assert client.get("/api/characters", params={"q": "x" * 81}).status_code == 422

    def test_detalhes_vazios_e_id_invalido(self, client: TestClient) -> None:
        p = _criar(client)
        d = client.get(f"/api/characters/{p['id']}").json()
        assert (
            d["character"]["id"] == p["id"] and d["variations"] == [] and d["uploads"] == [] and d["voice_tests"] == []
        )
        assert [s["slot"] for s in d["sheet"]] == [
            "principal",
            "frente",
            "tres_quartos",
            "lado",
            "feliz",
            "triste",
            "surpreso",
            "sono",
            "bravo",
        ]
        assert all(s["image"] is None and s["cutout"] is None for s in d["sheet"]) and d["versions"] == []
        assert client.get(f"/api/characters/{'0' * 32}").status_code == 404
        assert client.get("/api/characters/nao-e-id").status_code == 422

    def test_vozes_e_estimativas(self, client: TestClient) -> None:
        vozes = client.get("/api/characters/voices").json()["voices"]
        assert {v["id"] for v in vozes["pt-BR"]} == {"pf_dora", "pm_alex", "pm_santa"} and "en" in vozes
        var = client.get("/api/characters/estimate", params={"kind": "variations", "count": 4}).json()
        assert (var["width"], var["height"]) == (512, 512) and var["total_seconds"] == pytest.approx(
            var["per_item_seconds"] * 4, abs=0.5
        )
        folha = client.get("/api/characters/estimate", params={"kind": "sheet", "count": 3}).json()
        assert folha["per_item_seconds"] > var["per_item_seconds"]  # referência custa mais e ainda há o recorte
        assert client.get("/api/characters/estimate", params={"kind": "cutout"}).json()["total_seconds"] == 30.0
        padrao = client.get("/api/characters/estimate", params={"quality": "padrao"}).json()
        assert (padrao["width"], padrao["height"]) == (768, 768)
        assert client.get("/api/characters/estimate", params={"kind": "outro"}).status_code == 422
        assert client.get("/api/characters/estimate", params={"count": 9}).status_code == 422


class TestEditarEApagar:
    def test_editar_a_ficha_sobe_a_versao_e_refaz_o_prompt_tecnico(self, client: TestClient) -> None:
        p = _criar(client)
        r = client.patch(
            f"/api/characters/{p['id']}", json={"form": {**FICHA, "appearance": "pelo azul e orelhas longas"}}
        )
        assert r.status_code == 200, r.text
        novo = r.json()
        assert (
            novo["version"] == 2
            and "pelo azul" in novo["technical_prompt"]
            and novo["form"]["appearance"].startswith("pelo azul")
        )
        assert novo["voice"] == p["voice"]  # a voz escolhida não muda com a ficha

    def test_o_estilo_nao_muda_por_aqui(self, client: TestClient) -> None:
        p = _criar(client)
        r = client.patch(f"/api/characters/{p['id']}", json={"form": {**FICHA, "style": "3D"}})
        assert r.status_code == 422 and "Criar versão 3D" in r.json()["detail"]

    def test_so_o_prompt_tecnico_nao_sobe_a_versao(self, client: TestClient) -> None:
        p = _criar(client)
        r = client.patch(f"/api/characters/{p['id']}", json={"technical_prompt": "  a purple rabbit  "})
        assert r.json()["technical_prompt"] == "a purple rabbit" and r.json()["version"] == 1

    def test_valida_conteudo_nome_e_pedido_vazio(self, client: TestClient) -> None:
        p = _criar(client)
        bloqueado = client.patch(f"/api/characters/{p['id']}", json={"form": {**FICHA, "personality": "assustadora"}})
        assert bloqueado.status_code == 422
        assert (
            client.patch(f"/api/characters/{p['id']}", json={"technical_prompt": "a scary monster"}).status_code == 422
        )
        assert client.patch(f"/api/characters/{p['id']}", json={"form": {**FICHA, "name": ""}}).status_code == 422
        assert client.patch(f"/api/characters/{p['id']}", json={}).status_code == 422
        assert client.patch(f"/api/characters/{'0' * 32}", json={"technical_prompt": "x"}).status_code == 404

    def test_renomear_para_um_nome_existente(self, client: TestClient) -> None:
        _criar(client)
        outro = _criar(client, name="Bento")
        r = client.patch(f"/api/characters/{outro['id']}", json={"form": {**FICHA, "name": "Lila"}})
        assert r.status_code == 409 and "existing_id" in r.json()

    def test_apagar_leva_as_imagens_junto(self, client: TestClient, servicos: Servicos, tmp_path: Path) -> None:
        pid, midia = _com_principal(client, servicos, tmp_path)
        arquivo = servicos.midias.caminho_absoluto(midia)
        r = client.delete(f"/api/characters/{pid}")
        assert r.json() == {"deleted": True, "media_removed": 1}
        assert not arquivo.exists() and client.get(f"/api/characters/{pid}").status_code == 404
        assert client.delete(f"/api/characters/{pid}").status_code == 404


class TestVariacoes:
    def test_pede_o_job_e_guarda_o_prompt_tecnico_editado(self, client: TestClient) -> None:
        p = _criar(client)
        r = client.post(
            f"/api/characters/{p['id']}/variations",
            json={"count": 3, "quality": "padrao", "seed": 5, "technical_prompt": "  a purple rabbit  "},
        )
        assert r.status_code == 202
        job = r.json()
        assert job["kind"] == "personagem.variacoes" and job["title"] == "Variações de Lila (3)"
        assert job["params"]["technical_prompt"] == "a purple rabbit" and job["params"]["quality"] == "padrao"
        assert client.get(f"/api/characters/{p['id']}").json()["character"]["technical_prompt"] == "a purple rabbit"

    @pytest.mark.parametrize("corpo", [{"count": 5}, {"count": 0}, {"quality": "alta"}, {"seed": -3}])
    def test_valida_o_pedido(self, client: TestClient, corpo: dict[str, Any]) -> None:
        p = _criar(client)
        assert client.post(f"/api/characters/{p['id']}/variations", json=corpo).status_code == 422

    def test_sem_motor_e_filtro_e_id(self, client: TestClient, servicos: Servicos) -> None:
        p = _criar(client)
        r = client.post(f"/api/characters/{p['id']}/variations", json={"technical_prompt": "a scary zombie"})
        assert r.status_code == 422
        servicos.motores.imagem = ImagemFalsa(indisponivel="O motor de imagens ainda não está instalado")
        assert client.post(f"/api/characters/{p['id']}/variations", json={}).status_code == 503
        assert client.post(f"/api/characters/{'0' * 32}/variations", json={}).status_code == 404

    def test_gera_quatro_variacoes_quadradas_e_marca_o_estado(
        self, client_com_worker: TestClient, servicos: Servicos
    ) -> None:
        c = client_com_worker
        p = _criar(c)
        job = _esperar_job(c, c.post(f"/api/characters/{p['id']}/variations", json={"seed": 10}).json()["id"])
        assert len(job["result"]["media_ids"]) == 4
        assert [q.seed for q in _imagem(servicos).pedidos] == [10, 10 + 7919, 10 + 2 * 7919, 10 + 3 * 7919]
        assert all((q.largura, q.altura) == (512, 512) and q.referencias == () for q in _imagem(servicos).pedidos)
        detalhes = c.get(f"/api/characters/{p['id']}").json()
        assert detalhes["character"]["state"] == "variacoes" and len(detalhes["variations"]) == 4
        v = detalhes["variations"][0]
        assert v["role"] == "variacao" and v["owner_id"] == p["id"] and v["style"] == "2D" and v["model"] == "falso"
        assert v["metadata"]["character_version"] == 1 and v["technical_prompt"] == p["technical_prompt"]
        assert v["prompt"].startswith("### PERSONAGEM")
        assert detalhes["versions"] == [{"version": 1, "images": 4}]

    def test_mais_variacoes_acumulam_sem_apagar_as_antigas(self, client_com_worker: TestClient) -> None:
        c = client_com_worker
        p = _criar(c)
        for _ in range(2):
            _esperar_job(c, c.post(f"/api/characters/{p['id']}/variations", json={"count": 2}).json()["id"])
        assert len(c.get(f"/api/characters/{p['id']}").json()["variations"]) == 4

    def test_editar_e_gerar_de_novo_guarda_as_duas_versoes(self, client_com_worker: TestClient) -> None:
        c = client_com_worker
        p = _criar(c)
        _esperar_job(c, c.post(f"/api/characters/{p['id']}/variations", json={"count": 1}).json()["id"])
        c.patch(f"/api/characters/{p['id']}", json={"form": {**FICHA, "appearance": "pelo azul"}})
        _esperar_job(c, c.post(f"/api/characters/{p['id']}/variations", json={"count": 2}).json()["id"])
        assert c.get(f"/api/characters/{p['id']}").json()["versions"] == [
            {"version": 2, "images": 2},
            {"version": 1, "images": 1},
        ]

    def test_o_job_confere_o_filtro_de_novo(self, servicos: Servicos) -> None:
        p = servicos.personagens.criar("Lila", "2D", {"name": "Lila", "appearance": "igual ao Mickey"})
        with pytest.raises(ErroParaOUsuario, match="mickey"):
            gerar_variacoes(ContextoDeTeste(servicos=servicos), {"character_id": p.id})
        assert _imagem(servicos).pedidos == []

    def test_personagem_apagado_antes_do_job(self, servicos: Servicos) -> None:
        with pytest.raises(ErroParaOUsuario, match="não existe mais"):
            gerar_variacoes(ContextoDeTeste(servicos=servicos), {"character_id": "0" * 32})
        with pytest.raises(ErroParaOUsuario, match="incompleto"):
            gerar_variacoes(ContextoDeTeste(servicos=servicos), {"character_id": "x"})


class TestEscolherERecortar:
    def test_escolher_define_a_principal_e_pede_o_recorte(
        self, client_com_worker: TestClient, servicos: Servicos, tmp_path: Path
    ) -> None:
        c = client_com_worker
        p = _criar(c)
        midia = _com_imagem(servicos, tmp_path, p["id"])
        r = c.post(f"/api/characters/{p['id']}/choose", json={"media_id": midia.id})
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["character"]["state"] == "escolhido" and corpo["character"]["main_image_id"] == midia.id
        assert corpo["character"]["main_image_url"] == f"/api/media/{midia.id}/thumb"
        job = _esperar_job(c, corpo["job"]["id"])
        assert job["kind"] == "personagem.recortar" and job["params"]["slot"] == "principal"
        recorte = servicos.midias.obter(job["result"]["media_id"])
        assert recorte is not None and recorte.papel == "recorte" and recorte.pai_id == midia.id
        assert recorte.metadados["slot"] == "principal" and recorte.dono_id == p["id"]
        with Image.open(servicos.midias.caminho_absoluto(recorte)) as arquivo:
            assert "A" in arquivo.getbands()  # PNG transparente
        atual = c.get(f"/api/characters/{p['id']}").json()
        assert atual["character"]["has_cutout"] and atual["character"]["cutout_slots"] == ["principal"]
        assert atual["sheet"][0]["cutout"]["id"] == recorte.id and atual["sheet"][0]["image"]["id"] == midia.id

    def test_escolher_de_novo_a_mesma_imagem_nao_repete_o_recorte(
        self, client_com_worker: TestClient, servicos: Servicos, tmp_path: Path
    ) -> None:
        c = client_com_worker
        p = _criar(c)
        midia = _com_imagem(servicos, tmp_path, p["id"])
        _esperar_job(c, c.post(f"/api/characters/{p['id']}/choose", json={"media_id": midia.id}).json()["job"]["id"])
        assert c.post(f"/api/characters/{p['id']}/choose", json={"media_id": midia.id}).json()["job"] is None

    def test_so_vale_imagem_deste_personagem(self, client: TestClient, servicos: Servicos, tmp_path: Path) -> None:
        a, b = _criar(client), _criar(client, name="Bento")
        de_b = _com_imagem(servicos, tmp_path, b["id"])
        assert client.post(f"/api/characters/{a['id']}/choose", json={"media_id": de_b.id}).status_code == 422
        assert client.post(f"/api/characters/{a['id']}/choose", json={"media_id": "0" * 32}).status_code == 422
        pose = _com_imagem(servicos, tmp_path, a["id"], papel="pose", nome="pose.png")
        assert client.post(f"/api/characters/{a['id']}/choose", json={"media_id": pose.id}).status_code == 422
        assert client.post(f"/api/characters/{a['id']}/choose", json={"media_id": "x"}).status_code == 422

    def test_sem_motor_de_recorte_escolher_ainda_funciona(
        self, client: TestClient, servicos: Servicos, tmp_path: Path
    ) -> None:
        servicos.motores.recorte = RecorteFalso(indisponivel="O recorte de fundo ainda não está instalado")
        p = _criar(client)
        midia = _com_imagem(servicos, tmp_path, p["id"])
        r = client.post(f"/api/characters/{p['id']}/choose", json={"media_id": midia.id})
        assert r.status_code == 200 and r.json()["job"] is None and r.json()["character"]["state"] == "escolhido"


class TestFolhaDeReferencia:
    def test_gera_poses_e_expressoes_com_recorte_de_cada_uma(
        self, client_com_worker: TestClient, servicos: Servicos, tmp_path: Path
    ) -> None:
        c = client_com_worker
        pid, principal = _com_principal(c, servicos, tmp_path)
        r = c.post(f"/api/characters/{pid}/sheet", json={"slots": ["frente", "feliz"], "seed": 3})
        assert r.status_code == 202 and r.json()["title"] == "Folha de referência de Lila (2)"
        job = _esperar_job(c, r.json()["id"])
        assert job["progress"] == 1.0 and job["result"]["slots"] == ["frente", "feliz"]
        assert len(job["result"]["media_ids"]) == 5  # recorte da principal + 2 poses + 2 recortes
        pedidos = _imagem(servicos).pedidos
        assert len(pedidos) == 2 and all(
            q.referencias == (servicos.midias.caminho_absoluto(principal),) for q in pedidos
        )
        assert "front view" in pedidos[0].prompt and "happy smile" in pedidos[1].prompt
        assert all("reference image" in q.prompt and "exactly the same design" in q.prompt for q in pedidos)
        assert (pedidos[0].largura, pedidos[0].altura) == (512, 512)
        assert len(_recorte(servicos).origens) == 3
        detalhes = c.get(f"/api/characters/{pid}").json()
        assert detalhes["character"]["state"] == "pronto"
        assert detalhes["character"]["cutout_slots"] == ["principal", "frente", "feliz"]
        por_slot = {s["slot"]: s for s in detalhes["sheet"]}
        assert por_slot["frente"]["image"]["role"] == "pose" and por_slot["frente"]["cutout"]["role"] == "recorte"
        assert por_slot["feliz"]["cutout"]["parent_id"] == por_slot["feliz"]["image"]["id"]
        assert por_slot["lado"]["image"] is None and por_slot["triste"]["cutout"] is None
        assert por_slot["frente"]["image"]["metadata"]["slot"] == "frente"

    def test_cada_recorte_sabe_para_onde_olha(
        self, client_com_worker: TestClient, servicos: Servicos, tmp_path: Path
    ) -> None:
        c = client_com_worker
        pid, _ = _com_principal(c, servicos, tmp_path)
        _esperar_job(
            c,
            c.post(f"/api/characters/{pid}/sheet", json={"slots": ["frente", "tres_quartos", "lado", "feliz"]}).json()[
                "id"
            ],
        )
        por_slot = {s["slot"]: s for s in c.get(f"/api/characters/{pid}").json()["sheet"]}
        olhar = {
            slot: por_slot[slot]["cutout"]["metadata"]["facing"]
            for slot in ("principal", "frente", "tres_quartos", "lado", "feliz")
        }
        assert olhar == {
            "principal": "front",
            "frente": "front",
            "tres_quartos": "right",
            "lado": "right",
            "feliz": "front",
        }
        # o prompt das poses de lado pede que o personagem olhe para a direita (a animação parte disso)
        pedidos = _imagem(servicos).pedidos
        assert "facing right" in pedidos[1].prompt and "facing right" in pedidos[2].prompt
        assert "facing right" not in pedidos[0].prompt

    def test_corrigir_para_onde_o_recorte_olha(
        self, client_com_worker: TestClient, servicos: Servicos, tmp_path: Path
    ) -> None:
        c = client_com_worker
        pid, _ = _com_principal(c, servicos, tmp_path)
        _esperar_job(c, c.post(f"/api/characters/{pid}/sheet", json={"slots": ["lado"]}).json()["id"])
        lado = next(s for s in c.get(f"/api/characters/{pid}").json()["sheet"] if s["slot"] == "lado")
        recorte_id = lado["cutout"]["id"]
        r = c.put(f"/api/characters/{pid}/cutouts/{recorte_id}/facing", json={"facing": "left"})
        assert r.status_code == 200 and r.json()["metadata"]["facing"] == "left"
        assert r.json()["metadata"]["slot"] == "lado"  # os outros metadados continuam
        assert servicos.midias.obter(recorte_id).metadados["facing"] == "left"  # type: ignore[union-attr]
        assert c.put(f"/api/characters/{pid}/cutouts/{recorte_id}/facing", json={"facing": "cima"}).status_code == 422
        # só vale para recortes deste personagem: a imagem da pose e uma mídia de outro personagem dão 404
        pose_id = lado["image"]["id"]
        assert c.put(f"/api/characters/{pid}/cutouts/{pose_id}/facing", json={"facing": "right"}).status_code == 404
        outro = _criar(c, name="Bento")
        assert (
            c.put(f"/api/characters/{outro['id']}/cutouts/{recorte_id}/facing", json={"facing": "right"}).status_code
            == 404
        )
        assert c.put(f"/api/characters/{pid}/cutouts/{'0' * 32}/facing", json={"facing": "right"}).status_code == 404

    def test_uma_segunda_folha_nao_recorta_a_principal_de_novo_e_guarda_as_antigas(
        self, client_com_worker: TestClient, servicos: Servicos, tmp_path: Path
    ) -> None:
        c = client_com_worker
        pid, _ = _com_principal(c, servicos, tmp_path)
        for _ in range(2):
            _esperar_job(c, c.post(f"/api/characters/{pid}/sheet", json={"slots": ["lado"]}).json()["id"])
        assert len(_recorte(servicos).origens) == 3  # principal (1x) + lado (2x)
        poses = servicos.midias.listar(papeis=("pose",), dono_tipo="personagem", dono_id=pid)
        assert len(poses) == 2  # a pose refeita não sobrescreve a anterior
        detalhes = c.get(f"/api/characters/{pid}").json()
        assert (
            next(s for s in detalhes["sheet"] if s["slot"] == "lado")["image"]["id"] == poses[0].id
        )  # a mais nova vale

    def test_valida_o_pedido(self, client: TestClient, servicos: Servicos, tmp_path: Path) -> None:
        sem = _criar(client)
        r = client.post(f"/api/characters/{sem['id']}/sheet", json={})
        assert r.status_code == 422 and "Escolha uma das variações" in r.json()["detail"]
        pid, _ = _com_principal(client, servicos, tmp_path, name="Bento")
        for corpo in ({"slots": []}, {"slots": ["moonwalk"]}, {"slots": ["frente"] * 20}, {"quality": "alta"}):
            assert client.post(f"/api/characters/{pid}/sheet", json=corpo).status_code == 422
        assert client.post(f"/api/characters/{pid}/sheet", json={"slots": ["lado", "lado"]}).json()["params"][
            "slots"
        ] == ["lado"]
        assert client.post(f"/api/characters/{pid}/sheet", json={}).json()["params"]["slots"] == [
            "frente",
            "tres_quartos",
            "lado",
        ]

    def test_precisa_do_motor_de_imagem_e_do_recorte(
        self, client: TestClient, servicos: Servicos, tmp_path: Path
    ) -> None:
        pid, _ = _com_principal(client, servicos, tmp_path)
        servicos.motores.recorte = RecorteFalso(indisponivel="O recorte de fundo ainda não está instalado")
        r = client.post(f"/api/characters/{pid}/sheet", json={})
        assert r.status_code == 503 and "recorte" in r.json()["detail"]

    def test_falha_no_meio_mostra_a_mensagem_e_guarda_o_que_saiu(
        self, client_com_worker: TestClient, servicos: Servicos, tmp_path: Path
    ) -> None:
        c = client_com_worker
        pid, _ = _com_principal(c, servicos, tmp_path)
        servicos.motores.recorte = RecorteFalso(indisponivel="O recorte de fundo ainda não está instalado")
        job = enfileirar_folha(servicos, pid)
        resultado = _esperar_job(c, job, "failed")
        assert resultado["error"] == "O recorte de fundo ainda não está instalado"
        assert _imagem(servicos).pedidos == []


def enfileirar_folha(sv: Servicos, personagem_id: str) -> str:
    from app.jobs.servico import enfileirar

    return enfileirar(sv, "personagem.folha", {"character_id": personagem_id, "slots": ["frente"]}).id


class TestVozDoPersonagem:
    def test_definir_a_voz(self, client: TestClient) -> None:
        p = _criar(client)
        r = client.put(f"/api/characters/{p['id']}/voice", json={"id": "pm_santa", "speed": 0.9, "pitch": 0.85})
        assert r.status_code == 200 and r.json()["voice"] == {
            "id": "pm_santa",
            "speed": 0.9,
            "pitch": 0.85,
            "language": "pt-BR",
            "lang_code": "pt-br",
        }
        assert client.put(f"/api/characters/{p['id']}/voice", json={"id": "voz-x"}).status_code == 422
        assert client.put(f"/api/characters/{p['id']}/voice", json={"id": "pf_dora", "speed": 9}).status_code == 422
        assert client.put(f"/api/characters/{'0' * 32}/voice", json={"id": "pf_dora"}).status_code == 404
        assert client.get(f"/api/characters/{p['id']}").json()["character"]["voice"]["id"] == "pm_santa"

    def test_a_frase_de_teste_vira_audio_com_o_tom_ajustado(
        self, client_com_worker: TestClient, servicos: Servicos
    ) -> None:
        c = client_com_worker
        p = _criar(c)  # voz sugerida: aguda (1.15)
        r = c.post(f"/api/characters/{p['id']}/voice-test", json={"text": "Olá, eu sou a Lila!"})
        assert r.status_code == 202 and r.json()["title"] == "Voz de Lila"
        job = _esperar_job(c, r.json()["id"])
        midia = servicos.midias.obter(job["result"]["media_id"])
        assert midia is not None and midia.tipo == "audio" and midia.papel == "voz_teste" and midia.dono_id == p["id"]
        assert midia.prompt == "Olá, eu sou a Lila!" and midia.duracao_s == pytest.approx(0.95)
        voz = cast(VozFalsa, servicos.motores.voz).itens[0]
        assert (voz.voz, voz.lingua, voz.velocidade) == ("pf_dora", "pt-br", 0.9)  # "aguda e calma"
        comando = _ffmpeg(servicos).execucoes[0]
        assert "rubberband=pitch=1.1500" in comando and comando[-1].endswith(".wav")
        assert list(servicos.settings.temp_dir.glob("fala-*")) == []  # o áudio bruto não sobra
        assert c.get(f"/api/characters/{p['id']}").json()["voice_tests"][0]["id"] == midia.id

    def test_voz_sem_ajuste_de_tom_nao_chama_o_ffmpeg(self, client_com_worker: TestClient, servicos: Servicos) -> None:
        c = client_com_worker
        p = _criar(c, voice="")
        _esperar_job(c, c.post(f"/api/characters/{p['id']}/voice-test", json={"text": "Oi!"}).json()["id"])
        assert _ffmpeg(servicos).execucoes == []

    def test_da_para_testar_uma_voz_ainda_nao_salva(self, client_com_worker: TestClient, servicos: Servicos) -> None:
        c = client_com_worker
        p = _criar(c)
        job = c.post(
            f"/api/characters/{p['id']}/voice-test",
            json={"text": "Hello!", "voice": {"id": "am_adam", "speed": 1.2, "pitch": 0.8}},
        ).json()
        _esperar_job(c, job["id"])
        voz = cast(VozFalsa, servicos.motores.voz).itens[0]
        assert (voz.voz, voz.lingua, voz.velocidade) == ("am_adam", "en-us", 1.2)
        assert "rubberband=pitch=0.8000" in _ffmpeg(servicos).execucoes[0]
        assert c.get(f"/api/characters/{p['id']}").json()["character"]["voice"]["id"] == "pf_dora"  # não salvou

    def test_valida_o_pedido(self, client: TestClient, servicos: Servicos) -> None:
        p = _criar(client)
        url = f"/api/characters/{p['id']}/voice-test"
        assert client.post(url, json={"text": ""}).status_code == 422
        assert client.post(url, json={"text": "x" * 301}).status_code == 422
        assert client.post(url, json={"text": "uma cena de terror"}).status_code == 422
        assert client.post(url, json={"text": "oi", "voice": {"id": "voz-x"}}).status_code == 422
        servicos.motores.ffmpeg = FfmpegFalso(indisponivel="O ffmpeg ainda não está instalado")
        assert client.post(url, json={"text": "oi"}).status_code == 503
        servicos.motores.ffmpeg = FfmpegFalso()
        servicos.motores.voz = VozFalsa(indisponivel="A voz ainda não está instalada")
        assert client.post(url, json={"text": "oi"}).status_code == 503

    def test_o_job_confere_o_filtro_e_a_voz(self, servicos: Servicos) -> None:
        p = servicos.personagens.criar("Lila", "2D", {"name": "Lila"})
        with pytest.raises(ErroParaOUsuario, match="Reescreva"):
            falar_frase_de_teste(ContextoDeTeste(servicos=servicos), {"character_id": p.id, "text": "sangue e terror"})
        with pytest.raises(ErroParaOUsuario, match="desconhecida"):
            falar_frase_de_teste(
                ContextoDeTeste(servicos=servicos), {"character_id": p.id, "text": "oi", "voice": {"id": "x"}}
            )


class TestConverter2D3D:
    def test_cria_a_versao_no_outro_estilo_a_partir_da_imagem_principal(
        self, client_com_worker: TestClient, servicos: Servicos, tmp_path: Path
    ) -> None:
        c = client_com_worker
        pid, principal = _com_principal(c, servicos, tmp_path)
        r = c.post(f"/api/characters/{pid}/convert", json={"count": 2})
        assert r.status_code == 201
        novo = r.json()["character"]
        assert (
            novo["style"] == "3D"
            and novo["name"] == "Lila"
            and novo["origin"] == "conversao"
            and novo["origin_id"] == pid
        )
        assert novo["form"]["style"] == "3D" and "3D animated" in novo["technical_prompt"]
        assert novo["voice"]["id"] == "pf_dora" and novo["id"] != pid
        job = _esperar_job(c, r.json()["job"]["id"])
        assert len(job["result"]["media_ids"]) == 2
        for pedido in _imagem(servicos).pedidos:
            assert pedido.referencias == (servicos.midias.caminho_absoluto(principal),)
            assert "redrawn in a different art style" in pedido.prompt
        variacao = c.get(f"/api/characters/{novo['id']}").json()["variations"][0]
        assert variacao["parent_id"] == principal.id and variacao["style"] == "3D"
        assert variacao["metadata"]["from_reference"] is True
        # o original continua intacto
        assert c.get(f"/api/characters/{pid}").json()["character"]["main_image_id"] == principal.id

    def test_e_de_volta_para_2d(self, client: TestClient, servicos: Servicos, tmp_path: Path) -> None:
        pid, _ = _com_principal(client, servicos, tmp_path, style="3D")
        assert client.post(f"/api/characters/{pid}/convert", json={}).json()["character"]["style"] == "2D"

    def test_nao_cria_de_novo_se_a_outra_versao_ja_existe(
        self, client: TestClient, servicos: Servicos, tmp_path: Path
    ) -> None:
        pid, _ = _com_principal(client, servicos, tmp_path)
        primeira = client.post(f"/api/characters/{pid}/convert", json={}).json()["character"]
        r = client.post(f"/api/characters/{pid}/convert", json={})
        assert r.status_code == 409 and r.json()["existing_id"] == primeira["id"] and "3D" in r.json()["detail"]
        assert client.get("/api/characters").json()["total"] == 2

    def test_precisa_da_imagem_principal_e_do_motor(
        self, client: TestClient, servicos: Servicos, tmp_path: Path
    ) -> None:
        sem = _criar(client)
        assert client.post(f"/api/characters/{sem['id']}/convert", json={}).status_code == 422
        pid, _ = _com_principal(client, servicos, tmp_path, name="Bento")
        servicos.motores.imagem = ImagemFalsa(indisponivel="O motor de imagens ainda não está instalado")
        assert client.post(f"/api/characters/{pid}/convert", json={}).status_code == 503
        assert client.get("/api/characters").json()["total"] == 2  # não criou meio personagem

    def test_valida_o_pedido(self, client: TestClient, servicos: Servicos, tmp_path: Path) -> None:
        pid, _ = _com_principal(client, servicos, tmp_path)
        assert client.post(f"/api/characters/{pid}/convert", json={"count": 9}).status_code == 422
        assert client.post(f"/api/characters/{pid}/convert", json={"quality": "alta"}).status_code == 422


class TestEnviarImagemDoPersonagem:
    def _enviar(self, client: TestClient, dados: bytes, **params: Any) -> Any:
        base = {"name": "Toby", "style": "2D", "rights": "true", "file_name": "toby.png"}
        return client.post("/api/characters/upload", params={**base, **params}, content=dados)

    def test_cadastra_a_partir_da_imagem_e_recorta(self, client_com_worker: TestClient, servicos: Servicos) -> None:
        c = client_com_worker
        r = self._enviar(c, _png_bytes((80, 60)), style="3D")
        assert r.status_code == 201
        personagem, job = r.json()["character"], r.json()["job"]
        assert personagem["name"] == "Toby" and personagem["style"] == "3D" and personagem["origin"] == "upload"
        assert personagem["state"] == "escolhido" and personagem["main_image_id"]
        midia = servicos.midias.obter(personagem["main_image_id"])
        assert midia is not None and midia.papel == "upload" and midia.dono_id == personagem["id"]
        assert midia.metadados["rights_confirmed"] is True and (midia.largura, midia.altura) == (80, 60)
        _esperar_job(c, job["id"])
        assert c.get(f"/api/characters/{personagem['id']}").json()["character"]["cutout_slots"] == ["principal"]
        assert c.get(f"/api/characters/{personagem['id']}").json()["uploads"][0]["id"] == midia.id

    def test_exige_a_confirmacao_do_direito_de_uso(self, client: TestClient) -> None:
        r = self._enviar(client, _png_bytes(), rights="false")
        assert r.status_code == 422 and "direito" in r.json()["detail"]
        assert client.post("/api/characters/upload", params={"name": "Toby"}, content=_png_bytes()).status_code == 422
        assert client.get("/api/characters").json()["total"] == 0

    def test_recusa_imagem_falsa_ou_grande_e_nao_cria_personagem(self, client: TestClient, servicos: Servicos) -> None:
        assert self._enviar(client, b"MZ programa").status_code == 422
        assert self._enviar(client, _png_bytes(), file_name="toby.jpg").status_code == 422  # extensão que mente
        grande = b"\x89PNG\r\n\x1a\n" + b"0" * (15 * 1024 * 1024 + 1)
        assert self._enviar(client, grande).status_code == 413
        assert client.get("/api/characters").json()["total"] == 0 and servicos.midias.contar() == 0
        assert list(servicos.settings.temp_dir.glob("envio-*")) == []

    def test_filtro_no_nome_e_nome_repetido(self, client: TestClient, servicos: Servicos) -> None:
        assert self._enviar(client, _png_bytes(), name="Peppa").status_code == 422
        primeiro = self._enviar(client, _png_bytes()).json()["character"]
        r = self._enviar(client, _png_bytes())
        assert r.status_code == 409 and r.json()["existing_id"] == primeiro["id"]
        assert servicos.midias.contar() == 1  # a segunda imagem não ficou solta na biblioteca
        assert list(servicos.settings.temp_dir.glob("envio-*")) == []

    def test_sem_motor_de_recorte_cadastra_mesmo_assim(self, client: TestClient, servicos: Servicos) -> None:
        servicos.motores.recorte = RecorteFalso(indisponivel="O recorte de fundo ainda não está instalado")
        r = self._enviar(client, _png_bytes())
        assert r.status_code == 201 and r.json()["job"] is None

    def test_outro_site_nao_consegue_enviar(self, client: TestClient) -> None:
        r = client.post(
            "/api/characters/upload",
            params={"name": "Toby", "rights": "true"},
            content=_png_bytes(),
            headers={"Origin": "http://site-malicioso.example"},
        )
        assert r.status_code == 403
