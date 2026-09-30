"""Pacote .fabulim: exportar e importar projetos e personagens, e recusar pacotes malformados ou maliciosos."""

from __future__ import annotations

import hashlib
import io
import json
import wave
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings, carregar_configuracao
from app.container import Servicos, criar_servicos
from app.motores.contexto import ContextoSincrono
from app.motores.ffmpeg import Ffmpeg
from app.projetos import pacote
from app.projetos.cenas import DadosDaCena
from app.projetos.pacote import PacoteInvalido, exportar_personagens, exportar_projeto, importar_pacote

from .builders_projetos import dar_cenario, personagem_pronto, projeto_com_cenas
from .conftest import RAIZ, MedidoresFalsos, instalar_falso, ollama_falso
from .fakes_motores import motores_falsos

ID_A = "a" * 32
ID_B = "b" * 32


def _outra_maquina(tmp_path: Path, settings: Settings) -> Servicos:
    """Um segundo estúdio (banco e pastas próprios): a máquina para onde o pacote vai."""
    env = {
        "FABULIM_DATA_DIR": str(tmp_path / "data-2"),
        "FABULIM_MODELS_DIR": str(tmp_path / "models-2"),
        "FABULIM_TOOLS_DIR": str(tmp_path / "tools-2"),
        "FABULIM_HARDWARE_JSON": str(settings.hardware_json),
        "FABULIM_FRONTEND_DIST": str(tmp_path / "dist-2"),
        "FABULIM_AUTO_DIAGNOSTICO": "0",
    }
    config = carregar_configuracao(env, root=RAIZ)
    instalar_falso(config)
    cliente, _ = ollama_falso()
    return criar_servicos(config, ollama=cliente, medidores=MedidoresFalsos(), motores=motores_falsos())


def _projeto_completo(sv: Servicos, pasta: Path) -> tuple[Any, Any, list[Any]]:
    """Lila pronta (com recortes), um projeto de 2 cenas com cenário, uma edição (versão 2) e as três primeiras etapas aprovadas."""
    lila = personagem_pronto(sv, pasta, "Lila")
    projeto, cenas = projeto_com_cenas(sv, [lila])
    for cena in cenas:
        dar_cenario(sv, pasta, cena)
    dados = DadosDaCena.model_validate(sv.projetos.cena(cenas[0].id).dados).model_dump()  # type: ignore[union-attr]
    dados["narration"] = "Era uma vez um jardim lindo."
    dados["approved"] = {"roteiro": True, "storyboard": True}
    sv.projetos.atualizar_cena(cenas[0].id, dados, "editada pelo usuário")
    sv.projetos.atualizar(
        projeto.id,
        aprovacoes={"enredo": True, "roteiro": True, "storyboard": True},
        etapa="animacao",
        musica={"style": "calma", "volume": 0.2},
        configuracoes={
            "transition": "fade",
            "fps": 24,
            "voices": {lila.id: {"id": "pm_alex", "speed": 1.0, "pitch": 1.0}},
            "script_history": [{"scenes": []}],
        },
    )
    novo = sv.projetos.obter(projeto.id)
    return lila, novo, [sv.projetos.cena(c.id) for c in cenas]


def _zip(destino: Path, manifesto: dict[str, Any] | bytes | None, arquivos: dict[str, bytes] | None = None) -> Path:
    with zipfile.ZipFile(destino, "w") as zf:
        if manifesto is not None:
            zf.writestr(
                "manifest.json",
                manifesto if isinstance(manifesto, bytes) else json.dumps(manifesto, ensure_ascii=False),
            )
        for nome, dados in (arquivos or {}).items():
            zf.writestr(nome, dados)
    return destino


def _png(tamanho: tuple[int, int] = (32, 32), rgba: bool = False) -> bytes:
    saida = io.BytesIO()
    Image.new("RGBA" if rgba else "RGB", tamanho, (200, 30, 30, 255) if rgba else (200, 30, 30)).save(saida, "PNG")
    return saida.getvalue()


def _midia(id_: str = ID_A, dados: bytes | None = None, **campos: Any) -> tuple[dict[str, Any], dict[str, bytes]]:
    conteudo = dados if dados is not None else _png()
    extensao = campos.pop("ext", "png")
    registro = {
        "id": id_,
        "kind": "imagem",
        "role": "variacao",
        "file": f"media/{id_}.{extensao}",
        "created_at": "2026-09-30T00:00:00",
        "sha256": hashlib.sha256(conteudo).hexdigest(),
        "size": len(conteudo),
        "owner_type": "personagem",
        "owner_id": ID_A,
        **campos,
    }
    return registro, {registro["file"]: conteudo}


def _manifesto(midias: list[dict[str, Any]] | None = None, **campos: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "format": "fabulim",
        "version": 1,
        "kind": "characters",
        "app_version": "0.1.0",
        "exported_at": "2026-09-30T00:00:00",
        "characters": [
            {
                "id": ID_A,
                "name": "Bia",
                "style": "2D",
                "form": {"appearance": "raposa ruiva"},
                "voice": {"id": "pf_dora", "speed": 1.0, "pitch": 1.0},
                "main_image_id": ID_A,
            }
        ],
        "media": midias or [],
    }
    return {**base, **campos}


