"""Clipes: filtros do ffmpeg, clipe rápido, enviar vídeo, unir, outra resolução e continuar a partir de um vídeo."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.animacao.render import CamadaDeRender, CenaDeRender, renderizar_cena
from app.clipes.filtros import (
    argumentos_de_normalizacao,
    argumentos_de_reenquadrar,
    argumentos_de_uniao_com_transicao,
    argumentos_de_uniao_em_corte,
    filtro_de_reenquadrar,
    filtro_de_uniao_com_transicao,
    tamanho_do_preset,
)
from app.container import Servicos
from app.motores.ffmpeg import Ffmpeg
from app.tarefas.clipes import gerar_clipe_rapido, interpretar_acao

from .builders_projetos import personagem_pronto, png_de_personagem, projeto_com_cenas
from .conftest import esperar
from .fakes_motores import ContextoDeTeste, ContextoReal, FfmpegFalso, ImagemFalsa, TextoFalso

pytestmark = pytest.mark.usefixtures("resolucoes_pequenas")


def _esperar_job(c: TestClient, job_id: str, estado: str = "done") -> dict[str, Any]:
    assert esperar(lambda: c.get(f"/api/jobs/{job_id}").json()["status"] == estado, timeout=90, passo=0.2), c.get(
        f"/api/jobs/{job_id}"
    ).json()
    job: dict[str, Any] = c.get(f"/api/jobs/{job_id}").json()
    return job


class TestFiltros:
    def test_tamanhos_dos_presets(self) -> None:
        assert tamanho_do_preset("9:16") == (1080, 1920) and tamanho_do_preset("16:9") == (1920, 1080)
        assert tamanho_do_preset("1:1") == (1080, 1080)
        assert tamanho_do_preset("720p", (1920, 1080)) == (1280, 720)
        assert tamanho_do_preset("720p", (1080, 1920)) == (720, 1280)  # vertical: 720 de largura
        assert tamanho_do_preset("720p", (1080, 1080)) == (720, 720)
        assert tamanho_do_preset("720p") == (1280, 720)

    def test_reenquadrar_com_fundo_desfocado(self) -> None:
        filtro = filtro_de_reenquadrar(1080, 1920)
        assert "split=2[fundo][frente]" in filtro and "boxblur=luma_radius=27" in filtro
        assert "force_original_aspect_ratio=increase,crop=1080:1920" in filtro
        assert "force_original_aspect_ratio=decrease" in filtro and filtro.endswith("format=yuv420p[saida]")
        assert "overlay=(W-w)/2:(H-h)/2" in filtro

    def test_reenquadrar_cortando_centrado_nos_personagens(self) -> None:
        filtro = filtro_de_reenquadrar(1080, 1920, "crop", foco_x=0.25)
        assert "crop=1080:1920:x='max(0,min(iw-1080,iw*0.250-1080/2))'" in filtro and "boxblur" not in filtro

    def test_argumentos_de_reenquadrar(self, tmp_path: Path) -> None:
        com = [str(a) for a in argumentos_de_reenquadrar(tmp_path / "a.mp4", tmp_path / "b.mp4", 1280, 720)]
        assert com[0] == "-i" and "0:a:0" in com and "aac" in com and com[-1].endswith("b.mp4") and "-an" not in com
        sem = [
            str(a)
            for a in argumentos_de_reenquadrar(tmp_path / "a.mp4", tmp_path / "b.mp4", 1280, 720, tem_audio=False)
        ]
        assert "-an" in sem and "0:a:0" not in sem

    def test_normalizar_com_e_sem_audio(self, tmp_path: Path) -> None:
        com = [
            str(a)
            for a in argumentos_de_normalizacao(
                tmp_path / "a.mp4", tmp_path / "n.mp4", 640, 360, tem_audio=True, duracao_s=3
            )
        ]
        assert (
            "[audio]" in com[com.index("-filter_complex") + 1]
            and "aresample=44100" in com[com.index("-filter_complex") + 1]
        )
        sem = [
            str(a)
            for a in argumentos_de_normalizacao(
                tmp_path / "a.mp4", tmp_path / "n.mp4", 640, 360, tem_audio=False, duracao_s=2.5
            )
        ]
        assert "anullsrc=r=44100:cl=stereo" in sem and "2.500" in sem and "-shortest" in sem and "1:a:0" in sem

    def test_uniao_com_transicao_encadeia_video_e_audio(self) -> None:
        filtro = filtro_de_uniao_com_transicao([4.0, 4.0, 4.0], "fade", 0.5, "loudnorm=I=-14")
        assert filtro == (
            "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=3.500[v1];[0:a][1:a]acrossfade=d=0.5[a1];"
            "[v1][2:v]xfade=transition=fade:duration=0.5:offset=7.000[saida];[a1][2:a]acrossfade=d=0.5[audio_cru];"
            "[audio_cru]loudnorm=I=-14[audio]"
        )
        assert (
            filtro_de_uniao_com_transicao([4.0], "fade", 0.5, "loudnorm=I=-14")
            == "[0:v]null[saida];[0:a]loudnorm=I=-14[audio]"
        )

    def test_argumentos_da_uniao(self, tmp_path: Path) -> None:
        clipes = [tmp_path / f"{i}.mp4" for i in range(3)]
        com = [
            str(a)
            for a in argumentos_de_uniao_com_transicao(clipes, [2.0, 2.0, 2.0], "suave", tmp_path / "s.mp4", None)
        ]
        assert com.count("-i") == 3 and "[audio]" in com and "dissolve" in com[com.index("-filter_complex") + 1]
        corte = [str(a) for a in argumentos_de_uniao_em_corte(tmp_path / "l.txt", tmp_path / "s.mp4", None)]
        assert (
            corte[corte.index("-c:v") + 1] == "copy"
            and any(a.startswith("loudnorm") for a in corte)
            and "concat" in corte
        )


@pytest.fixture
def lila(servicos: Servicos, tmp_path: Path) -> Any:
    return personagem_pronto(servicos, tmp_path, "Lila", species="coelha")


def _texto(sv: Servicos) -> TextoFalso:
    return cast(TextoFalso, sv.motores.texto)


def _ffmpeg(sv: Servicos) -> FfmpegFalso:
    return cast(FfmpegFalso, sv.motores.ffmpeg)


class TestInterpretarAcao:
    def test_o_modelo_local_devolve_cenario_movimento_emocao_e_efeitos(self, servicos: Servicos, lila: Any) -> None:
        _texto(servicos).respostas.append(
            {
                "background": "uma poça de água na grama depois da chuva",
                "animation": "pular",
                "emotion": "feliz",
                "sfx": ["splash"],
            }
        )
        plano = interpretar_acao(ContextoDeTeste(servicos=servicos), lila, "a Lila pula na poça")
        assert plano == {
            "background": "uma poça de água na grama depois da chuva",
            "animation": "pular",
            "emotion": "feliz",
            "sfx": ["splash"],
        }
        chamada = _texto(servicos).chamadas[0]
        assert (
            chamada["dados"] == "a Lila pula na poça"
            and "coelha" in chamada["instrucao"]
            and "ignore-as" in chamada["sistema"]
        )

    def test_o_cenario_do_modelo_perde_o_nome_e_a_especie_do_personagem(self, servicos: Servicos, lila: Any) -> None:
        _texto(servicos).respostas.append(
            {"background": "a coelha Lila pulando numa poça", "animation": "pular", "emotion": "feliz"}
        )
        plano = interpretar_acao(ContextoDeTeste(servicos=servicos), lila, "a Lila pula na poça")
        assert (
            "Lila" not in plano["background"] and "coelha" not in plano["background"] and "poça" in plano["background"]
        )

    def test_sem_o_modelo_usa_palavras_chave(self, servicos: Servicos, lila: Any) -> None:
        servicos.motores.texto = TextoFalso(indisponivel="O Ollama não está no ar")
        ctx = ContextoDeTeste(servicos=servicos)
        plano = interpretar_acao(ctx, lila, "a coelha Lila pula na poça de água")
        assert (
            plano["animation"] == "pular"
            and plano["emotion"] == "feliz"
            and "Lila" not in plano["background"]
            and "poça" in plano["background"]
        )
        assert any("palavras-chave" in msg for _, msg in ctx.logs)

    def test_valores_invalidos_do_modelo_caem_nas_palavras_chave(self, servicos: Servicos, lila: Any) -> None:
        _texto(servicos).respostas.append(
            {"background": "", "animation": "voar-de-moto", "emotion": "furioso", "sfx": []}
        )
        plano = interpretar_acao(ContextoDeTeste(servicos=servicos), lila, "Lila dança no jardim")
        assert plano["animation"] == "dancar" and plano["emotion"] == "feliz" and plano["background"] == "no jardim"

    def test_modelo_que_falha_no_meio_nao_derruba(self, servicos: Servicos, lila: Any) -> None:
        # TextoFalso sem resposta pronta levanta MotorFalhou
        plano = interpretar_acao(ContextoDeTeste(servicos=servicos), lila, "Lila anda no parque")
        assert plano["animation"] == "andar"


class TestClipeRapido:
    def test_gera_cenario_anima_o_personagem_e_guarda_o_clipe(self, servicos: Servicos, lila: Any) -> None:
        _texto(servicos).respostas.append(
            {
                "background": "uma poça de água na grama",
                "animation": "pular",
                "emotion": "surpreso",
                "sfx": ["splash", "boing"],
            }
        )
        params = {
            "character_id": lila.id,
            "prompt": "Lila pula na poça",
            "duration_s": 4,
            "format": "9:16",
            "quality": "rascunho",
            "seed": 12,
        }
        r = gerar_clipe_rapido(ContextoDeTeste(servicos=servicos), params)
        clipe = servicos.midias.obter(r["media_id"])
        assert (
            clipe is not None
            and clipe.papel == "clipe_rapido"
            and clipe.tipo == "video"
            and clipe.pai_id == r["background_media_id"]
        )
        assert (clipe.largura, clipe.altura, clipe.duracao_s) == (90, 160, 4.0) and clipe.prompt == "Lila pula na poça"
        assert (
            clipe.metadados["animation"] == "pular"
            and clipe.metadados["emotion"] == "surpreso"
            and clipe.metadados["character_id"] == lila.id
        )
        assert clipe.metadados["layout"][0]["personagem_id"] == lila.id and clipe.metadados["format"] == "9:16"
        fundo = servicos.midias.obter(r["background_media_id"])
        assert (
            fundo is not None and fundo.papel == "fundo_clipe" and fundo.seed == 12 and "poça" in (fundo.prompt or "")
        )
        pedido = cast(ImagemFalsa, servicos.motores.imagem).pedidos[0]
        assert (
            (pedido.largura, pedido.altura) == (352, 640)
            and "Lila" not in pedido.prompt
            and "No characters" in pedido.prompt
        )
        render = _ffmpeg(servicos).renders[0]
        assert (render["largura"], render["altura"], render["quadros"], render["fps"]) == (90, 160, 96, 24)
        mux = _ffmpeg(servicos).execucoes[-1]
        assert (
            "-c:v" in mux and "copy" in mux and "-shortest" in mux and mux.count("-i") == 2
        )  # o vídeo desenhado e a trilha

    def test_formato_horizontal_e_qualidade_padrao(self, servicos: Servicos, lila: Any) -> None:
        params = {"character_id": lila.id, "prompt": "Lila anda no parque", "format": "16:9", "quality": "padrao"}
        gerar_clipe_rapido(ContextoDeTeste(servicos=servicos), params)
        pedido = cast(ImagemFalsa, servicos.motores.imagem).pedidos[0]
        assert (pedido.largura, pedido.altura) == (768, 432)
        assert (_ffmpeg(servicos).renders[0]["largura"], _ffmpeg(servicos).renders[0]["altura"]) == (160, 90)

    def test_confere_o_filtro_de_conteudo_no_pedido_e_no_cenario(self, servicos: Servicos, lila: Any) -> None:
        from app.erros import ErroParaOUsuario

        with pytest.raises(ErroParaOUsuario, match="peppa"):
            gerar_clipe_rapido(
                ContextoDeTeste(servicos=servicos), {"character_id": lila.id, "prompt": "Lila encontra a Peppa Pig"}
            )
        _texto(servicos).respostas.append(
            {"background": "uma floresta com muito sangue", "animation": "andar", "emotion": "feliz"}
        )
        with pytest.raises(ErroParaOUsuario, match="sangue"):
            gerar_clipe_rapido(
                ContextoDeTeste(servicos=servicos), {"character_id": lila.id, "prompt": "Lila anda na floresta"}
            )
        assert cast(ImagemFalsa, servicos.motores.imagem).pedidos == []

    def test_personagem_apagado_e_pedido_invalido(self, servicos: Servicos) -> None:
        from app.erros import ErroParaOUsuario

        with pytest.raises(ErroParaOUsuario, match="não existe mais"):
            gerar_clipe_rapido(ContextoDeTeste(servicos=servicos), {"character_id": "0" * 32, "prompt": "pula"})
        with pytest.raises(ErroParaOUsuario, match="incompleto"):
            gerar_clipe_rapido(ContextoDeTeste(servicos=servicos), {"character_id": "x", "prompt": "a"})


class TestApiDoClipeRapido:
    def test_pedido_valido_vira_job(self, client: TestClient, lila: Any) -> None:
        r = client.post(
            "/api/clips/quick", json={"character_id": lila.id, "prompt": "Lila pula na poça", "duration_s": 6}
        )
        assert r.status_code == 202
        job = r.json()
        assert (
            job["kind"] == "clipe.rapido"
            and job["title"] == "Clipe rápido de Lila"
            and job["params"]["duration_s"] == 6
        )

    @pytest.mark.parametrize(
        "corpo",
        [
            {"prompt": "x"},
            {"prompt": "ab"},
            {"duration_s": 1},
            {"duration_s": 30},
            {"format": "1:1"},
            {"quality": "alta"},
            {"prompt": "x" * 301},
        ],
    )
    def test_valida(self, client: TestClient, lila: Any, corpo: dict[str, Any]) -> None:
        assert (
            client.post("/api/clips/quick", json={"character_id": lila.id, "prompt": "Lila pula", **corpo}).status_code
            == 422
        )

    def test_personagem_sem_recorte_e_marca_de_terceiros(
        self, client: TestClient, servicos: Servicos, tmp_path: Path, lila: Any
    ) -> None:
        sem = personagem_pronto(servicos, tmp_path, "Sol", slots=())
        r = client.post("/api/clips/quick", json={"character_id": sem.id, "prompt": "Sol pula"})
        assert r.status_code == 409 and "PNG transparente" in r.json()["detail"]
        assert (
            client.post("/api/clips/quick", json={"character_id": lila.id, "prompt": "Lila e o Mickey"}).status_code
            == 422
        )
        assert client.post("/api/clips/quick", json={"character_id": "0" * 32, "prompt": "pula"}).status_code == 404

    def test_sem_motor_de_imagem_ou_ffmpeg(self, client: TestClient, servicos: Servicos, lila: Any) -> None:
        servicos.motores.imagem = ImagemFalsa(indisponivel="O motor de imagens ainda não está instalado")
        assert client.post("/api/clips/quick", json={"character_id": lila.id, "prompt": "Lila pula"}).status_code == 503
        servicos.motores.imagem = ImagemFalsa()
        servicos.motores.ffmpeg = FfmpegFalso(indisponivel="O ffmpeg ainda não está instalado")
        assert client.post("/api/clips/quick", json={"character_id": lila.id, "prompt": "Lila pula"}).status_code == 503

    def test_o_clipe_aparece_na_biblioteca_pelo_job_completo(
        self, client_com_worker: TestClient, servicos: Servicos, lila: Any
    ) -> None:
        c = client_com_worker
        job = c.post(
            "/api/clips/quick", json={"character_id": lila.id, "prompt": "Lila pula na poça", "duration_s": 3}
        ).json()
        resultado = _esperar_job(c, job["id"])
        lista = c.get("/api/clips").json()
        assert lista["total"] == 1 and lista["items"][0]["id"] == resultado["result"]["media_id"]
        assert lista["items"][0]["role"] == "clipe_rapido" and lista["items"][0]["metadata"]["character_name"] == "Lila"
        detalhe = c.get(f"/api/clips/{lista['items'][0]['id']}").json()
        assert detalhe["kind"] == "video" and detalhe["variants"] == []


class TestBiblioteca:
    def _clipe(self, sv: Servicos, tmp_path: Path, papel: str, nome: str, **campos: Any) -> Any:
        arquivo = tmp_path / f"{nome}.mp4"
        arquivo.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
        return sv.midias.adotar(arquivo, tipo="video", papel=papel, duracao_s=3.0, **campos)

    def test_lista_so_os_papeis_da_biblioteca(self, client: TestClient, servicos: Servicos, tmp_path: Path) -> None:
        a = self._clipe(servicos, tmp_path, "clipe_rapido", "a", prompt="Lila pula")
        self._clipe(servicos, tmp_path, "cena_clipe", "interno")  # clipe de cena: não aparece na biblioteca
        c = self._clipe(servicos, tmp_path, "video_final", "v")
        todos = client.get("/api/clips").json()
        assert {m["id"] for m in todos["items"]} == {a.id, c.id} and todos["total"] == 2
        assert [m["id"] for m in client.get("/api/clips", params={"role": "video_final"}).json()["items"]] == [c.id]
        assert client.get("/api/clips", params={"role": "cena_clipe"}).json()["total"] == 0
        assert [m["id"] for m in client.get("/api/clips", params={"q": "pula"}).json()["items"]] == [a.id]
        assert client.get("/api/clips", params={"limit": 0}).status_code == 422

    def test_detalhes_apagar_e_protecao_de_projeto(
        self, client: TestClient, servicos: Servicos, tmp_path: Path, lila: Any
    ) -> None:
        livre = self._clipe(servicos, tmp_path, "clipe_rapido", "a")
        projeto, _ = projeto_com_cenas(servicos, [lila])
        do_projeto = self._clipe(
            servicos,
            tmp_path,
            "video_final",
            "v",
            dono_tipo="projeto",
            dono_id=projeto.id,
            metadados={"project_id": projeto.id},
        )
        assert client.get(f"/api/clips/{do_projeto.id}").json()["project_title"] == "A chuva do jardim"
        assert client.delete(f"/api/clips/{do_projeto.id}").status_code == 409
        assert client.delete(f"/api/clips/{livre.id}").json() == {"deleted": True}
        assert (
            client.get(f"/api/clips/{livre.id}").status_code == 404
            and client.get("/api/clips/nao-e-id").status_code == 422
        )
        assert client.get(f"/api/clips/{'0' * 32}").status_code == 404

    def test_reenquadrar_e_unir_pedem_job_e_validam(
        self, client: TestClient, servicos: Servicos, tmp_path: Path
    ) -> None:
        a, b = (
            self._clipe(servicos, tmp_path, "clipe_rapido", "a"),
            self._clipe(servicos, tmp_path, "clipe_rapido", "b"),
        )
        r = client.post(f"/api/clips/{a.id}/reframe", json={"preset": "16:9", "mode": "crop"})
        assert (
            r.status_code == 202
            and r.json()["kind"] == "clipe.reenquadrar"
            and r.json()["params"] == {"preset": "16:9", "mode": "crop", "clip_id": a.id}
        )
        assert client.post(f"/api/clips/{a.id}/reframe", json={"preset": "4:3"}).status_code == 422
        assert client.post(f"/api/clips/{'0' * 32}/reframe", json={"preset": "1:1"}).status_code == 404
        j = client.post("/api/clips/join", json={"clip_ids": [a.id, b.id], "transition": "fade"})
        assert j.status_code == 202 and j.json()["title"] == "Unir 2 vídeos" and j.json()["params"]["size"] == "auto"
        assert client.post("/api/clips/join", json={"clip_ids": [a.id]}).status_code == 422
        assert client.post("/api/clips/join", json={"clip_ids": [a.id, "0" * 32]}).status_code == 404
        assert (
            client.post("/api/clips/join", json={"clip_ids": [a.id, b.id], "transition": "explosao"}).status_code == 422
        )
        servicos.motores.ffmpeg = FfmpegFalso(indisponivel="O ffmpeg ainda não está instalado")
        assert client.post("/api/clips/join", json={"clip_ids": [a.id, b.id]}).status_code == 503


def _clipe_real(
    ffmpeg: Ffmpeg,
    pasta: Path,
    nome: str,
    cor: tuple[int, int, int],
    tamanho: tuple[int, int] = (96, 54),
    duracao: float = 1.0,
    com_audio: bool = True,
) -> Path:
    fundo = pasta / f"{nome}.png"
    Image.new("RGB", tamanho, cor).save(fundo)
    cena = CenaDeRender(fundo, duracao, [CamadaDeRender(png_de_personagem(pasta / f"{nome}-p.png"), 0.5, 0.9, 0.5)])
    mudo = pasta / f"{nome}-mudo.mp4"
    renderizar_cena(ContextoReal(), ffmpeg, cena, mudo, largura=tamanho[0], altura=tamanho[1], fps=12)
    if not com_audio:
        return mudo
    saida = pasta / f"{nome}.mp4"
    ffmpeg.rodar(
        ContextoReal(),
        [
            "-i",
            mudo.resolve(),
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=330:duration=" + str(duracao),
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            saida.resolve(),
        ],
    )
    return saida


class TestComFfmpegDeVerdade:
    @pytest.fixture
    def real(self, servicos: Servicos, ffmpeg_real: Ffmpeg) -> Ffmpeg:
        servicos.motores.ffmpeg = ffmpeg_real
        return ffmpeg_real

    def _guardar(self, sv: Servicos, arquivo: Path, papel: str = "clipe_enviado", **campos: Any) -> Any:
        sonda = sv.motores.ffmpeg.sondar(arquivo)
        return sv.midias.adotar(
            arquivo,
            tipo="video",
            papel=papel,
            extensao="mp4",
            largura=sonda.largura,
            altura=sonda.altura,
            duracao_s=sonda.duracao_s,
            mover=False,
            **campos,
        )

    def test_unir_clipes_de_tamanhos_diferentes_com_corte_e_com_transicao(
        self, servicos: Servicos, tmp_path: Path, real: Ffmpeg
    ) -> None:
        from app.tarefas.clipes import unir_videos

        a = self._guardar(servicos, _clipe_real(real, tmp_path, "a", (200, 60, 60), (96, 54)))
        b = self._guardar(
            servicos, _clipe_real(real, tmp_path, "b", (60, 200, 60), (54, 96), com_audio=False)
        )  # vertical e sem áudio
        corte = unir_videos(_ctx_real(servicos), {"clip_ids": [a.id, b.id], "transition": "corte", "size": "auto"})
        sonda = real.sondar(servicos.midias.caminho_absoluto(servicos.midias.obter(corte["media_id"])))  # type: ignore[arg-type]
        assert (sonda.largura, sonda.altura) == (96, 54) and sonda.duracao_s == pytest.approx(2.0, abs=0.25)
        assert sonda.tem_audio and sonda.codec_de_video == "h264" and sonda.canais == 2
        fade = unir_videos(_ctx_real(servicos), {"clip_ids": [a.id, b.id], "transition": "fade", "size": "9:16"})
        sonda2 = real.sondar(servicos.midias.caminho_absoluto(servicos.midias.obter(fade["media_id"])))  # type: ignore[arg-type]
        assert (sonda2.largura, sonda2.altura) == (1080, 1920) and sonda2.duracao_s == pytest.approx(1.5, abs=0.3)
        final = servicos.midias.obter(fade["media_id"])
        assert final is not None and final.papel == "clipe_unido" and final.metadados["source_ids"] == [a.id, b.id]
        assert list(servicos.settings.temp_dir.glob("uniao-*")) == []  # os normalizados temporários foram apagados

    def test_outra_resolucao_com_fundo_desfocado_e_cortando(
        self, servicos: Servicos, tmp_path: Path, real: Ffmpeg
    ) -> None:
        from app.tarefas.clipes import reenquadrar

        origem = self._guardar(
            servicos,
            _clipe_real(real, tmp_path, "h", (200, 200, 60), (192, 108)),
            "clipe_rapido",
            metadados={"layout": [{"x": 0.2}]},
        )
        ajustado = reenquadrar(_ctx_real(servicos), {"clip_id": origem.id, "preset": "9:16", "mode": "fit"})
        assert (ajustado["width"], ajustado["height"]) == (1080, 1920)
        variante = servicos.midias.obter(ajustado["media_id"])
        assert variante is not None and variante.pai_id == origem.id and variante.papel == "clipe_reenquadrado"
        assert variante.metadados["preset"] == "9:16" and variante.miniatura is not None
        cortado = reenquadrar(_ctx_real(servicos), {"clip_id": origem.id, "preset": "1:1", "mode": "crop"})
        assert (cortado["width"], cortado["height"]) == (1080, 1080)
        rapido = reenquadrar(_ctx_real(servicos), {"clip_id": origem.id, "preset": "720p", "mode": "fit"})
        assert (rapido["width"], rapido["height"]) == (1280, 720)

    def test_reenquadrar_video_sem_audio(self, servicos: Servicos, tmp_path: Path, real: Ffmpeg) -> None:
        from app.tarefas.clipes import reenquadrar

        origem = self._guardar(servicos, _clipe_real(real, tmp_path, "m", (60, 60, 200), (96, 54), com_audio=False))
        r = reenquadrar(_ctx_real(servicos), {"clip_id": origem.id, "preset": "1:1"})
        assert not real.sondar(servicos.midias.caminho_absoluto(servicos.midias.obter(r["media_id"]))).tem_audio  # type: ignore[arg-type]

    def test_clipe_que_sumiu(self, servicos: Servicos, tmp_path: Path, real: Ffmpeg) -> None:
        from app.erros import ErroParaOUsuario
        from app.tarefas.clipes import reenquadrar

        origem = self._guardar(servicos, _clipe_real(real, tmp_path, "x", (1, 2, 3)))
        servicos.midias.caminho_absoluto(origem).unlink()
        with pytest.raises(ErroParaOUsuario, match="sumiu do disco"):
            reenquadrar(_ctx_real(servicos), {"clip_id": origem.id, "preset": "1:1"})
        with pytest.raises(ErroParaOUsuario, match="não está mais na biblioteca"):
            reenquadrar(_ctx_real(servicos), {"clip_id": "0" * 32, "preset": "1:1"})

    def test_enviar_video_de_verdade(
        self, client: TestClient, servicos: Servicos, tmp_path: Path, real: Ffmpeg
    ) -> None:
        video = _clipe_real(real, tmp_path, "meu", (10, 120, 200), (128, 72), 1.0)
        r = client.post(
            "/api/clips/upload", params={"name": "meu video.mp4", "rights": "true"}, content=video.read_bytes()
        )
        assert r.status_code == 201, r.text
        corpo = r.json()
        assert (
            corpo["role"] == "clipe_enviado"
            and (corpo["width"], corpo["height"]) == (128, 72)
            and corpo["format"] == "mp4"
        )
        assert (
            corpo["duration_s"] == pytest.approx(1.0, abs=0.2)
            and corpo["thumb_url"]
            and corpo["metadata"]["original_name"] == "meu_video.mp4"
        )
        assert corpo["metadata"]["has_audio"] is True and corpo["metadata"]["rights_confirmed"] is True
        assert client.get(corpo["thumb_url"]).headers["content-type"] == "image/webp"
        assert list(servicos.settings.temp_dir.glob("envio-*")) == []

    def test_enviar_recusa_o_que_nao_e_video(self, client: TestClient, servicos: Servicos, real: Ffmpeg) -> None:
        r = client.post(
            "/api/clips/upload", params={"name": "a.mp4", "rights": "true"}, content=b"MZ isto e um programa"
        )
        assert r.status_code == 422 and "recusado" in r.json()["detail"]
        assert (
            client.post("/api/clips/upload", params={"name": "a.mp4"}, content=b"x").status_code == 422
        )  # sem confirmar o direito de uso
        assert (
            client.post("/api/clips/upload", params={"name": "a.mp4", "rights": "true"}, content=b"").status_code == 422
        )
        assert client.post("/api/clips/upload", params={"rights": "true"}, content=b"x").status_code == 422  # sem nome
        assert servicos.midias.contar() == 0 and list(servicos.settings.temp_dir.glob("envio-*")) == []

    def test_enviar_grande_demais_pelo_cabecalho(self, client: TestClient, real: Ffmpeg) -> None:
        r = client.post(
            "/api/clips/upload",
            params={"name": "a.mp4", "rights": "true"},
            headers={"content-length": str(2 * 1024**3)},
            content=b"x",
        )
        assert r.status_code in (413, 400, 422)

    def test_o_outro_site_nao_consegue_enviar(self, client: TestClient, real: Ffmpeg) -> None:
        r = client.post(
            "/api/clips/upload",
            params={"name": "a.mp4", "rights": "true"},
            content=b"x",
            headers={"Origin": "http://site-malicioso.example"},
        )
        assert r.status_code == 403


def _ctx_real(sv: Servicos) -> ContextoReal:
    return ContextoReal(servicos=sv)


class TestContinuar:
    @pytest.fixture
    def real(self, servicos: Servicos, ffmpeg_real: Ffmpeg) -> Ffmpeg:
        servicos.motores.ffmpeg = ffmpeg_real
        return ffmpeg_real

    def test_continua_um_clipe_rapido_no_mesmo_lugar_do_ultimo_quadro(
        self, client: TestClient, servicos: Servicos, tmp_path: Path, real: Ffmpeg, lila: Any
    ) -> None:
        from app.tarefas.clipes import gerar_clipe_rapido as gerar

        servicos.motores.ffmpeg = FfmpegFalso()  # o clipe rápido é gerado com os motores falsos...
        r = gerar(
            ContextoDeTeste(servicos=servicos),
            {"character_id": lila.id, "prompt": "Lila pula na poça", "duration_s": 3},
        )
        origem = servicos.midias.obter(r["media_id"])
        assert origem is not None
        video = _clipe_real(real, tmp_path, "rapido", (120, 190, 240), (96, 54), 1.5)
        shutil.copyfile(
            video, servicos.midias.caminho_absoluto(origem)
        )  # troca o arquivo falso por um vídeo de verdade
        servicos.motores.ffmpeg = real  # ...e a continuação usa o ffmpeg de verdade
        resposta = client.post(
            f"/api/clips/{origem.id}/continue",
            json={"prompt": "Agora Lila vai para o parque e encontra um amigo.", "title": "No parque"},
        )
        assert resposta.status_code == 201, resposta.text
        corpo = resposta.json()
        projeto = corpo["project"]
        assert (
            projeto["title"] == "No parque"
            and projeto["character_ids"] == [lila.id]
            and projeto["story"]["story"].startswith("Agora Lila")
        )
        assert corpo["last_frame"]["role"] == "quadro_final" and corpo["last_frame"]["owner_id"] == projeto["id"]
        ligacao = projeto["settings"]["continuation"]["junction"]
        assert (
            ligacao["title"] == "Ligação com o vídeo anterior"
            and ligacao["characters"] == [lila.id]
            and ligacao["background"]
        )
        assert ligacao["layout"][0]["entrada"] == "nenhuma" and ligacao["duration_s"] == 3.0
        fundo = servicos.midias.obter(ligacao["background"]["media_id"])
        assert fundo is not None and fundo.papel == "fundo_ligacao" and fundo.dono_id == projeto["id"]

    def test_o_roteiro_da_continuacao_comeca_pela_cena_de_ligacao(
        self, client_com_worker: TestClient, servicos: Servicos, tmp_path: Path, real: Ffmpeg, lila: Any
    ) -> None:
        c = client_com_worker
        video = _clipe_real(real, tmp_path, "externo", (200, 100, 50), (72, 128), 1.5)  # vertical, enviado por fora
        r = c.post(
            "/api/clips/upload", params={"name": "externo.mp4", "rights": "true"}, content=video.read_bytes()
        ).json()
        continuacao = c.post(
            f"/api/clips/{r['id']}/continue",
            json={
                "prompt": "Lila chega e acena para todo mundo.",
                "character_ids": [lila.id],
                "last_scene": "uma rua ensolarada",
            },
        ).json()
        projeto = continuacao["project"]
        assert projeto["format"] == "short" and projeto["style"] == "2D" and projeto["language"] == "pt-BR"
        ligacao = projeto["settings"]["continuation"]["junction"]
        assert (
            ligacao["characters"] == [] and ligacao["visual"] == "uma rua ensolarada"
        )  # vídeo de fora: o último quadro vira o cenário
        c.post(f"/api/projects/{projeto['id']}/stages/enredo/approve", json={})
        job = c.post(f"/api/projects/{projeto['id']}/script", json={"mode": "simples"}).json()
        _esperar_job(c, job["id"])
        cenas = c.get(f"/api/projects/{projeto['id']}").json()["scenes"]
        assert (
            cenas[0]["data"]["title"] == "Ligação com o vídeo anterior"
            and cenas[0]["data"]["background"]["media_id"] == ligacao["background"]["media_id"]
        )
        assert len(cenas) >= 2 and cenas[1]["data"]["title"] != "Ligação com o vídeo anterior"

    def test_validacoes_da_continuacao(
        self, client: TestClient, servicos: Servicos, tmp_path: Path, real: Ffmpeg, lila: Any
    ) -> None:
        video = _clipe_real(real, tmp_path, "c", (1, 2, 3))
        arquivo = servicos.midias.adotar(
            video,
            tipo="video",
            papel="clipe_enviado",
            extensao="mp4",
            duracao_s=1.0,
            largura=96,
            altura=54,
            mover=False,
        )
        url = f"/api/clips/{arquivo.id}/continue"
        assert client.post(url, json={"prompt": "ok"}).status_code == 422
        assert client.post(url, json={"prompt": "Lila encontra a Peppa Pig"}).status_code == 422
        assert client.post(url, json={"prompt": "Lila vai ao parque", "character_ids": ["0" * 32]}).status_code == 422
        assert client.post(f"/api/clips/{'0' * 32}/continue", json={"prompt": "Lila vai ao parque"}).status_code == 404
        assert servicos.projetos.listar() == []