def _valido(tmp_path: Path, nome: str = "ok.fabulim") -> Path:
    registro, arquivos = _midia()
    return _zip(tmp_path / nome, _manifesto([registro]), arquivos)


def _nada_entrou(sv: Servicos) -> bool:
    return not sv.personagens.listar() and not sv.projetos.listar() and sv.midias.contar() == 0


class TestIdaEVolta:
    def test_o_projeto_volta_inteiro_com_ids_novos_e_sem_mexer_no_original(
        self, servicos: Servicos, tmp_path: Path
    ) -> None:
        lila, projeto, cenas = _projeto_completo(servicos, tmp_path)
        antes = servicos.midias.contar()
        relatorio = exportar_projeto(servicos, projeto, tmp_path / "p.fabulim")
        assert relatorio.kind == "project" and relatorio.arquivo.is_file() and relatorio.midias > 0
        importado = importar_pacote(servicos, relatorio.arquivo)
        assert importado.kind == "project" and importado.cenas == 2 and importado.projeto_id != projeto.id
        # o personagem da biblioteca não é fundido nem sobrescrito: o importado ganha outro nome
        assert (
            importado.personagens[0]["name"] == "Lila (importado)"
            and importado.personagens[0]["renamed_from"] == "Lila"
        )
        assert any("Lila (importado)" in aviso for aviso in importado.avisos)
        nova_lila = servicos.personagens.obter(importado.personagens[0]["id"])
        assert nova_lila is not None and nova_lila.estilo == "2D" and nova_lila.origem == "importado"
        assert nova_lila.imagem_principal_id is not None and nova_lila.imagem_principal_id != lila.imagem_principal_id
        assert set(fluxos_recortes(servicos, nova_lila.id)) == {"principal", "frente", "lado", "feliz"}
        # o projeto: enredo, aprovações, etapa, música e ajustes; as chaves dos ajustes apontam para o personagem novo
        novo = servicos.projetos.obter(importado.projeto_id or "")
        assert novo is not None and novo.titulo == projeto.titulo and novo.formato == "short" and novo.idioma == "pt-BR"
        assert novo.aprovacoes == {"enredo": True, "roteiro": True, "storyboard": True} and novo.etapa == "animacao"
        assert novo.musica == {"style": "calma", "volume": 0.2}
        assert novo.configuracoes["transition"] == "fade" and novo.configuracoes["fps"] == 24
        assert list(novo.configuracoes["voices"]) == [nova_lila.id]
        assert "script_history" not in novo.configuracoes and novo.personagens == [nova_lila.id]
        # as cenas: mesma ordem e texto, referências refeitas e o histórico de versões inteiro
        novas = servicos.projetos.cenas(novo.id)
        assert [c.ordem for c in novas] == [1, 2] and novas[0].versao == 2
        assert novas[0].id != cenas[0].id
        dados = DadosDaCena.model_validate(novas[0].dados)
        assert dados.narration == "Era uma vez um jardim lindo." and dados.approved == {
            "roteiro": True,
            "storyboard": True,
        }
        assert dados.characters == [nova_lila.id] and dados.dialogue[0].character_id == nova_lila.id
        fundo = servicos.midias.obter(dados.background.media_id)  # type: ignore[union-attr]
        assert fundo is not None and fundo.dono_id == novas[0].id and fundo.dono_tipo == "cena"
        assert fundo.metadados["imported_from"] and fundo.metadados["project_id"] == novo.id
        assert servicos.midias.caminho_absoluto(fundo).is_file()
        with Image.open(servicos.midias.caminho_absoluto(fundo)) as imagem:
            imagem.load()
        assert [v["version"] for v in servicos.projetos.versoes_da_cena(novas[0].id)] == [2, 1]
        assert servicos.projetos.versoes_da_cena(novas[0].id)[0]["reason"] == "editada pelo usuário"
        # o original continua igual
        assert servicos.projetos.obter(projeto.id).aprovacoes["storyboard"] is True  # type: ignore[union-attr]
        assert [c.id for c in servicos.projetos.cenas(projeto.id)] == [c.id for c in cenas]
        assert servicos.midias.contar() > antes

    def test_em_outra_maquina_o_nome_do_personagem_fica_como_esta(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, _ = _projeto_completo(servicos, tmp_path)
        arquivo = exportar_projeto(servicos, projeto, tmp_path / "p.fabulim").arquivo
        outra = _outra_maquina(tmp_path, servicos.settings)
        relatorio = importar_pacote(outra, arquivo)
        assert relatorio.personagens[0]["name"] == "Lila" and relatorio.personagens[0]["renamed_from"] is None
        assert [p.nome for p in outra.personagens.listar()] == ["Lila"]
        assert len(outra.projetos.listar()) == 1 and relatorio.midias == outra.midias.contar()

    def test_importar_duas_vezes_numera_os_personagens(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, _ = _projeto_completo(servicos, tmp_path)
        arquivo = exportar_projeto(servicos, projeto, tmp_path / "p.fabulim").arquivo
        outra = _outra_maquina(tmp_path, servicos.settings)
        nomes = [importar_pacote(outra, arquivo).personagens[0]["name"] for _ in range(3)]
        assert nomes == ["Lila", "Lila (importado)", "Lila (importado 2)"]

    def test_o_pacote_so_tem_o_manifesto_e_os_arquivos_de_midia(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, _ = _projeto_completo(servicos, tmp_path)
        arquivo = exportar_projeto(servicos, projeto, tmp_path / "p.fabulim").arquivo
        with zipfile.ZipFile(arquivo) as zf:
            nomes = zf.namelist()
            manifesto = json.loads(zf.read("manifest.json"))
        assert "manifest.json" in nomes
        assert all(n == "manifest.json" or pacote.ENTRADA_DE_MIDIA.match(n) for n in nomes)
        assert manifesto["format"] == "fabulim" and manifesto["version"] == 1 and manifesto["kind"] == "project"
        assert manifesto["includes_renders"] is False and manifesto["profile"] == "C"
        papeis = {m["role"] for m in manifesto["media"]}
        assert papeis == {"variacao", "recorte", "fundo"}  # sem clipes, áudio, vídeo, miniaturas
        for m in manifesto["media"]:
            with zipfile.ZipFile(arquivo) as zf:
                assert hashlib.sha256(zf.read(m["file"])).hexdigest() == m["sha256"]

    def test_sem_os_renders_a_animacao_e_o_resto_voltam_a_pedir_aprovacao(
        self, servicos: Servicos, tmp_path: Path
    ) -> None:
        _, projeto, cenas = _projeto_completo(servicos, tmp_path)
        for cena in cenas:  # cada cena já tem clipe aprovado, e o projeto já passou da animação
            dados = DadosDaCena.model_validate(cena.dados).model_dump()
            dados["clip"] = {
                "media_id": dados["background"]["media_id"],
                "render_hash": "x",
                "quality": "final",
                "duration_s": 5,
            }
            dados["approved"] = {"roteiro": True, "storyboard": True, "animacao": True}
            servicos.projetos.atualizar_cena_sem_versao(cena.id, dados)
        servicos.projetos.atualizar(
            projeto.id,
            aprovacoes={"enredo": True, "roteiro": True, "storyboard": True, "animacao": True, "audio": True},
            etapa="montagem",
        )
        arquivo = exportar_projeto(servicos, servicos.projetos.obter(projeto.id), tmp_path / "p.fabulim").arquivo  # type: ignore[arg-type]
        relatorio = importar_pacote(_outra_maquina(tmp_path, servicos.settings), arquivo)
        assert any("voltaram a «não aprovada»" in aviso for aviso in relatorio.avisos)

    def test_o_relatorio_diz_o_que_mudou_no_projeto_importado(self, servicos: Servicos, tmp_path: Path) -> None:
        _, projeto, cenas = _projeto_completo(servicos, tmp_path)
        for cena in cenas:
            dados = DadosDaCena.model_validate(cena.dados).model_dump()
            dados["clip"] = {
                "media_id": dados["background"]["media_id"],
                "render_hash": "x",
                "quality": "final",
                "duration_s": 5,
            }
            dados["approved"] = {"roteiro": True, "storyboard": True, "animacao": True}
            servicos.projetos.atualizar_cena_sem_versao(cena.id, dados)
        servicos.projetos.atualizar(
            projeto.id,
            aprovacoes={"enredo": True, "roteiro": True, "storyboard": True, "animacao": True, "audio": True},
            etapa="montagem",
        )
        arquivo = exportar_projeto(servicos, servicos.projetos.obter(projeto.id), tmp_path / "p.fabulim").arquivo  # type: ignore[arg-type]
        outra = _outra_maquina(tmp_path, servicos.settings)
        relatorio = importar_pacote(outra, arquivo)
        novo = outra.projetos.obter(relatorio.projeto_id or "")
        assert novo is not None
        assert novo.aprovacoes == {"enredo": True, "roteiro": True, "storyboard": True} and novo.etapa == "animacao"
        for cena in outra.projetos.cenas(novo.id):
            dados = DadosDaCena.model_validate(cena.dados)
            assert dados.clip is None and dados.timeline is None and "animacao" not in dados.approved
            assert dados.approved["storyboard"] is True  # o cenário veio no pacote: continua aprovado

    def test_so_os_personagens(self, servicos: Servicos, tmp_path: Path) -> None:
        lila = personagem_pronto(servicos, tmp_path, "Lila")
        bento = personagem_pronto(servicos, tmp_path, "Bento", "3D", voz={"id": "pm_alex", "speed": 0.9, "pitch": 1.0})
        relatorio = exportar_personagens(servicos, [lila, bento], tmp_path / "bib.fabulim")
        assert relatorio.kind == "characters" and relatorio.midias == 10  # de cada um: a imagem principal e 4 recortes
        outra = _outra_maquina(tmp_path, servicos.settings)
        r = importar_pacote(outra, relatorio.arquivo)
        assert r.kind == "characters" and r.projeto_id is None and r.cenas == 0
        por_nome = {p.nome: p for p in outra.personagens.listar()}
        assert set(por_nome) == {"Lila", "Bento"} and por_nome["Bento"].estilo == "3D"
        assert por_nome["Bento"].voz["id"] == "pm_alex" and por_nome["Bento"].voz["speed"] == 0.9
        assert por_nome["Lila"].estado == "pronto" and por_nome["Lila"].imagem_principal_id is not None
        assert set(fluxos_recortes(outra, por_nome["Bento"].id)) == {"principal", "frente", "lado", "feliz"}
        assert outra.midias.contar() == 10

    def test_a_pose_mais_nova_continua_sendo_a_mais_nova(self, servicos: Servicos, tmp_path: Path) -> None:
        lila = personagem_pronto(servicos, tmp_path, "Lila", slots=("principal",))
        cores = [(10, 10, 10), (250, 250, 250)]
        for cor in cores:  # duas versões do recorte do slot «lado»; a última criada vale
            origem = tmp_path / f"lado-{cor[0]}.png"
            Image.new("RGBA", (40, 40), (*cor, 255)).save(origem)
            servicos.midias.adotar(
                origem,
                tipo="imagem",
                papel="recorte",
                dono_tipo="personagem",
                dono_id=lila.id,
                metadados={"slot": "lado"},
            )
        arquivo = exportar_personagens(servicos, [lila], tmp_path / "b.fabulim").arquivo
        outra = _outra_maquina(tmp_path, servicos.settings)
        r = importar_pacote(outra, arquivo)
        recorte = fluxos_recortes(outra, r.personagens[0]["id"])["lado"]
        with Image.open(outra.midias.caminho_absoluto(recorte)) as imagem:
            assert imagem.convert("RGBA").getpixel((5, 5))[:3] == cores[1]

    def test_arquivo_que_sumiu_do_disco_vira_aviso_e_o_resto_segue(self, servicos: Servicos, tmp_path: Path) -> None:
        lila = personagem_pronto(servicos, tmp_path, "Lila")
        sumida = servicos.midias.listar(papeis=("recorte",), dono_id=lila.id)[0]
        servicos.midias.caminho_absoluto(sumida).unlink()
        relatorio = exportar_personagens(servicos, [lila], tmp_path / "b.fabulim")
        assert relatorio.midias == 4 and any("não está mais no disco" in a for a in relatorio.avisos)
        assert importar_pacote(_outra_maquina(tmp_path, servicos.settings), relatorio.arquivo).midias == 4

    def test_avisa_quando_o_perfil_da_maquina_e_outro(self, servicos: Servicos, tmp_path: Path) -> None:
        registro, arquivos = _midia()
        arquivo = _zip(tmp_path / "d.fabulim", _manifesto([registro], profile="D"), arquivos)
        relatorio = importar_pacote(_outra_maquina(tmp_path, servicos.settings), arquivo)
        assert any("perfil D" in aviso and "perfil C" in aviso for aviso in relatorio.avisos)


class TestComVideoDeVerdade:
    @pytest.fixture
    def real(self, servicos: Servicos, ffmpeg_real: Ffmpeg) -> Ffmpeg:
        servicos.motores.ffmpeg = ffmpeg_real
        return ffmpeg_real

    def _video(self, real: Ffmpeg, caminho: Path) -> Path:
        real.rodar(
            ContextoSincrono(),
            ["-f", "lavfi", "-i", "color=c=red:s=128x72:d=1:r=12", "-c:v", "libx264", "-pix_fmt", "yuv420p", caminho],
            timeout=120,
        )
        return caminho

    def _onda(self, caminho: Path) -> Path:
        with wave.open(str(caminho), "wb") as onda:
            onda.setnchannels(1)
            onda.setsampwidth(2)
            onda.setframerate(24_000)
            onda.writeframes(b"\x00\x00" * 24_000)
        return caminho

    def test_com_renders_o_clipe_o_audio_e_a_legenda_vao_junto(
        self, servicos: Servicos, tmp_path: Path, real: Ffmpeg
    ) -> None:
        _, projeto, cenas = _projeto_completo(servicos, tmp_path)
        clipe = servicos.midias.adotar(
            self._video(real, tmp_path / "c.mp4"),
            tipo="video",
            papel="cena_clipe",
            dono_tipo="cena",
            dono_id=cenas[0].id,
            duracao_s=1.0,
        )
        mix = servicos.midias.adotar(
            self._onda(tmp_path / "mix.wav"), tipo="audio", papel="mix", dono_tipo="projeto", dono_id=projeto.id
        )
        srt = tmp_path / "l.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nOlá!\n", encoding="utf-8")
        legenda = servicos.midias.adotar(srt, tipo="legenda", papel="legenda", dono_tipo="projeto", dono_id=projeto.id)
        final = servicos.midias.adotar(
            self._video(real, tmp_path / "f.mp4"),
            tipo="video",
            papel="video_final",
            dono_tipo="projeto",
            dono_id=projeto.id,
            duracao_s=1.0,
        )
        dados = DadosDaCena.model_validate(servicos.projetos.cena(cenas[0].id).dados).model_dump()  # type: ignore[union-attr]
        dados["clip"] = {"media_id": clipe.id, "render_hash": "h", "quality": "final", "duration_s": 1.0}
        dados["approved"]["animacao"] = True
        servicos.projetos.atualizar_cena_sem_versao(cenas[0].id, dados)
        servicos.projetos.atualizar(
            projeto.id,
            configuracoes={
                **projeto.configuracoes,
                "final_media_id": final.id,
                "audio": {"mix_media_id": mix.id, "srt_media_id": legenda.id},
            },
        )
        sem = exportar_projeto(servicos, servicos.projetos.obter(projeto.id), tmp_path / "sem.fabulim").arquivo  # type: ignore[arg-type]
        com = exportar_projeto(
            servicos, servicos.projetos.obter(projeto.id), tmp_path / "com.fabulim", renders=True
        ).arquivo  # type: ignore[arg-type]
        assert sem.stat().st_size < com.stat().st_size
        outra = _outra_maquina(tmp_path, servicos.settings)
        outra.motores.ffmpeg = real
        r = importar_pacote(outra, com)
        novo = outra.projetos.obter(r.projeto_id or "")
        assert novo is not None
        papeis = sorted(m.papel for m in outra.midias.listar(dono_tipo="projeto", dono_id=novo.id))
        assert papeis == ["legenda", "mix", "video_final"]
        assert outra.midias.obter(novo.configuracoes["final_media_id"]).tipo == "video"  # type: ignore[union-attr]
        assert set(novo.configuracoes["audio"]) == {"mix_media_id", "srt_media_id"}
        primeira = DadosDaCena.model_validate(outra.projetos.cenas(novo.id)[0].dados)
        assert primeira.clip is not None and outra.midias.obter(primeira.clip.media_id).papel == "cena_clipe"  # type: ignore[union-attr]
        assert primeira.approved["animacao"] is True

    def test_um_mp4_falso_e_recusado_pelo_ffprobe(self, servicos: Servicos, tmp_path: Path, real: Ffmpeg) -> None:
        conteudo = b"isto nao e um video" * 50
        registro, arquivos = _midia(
            dados=conteudo, kind="video", ext="mp4", role="clipe_enviado", owner_type=None, owner_id=None
        )
        arquivo = _zip(tmp_path / "f.fabulim", _manifesto([registro]), arquivos)
        with pytest.raises(PacoteInvalido, match="vídeo do pacote"):
            importar_pacote(servicos, arquivo)
        assert servicos.midias.contar() == 0

    def test_sem_ffmpeg_os_videos_ficam_de_fora_com_aviso(
        self, servicos: Servicos, tmp_path: Path, real: Ffmpeg
    ) -> None:
        video = self._video(real, tmp_path / "v.mp4")
        registro, arquivos = _midia(
            dados=video.read_bytes(), kind="video", ext="mp4", role="clipe_enviado", owner_type=None, owner_id=None
        )
        arquivo = _zip(tmp_path / "v.fabulim", _manifesto([registro]), arquivos)
        outra = _outra_maquina(tmp_path, servicos.settings)
        from .fakes_motores import FfmpegFalso

        outra.motores.ffmpeg = FfmpegFalso(indisponivel="ffmpeg não instalado")
        r = importar_pacote(outra, arquivo)
        assert r.midias == 0 and any("ffmpeg não está instalado" in a for a in r.avisos)


class TestPacoteRecusado:
    def test_o_pacote_valido_de_referencia_entra(self, servicos: Servicos, tmp_path: Path) -> None:
        r = importar_pacote(servicos, _valido(tmp_path))
        assert r.personagens[0]["name"] == "Bia" and r.midias == 1

    def test_arquivo_que_nao_e_zip(self, servicos: Servicos, tmp_path: Path) -> None:
        falso = tmp_path / "x.fabulim"
        falso.write_bytes(b"MZ\x90\x00 isto e um executavel")
        with pytest.raises(PacoteInvalido, match="não é um zip válido"):
            importar_pacote(servicos, falso)

    def test_zip_sem_manifesto(self, servicos: Servicos, tmp_path: Path) -> None:
        with pytest.raises(PacoteInvalido, match=r"não tem o manifest\.json"):
            importar_pacote(servicos, _zip(tmp_path / "s.fabulim", None, {f"media/{ID_A}.png": _png()}))

    @pytest.mark.parametrize(
        "nome",
        [
            "../evil.png",
            "media/../../evil.png",
            "/etc/passwd",
            "C:/Windows/x.png",
            "\\\\servidor\\x.png",
            "..\\evil.png",
        ],
    )
    def test_nomes_que_tentam_sair_da_pasta(self, servicos: Servicos, tmp_path: Path, nome: str) -> None:
        arquivo = _zip(tmp_path / "z.fabulim", _manifesto(), {nome: b"x"})
        with pytest.raises(PacoteInvalido, match="perigoso"):
            importar_pacote(servicos, arquivo)
        assert _nada_entrou(servicos)

    def test_arquivo_que_nao_faz_parte_do_formato(self, servicos: Servicos, tmp_path: Path) -> None:
        for nome in ("malware.exe", "media/nome-solto.png", "media/x.png", f"media/{ID_A}.exe", "outra/pasta/a.png"):
            arquivo = _zip(tmp_path / "f.fabulim", _manifesto(), {nome: b"x"})
            with pytest.raises(PacoteInvalido, match="não faz parte do formato"):
                importar_pacote(servicos, arquivo)

    def test_link_simbolico(self, servicos: Servicos, tmp_path: Path) -> None:
        arquivo = tmp_path / "l.fabulim"
        with zipfile.ZipFile(arquivo, "w") as zf:
            zf.writestr("manifest.json", json.dumps(_manifesto()))
            info = zipfile.ZipInfo(f"media/{ID_A}.png")
            info.external_attr = 0o120777 << 16
            zf.writestr(info, "../../../etc/passwd")
        with pytest.raises(PacoteInvalido, match="link simbólico"):
            importar_pacote(servicos, arquivo)

    def test_entrada_repetida(self, servicos: Servicos, tmp_path: Path) -> None:
        arquivo = tmp_path / "r.fabulim"
        with pytest.warns(UserWarning), zipfile.ZipFile(arquivo, "w") as zf:
            zf.writestr("manifest.json", json.dumps(_manifesto()))
            zf.writestr("manifest.json", json.dumps(_manifesto()))
        with pytest.raises(PacoteInvalido, match="repete o mesmo arquivo"):
            importar_pacote(servicos, arquivo)

    def test_bomba_de_descompressao(self, servicos: Servicos, tmp_path: Path) -> None:
        arquivo = tmp_path / "b.fabulim"
        with zipfile.ZipFile(arquivo, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(_manifesto()))
            zf.writestr(f"media/{ID_A}.png", b"\x00" * (40 * 1024 * 1024))
        with pytest.raises(PacoteInvalido, match="compressão suspeita"):
            importar_pacote(servicos, arquivo)

    def test_pacote_grande_demais_descompactado(
        self, servicos: Servicos, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(pacote, "LIMITE_TOTAL", 100)
        with pytest.raises(PacoteInvalido, match="grande demais"):
            importar_pacote(servicos, _valido(tmp_path))

    def test_manifesto_quebrado(self, servicos: Servicos, tmp_path: Path) -> None:
        for conteudo in (b"{nao e json", b"\xff\xfe\x00", b"[1, 2, 3]", b'"texto"'):
            with pytest.raises(PacoteInvalido):
                importar_pacote(servicos, _zip(tmp_path / "m.fabulim", conteudo))

    def test_manifesto_grande_demais(self, servicos: Servicos, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pacote, "LIMITE_DO_MANIFESTO", 50)
        with pytest.raises(PacoteInvalido, match=r"manifest\.json é grande demais"):
            importar_pacote(servicos, _valido(tmp_path))

    def test_de_outro_programa_ou_de_versao_futura(self, servicos: Servicos, tmp_path: Path) -> None:
        with pytest.raises(PacoteInvalido, match="não é um pacote do Fabulim"):
            importar_pacote(servicos, _zip(tmp_path / "o.fabulim", {"format": "outro-programa", "version": 1}))
        with pytest.raises(PacoteInvalido, match="versão mais nova"):
            importar_pacote(servicos, _zip(tmp_path / "v.fabulim", _manifesto(version=99)))

    @pytest.mark.parametrize(
        ("campo", "valor"),
        [
            ("kind", "virus"),
            ("characters", [{"id": "x", "name": "Bia", "style": "2D", "form": {}}]),
            ("characters", [{"id": ID_A, "name": "", "style": "2D", "form": {}}]),
            ("characters", [{"id": ID_A, "name": "Bia", "style": "4D", "form": {}}]),
            ("characters", [{"id": ID_A, "name": "B" * 500, "style": "2D", "form": {}}]),
            ("media", "não é lista"),
        ],
    )
    def test_campos_invalidos_no_manifesto(self, servicos: Servicos, tmp_path: Path, campo: str, valor: Any) -> None:
        arquivo = _zip(tmp_path / "c.fabulim", {**_manifesto(), campo: valor})
        with pytest.raises(PacoteInvalido, match="campo inválido"):
            importar_pacote(servicos, arquivo)
        assert _nada_entrou(servicos)

    def test_ficha_de_personagem_invalida(self, servicos: Servicos, tmp_path: Path) -> None:
        manifesto = _manifesto()
        manifesto["characters"][0]["form"] = {"appearance": "x" * 5000}
        with pytest.raises(PacoteInvalido, match="ficha do personagem"):
            importar_pacote(servicos, _zip(tmp_path / "f.fabulim", manifesto))
        assert _nada_entrou(servicos)

    def test_cena_invalida(self, servicos: Servicos, tmp_path: Path) -> None:
        projeto = {"title": "X", "format": "short", "language": "pt-BR", "style": "2D", "target_duration_s": 30}
        cena = {"id": ID_B, "order": 1, "data": {"title": "a", "camera": "voo_de_drone"}, "version": 1}
        manifesto = _manifesto(kind="project", project=projeto, scenes=[cena])
        with pytest.raises(PacoteInvalido, match="cena 1 do pacote é inválida"):
            importar_pacote(servicos, _zip(tmp_path / "c.fabulim", manifesto))
        assert _nada_entrou(servicos)

    def test_etapa_inexistente(self, servicos: Servicos, tmp_path: Path) -> None:
        projeto = {
            "title": "X",
            "format": "short",
            "language": "pt-BR",
            "style": "2D",
            "target_duration_s": 30,
            "stage": "lancamento",
        }
        with pytest.raises(PacoteInvalido, match="etapa que não existe"):
            importar_pacote(servicos, _zip(tmp_path / "e.fabulim", _manifesto(kind="project", project=projeto)))

    def test_projeto_sem_os_dados_do_projeto(self, servicos: Servicos, tmp_path: Path) -> None:
        with pytest.raises(PacoteInvalido, match="dados do projeto"):
            importar_pacote(servicos, _zip(tmp_path / "e.fabulim", _manifesto(kind="project")))

    def test_referencias_que_nao_existem(self, servicos: Servicos, tmp_path: Path) -> None:
        registro, arquivos = _midia(owner_id=ID_B)  # dono que não está no pacote
        with pytest.raises(PacoteInvalido, match="personagem que não está no pacote"):
            importar_pacote(servicos, _zip(tmp_path / "a.fabulim", _manifesto([registro]), arquivos))
        registro, arquivos = _midia(owner_type="cena", owner_id=ID_B)
        with pytest.raises(PacoteInvalido, match="cena que não está no pacote"):
            importar_pacote(servicos, _zip(tmp_path / "b.fabulim", _manifesto([registro]), arquivos))

    def test_arquivo_citado_que_nao_esta_no_pacote(self, servicos: Servicos, tmp_path: Path) -> None:
        registro, _ = _midia()
        with pytest.raises(PacoteInvalido, match="não está no pacote"):
            importar_pacote(servicos, _zip(tmp_path / "a.fabulim", _manifesto([registro])))

    def test_arquivo_apontado_com_nome_de_outro_id(self, servicos: Servicos, tmp_path: Path) -> None:
        registro, arquivos = _midia()
        registro["file"] = f"media/{ID_B}.png"
        with pytest.raises(PacoteInvalido, match="nome fora do formato"):
            importar_pacote(servicos, _zip(tmp_path / "a.fabulim", _manifesto([registro]), arquivos))

    def test_id_de_midia_repetido(self, servicos: Servicos, tmp_path: Path) -> None:
        registro, arquivos = _midia()
        with pytest.raises(PacoteInvalido, match="repete o mesmo id de mídia"):
            importar_pacote(servicos, _zip(tmp_path / "a.fabulim", _manifesto([registro, registro]), arquivos))

    def test_extensao_que_nao_combina_com_o_tipo(self, servicos: Servicos, tmp_path: Path) -> None:
        registro, arquivos = _midia(kind="audio", ext="png")
        with pytest.raises(PacoteInvalido, match="não é aceita para audio"):
            importar_pacote(servicos, _zip(tmp_path / "a.fabulim", _manifesto([registro]), arquivos))

    def test_tamanho_diferente_do_manifesto(self, servicos: Servicos, tmp_path: Path) -> None:
        registro, arquivos = _midia()
        registro["size"] += 1
        with pytest.raises(PacoteInvalido, match="tamanho de um arquivo não bate"):
            importar_pacote(servicos, _zip(tmp_path / "a.fabulim", _manifesto([registro]), arquivos))

    def test_soma_de_verificacao_que_nao_bate(self, servicos: Servicos, tmp_path: Path) -> None:
        registro, arquivos = _midia()
        registro["sha256"] = "0" * 64
        with pytest.raises(PacoteInvalido, match="soma de verificação"):
            importar_pacote(servicos, _zip(tmp_path / "a.fabulim", _manifesto([registro]), arquivos))
        assert _nada_entrou(servicos)

    def test_imagem_que_nao_e_imagem(self, servicos: Servicos, tmp_path: Path) -> None:
        registro, arquivos = _midia(dados=b"<?php system($_GET['x']); ?>" * 20)
        with pytest.raises(PacoteInvalido, match="não é uma imagem PNG de verdade"):
            importar_pacote(servicos, _zip(tmp_path / "a.fabulim", _manifesto([registro]), arquivos))

    def test_extensao_que_mente_sobre_a_imagem(self, servicos: Servicos, tmp_path: Path) -> None:
        saida = io.BytesIO()
        Image.new("RGB", (16, 16)).save(saida, "JPEG")
        registro, arquivos = _midia(dados=saida.getvalue(), ext="png")
        with pytest.raises(PacoteInvalido, match="não é uma imagem PNG de verdade"):
            importar_pacote(servicos, _zip(tmp_path / "a.fabulim", _manifesto([registro]), arquivos))

    def test_imagem_truncada(self, servicos: Servicos, tmp_path: Path) -> None:
        registro, arquivos = _midia(dados=_png((300, 300))[:200])
        with pytest.raises(PacoteInvalido, match="imagem do pacote está corrompida"):
            importar_pacote(servicos, _zip(tmp_path / "a.fabulim", _manifesto([registro]), arquivos))

    def test_audio_e_legenda_falsos(self, servicos: Servicos, tmp_path: Path) -> None:
        registro, arquivos = _midia(
            dados=b"RIFFxxxxWAVE nada", kind="audio", ext="wav", role="mix", owner_type=None, owner_id=None
        )
        with pytest.raises(PacoteInvalido, match="não é um WAV válido"):
            importar_pacote(servicos, _zip(tmp_path / "a.fabulim", _manifesto([registro]), arquivos))
        registro, arquivos = _midia(
            dados=b"\xff\xfe\xfd texto invalido",
            kind="legenda",
            ext="srt",
            role="legenda",
            owner_type=None,
            owner_id=None,
        )
        with pytest.raises(PacoteInvalido, match="não é texto UTF-8"):
            importar_pacote(servicos, _zip(tmp_path / "b.fabulim", _manifesto([registro]), arquivos))

    def test_falha_no_meio_desfaz_tudo_o_que_ja_entrou(self, servicos: Servicos, tmp_path: Path) -> None:
        boa, arquivo_bom = _midia(ID_A)
        ruim, arquivo_ruim = _midia(ID_B, dados=b"nao e imagem", created_at="2026-09-30T00:00:05")
        arquivos = {**arquivo_bom, **arquivo_ruim}
        manifesto = _manifesto([boa, ruim])
        pasta_das_midias = servicos.midias.raiz
        with pytest.raises(PacoteInvalido):
            importar_pacote(servicos, _zip(tmp_path / "a.fabulim", manifesto, arquivos))
        assert _nada_entrou(servicos)  # o personagem e a primeira imagem, que já tinham entrado, foram desfeitos
        assert [p for p in pasta_das_midias.rglob("*") if p.is_file()] == []
        assert list(servicos.settings.temp_dir.glob("importar-*")) == []  # e a pasta temporária foi embora


class TestRotas:
    def _pronto(self, client: TestClient, servicos: Servicos, tmp_path: Path) -> Any:
        _, projeto, _ = _projeto_completo(servicos, tmp_path)
        return projeto

    def test_baixar_o_projeto_e_importar_de_volta(self, client: TestClient, servicos: Servicos, tmp_path: Path) -> None:
        projeto = self._pronto(client, servicos, tmp_path)
        r = client.get(f"/api/packages/projects/{projeto.id}")
        assert r.status_code == 200 and "a-chuva-do-jardim.fabulim" in r.headers["content-disposition"]
        assert zipfile.ZipFile(io.BytesIO(r.content)).namelist()[-1] == "manifest.json"
        assert list(servicos.settings.temp_dir.glob("exportar-*")) == []  # o temporário some depois de enviado
        i = client.post("/api/packages/import", content=r.content)
        assert i.status_code == 201, i.text
        corpo = i.json()
        assert corpo["kind"] == "project" and corpo["scenes"] == 2 and corpo["project"]["title"] == "A chuva do jardim"
        assert (
            corpo["character_list"][0]["name"] == "Lila (importado)"
            and corpo["character_list"][0]["has_cutout"] is True
        )
        assert corpo["project"]["id"] != projeto.id and len(client.get("/api/projects").json()["items"]) == 2
        assert list(servicos.settings.temp_dir.glob("importar-*")) == []

    def test_com_renders_e_projeto_inexistente(self, client: TestClient, servicos: Servicos, tmp_path: Path) -> None:
        projeto = self._pronto(client, servicos, tmp_path)
        assert client.get(f"/api/packages/projects/{projeto.id}?renders=true").status_code == 200
        assert client.get(f"/api/packages/projects/{'0' * 32}").status_code == 404
        assert client.get("/api/packages/projects/nao-e-id").status_code == 422

    def test_baixar_personagens(self, client: TestClient, servicos: Servicos, tmp_path: Path) -> None:
        assert client.get("/api/packages/characters").status_code == 404  # biblioteca vazia
        lila = personagem_pronto(servicos, tmp_path, "Lila")
        personagem_pronto(servicos, tmp_path, "Bento")
        um = client.get(f"/api/packages/characters?id={lila.id}")
        assert um.status_code == 200 and "lila.fabulim" in um.headers["content-disposition"]
        assert len(json.loads(zipfile.ZipFile(io.BytesIO(um.content)).read("manifest.json"))["characters"]) == 1
        todos = client.get("/api/packages/characters")
        assert "personagens.fabulim" in todos.headers["content-disposition"]
        assert len(json.loads(zipfile.ZipFile(io.BytesIO(todos.content)).read("manifest.json"))["characters"]) == 2
        assert client.get("/api/packages/characters?id=xyz").status_code == 422
        assert client.get(f"/api/packages/characters?id={'0' * 32}").status_code == 404

    def test_importar_recusa_lixo_vazio_e_arquivo_grande(
        self, client: TestClient, servicos: Servicos, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lixo = client.post("/api/packages/import", content=b"isto nao e um pacote")
        assert lixo.status_code == 422 and "não é um zip válido" in lixo.json()["detail"]
        assert client.post("/api/packages/import", content=b"").status_code == 422
        monkeypatch.setattr(pacote, "LIMITE_TOTAL", 10)
        grande = client.post("/api/packages/import", content=b"x" * 100)
        assert grande.status_code == 413
        assert list(servicos.settings.temp_dir.glob("importar-*")) == []
        assert _nada_entrou(servicos)

    def test_importar_exige_origem_do_proprio_app(self, client: TestClient, tmp_path: Path) -> None:
        r = client.post("/api/packages/import", content=b"x", headers={"Origin": "http://evil.example"})
        assert r.status_code == 403  # a proteção contra CSRF vale para o envio de pacotes


def fluxos_recortes(sv: Servicos, personagem_id: str) -> dict[str, Any]:
    from app.personagens import fluxos

    return fluxos.recortes_por_slot(sv, personagem_id)
