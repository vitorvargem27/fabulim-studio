"""Biblioteca de mídias: adotar arquivos, miniaturas, consulta, remoção e segurança de caminhos."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest
from PIL import Image

from app.container import Servicos
from app.midias import RepositorioMidias
from app.security.caminhos import CaminhoInseguro


def _png(caminho: Path, tamanho: tuple[int, int] = (64, 48), rgba: bool = False) -> Path:
    if rgba:
        Image.new("RGBA", tamanho, (10, 200, 30, 128)).save(caminho, "PNG")
    else:
        Image.new("RGB", tamanho, (10, 200, 30)).save(caminho, "PNG")
    return caminho


def _wav(caminho: Path) -> Path:
    with wave.open(str(caminho), "wb") as arquivo:
        arquivo.setnchannels(1)
        arquivo.setsampwidth(2)
        arquivo.setframerate(8000)
        arquivo.writeframes(b"\x00\x00" * 8000)
    return caminho


@pytest.fixture
def midias(servicos: Servicos) -> RepositorioMidias:
    return servicos.midias


class TestAdotar:
    def test_move_o_arquivo_para_a_biblioteca_e_cria_a_miniatura(
        self, midias: RepositorioMidias, tmp_path: Path
    ) -> None:
        origem = _png(tmp_path / "gerada.png", (640, 360))
        midia = midias.adotar(origem, tipo="imagem", papel="cenario", prompt="um jardim", seed=7, estilo="2D")
        assert not origem.exists()  # foi movida
        assert midia.caminho.startswith("imagem/") and midia.caminho.endswith(f"{midia.id}.png")
        assert midias.caminho_absoluto(midia).is_file()
        assert (midia.largura, midia.altura, midia.formato) == (640, 360, "png")
        assert midia.tamanho_bytes > 0 and midia.prompt == "um jardim" and midia.seed == 7
        assert midia.miniatura and midia.miniatura.startswith("miniatura/") and midia.miniatura.endswith(".webp")
        miniatura = midias.caminho_da_miniatura(midia)
        assert miniatura is not None and miniatura.is_file()
        with Image.open(miniatura) as t:
            assert max(t.size) <= 384 and t.format == "WEBP"

    def test_copiar_mantem_a_origem(self, midias: RepositorioMidias, tmp_path: Path) -> None:
        origem = _png(tmp_path / "minha.png")
        midia = midias.adotar(origem, tipo="imagem", papel="upload", mover=False)
        assert origem.exists() and midias.caminho_absoluto(midia).is_file()

    def test_a_miniatura_guarda_a_transparencia_dos_recortes(self, midias: RepositorioMidias, tmp_path: Path) -> None:
        midia = midias.adotar(_png(tmp_path / "r.png", rgba=True), tipo="imagem", papel="recorte")
        miniatura = midias.caminho_da_miniatura(midia)
        assert miniatura is not None
        with Image.open(miniatura) as t:
            assert "A" in t.getbands()

    def test_audio_nao_tem_miniatura_e_video_usa_um_quadro(self, midias: RepositorioMidias, tmp_path: Path) -> None:
        audio = midias.adotar(_wav(tmp_path / "fala.wav"), tipo="audio", papel="fala", duracao_s=1.0)
        assert audio.miniatura is None and audio.duracao_s == 1.0 and audio.largura is None
        quadro = _png(tmp_path / "quadro.png")
        (tmp_path / "clipe.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
        video = midias.adotar(
            tmp_path / "clipe.mp4", tipo="video", papel="clipe", miniatura_de=quadro, largura=1280, altura=720
        )
        assert video.miniatura is not None and (video.largura, video.altura) == (1280, 720)

    def test_tipo_desconhecido_e_recusado(self, midias: RepositorioMidias, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="tipo de mídia"):
            midias.adotar(_png(tmp_path / "x.png"), tipo="planilha", papel="x")

    def test_para_api_usa_chaves_em_ingles_e_urls_do_servidor(self, midias: RepositorioMidias, tmp_path: Path) -> None:
        midia = midias.adotar(
            _png(tmp_path / "a.png"), tipo="imagem", papel="personagem", dono_tipo="personagem", dono_id="p1"
        )
        api = midia.para_api()
        assert api["url"] == f"/api/media/{midia.id}" and api["thumb_url"] == f"/api/media/{midia.id}/thumb"
        assert api["kind"] == "imagem" and api["role"] == "personagem" and api["owner_id"] == "p1"
        assert "caminho" not in api and "miniatura" not in api  # o caminho no disco nunca vai para a interface


class TestConsulta:
    def _criar(self, midias: RepositorioMidias, tmp_path: Path) -> list[str]:
        ids = []
        for i, (papel, prompt, dono) in enumerate(
            [
                ("cenario", "um jardim florido", None),
                ("cenario", "100% de chuva_forte", None),
                ("personagem", "coelha lilás", "p1"),
                ("recorte", "coelha lilás sem fundo", "p1"),
            ]
        ):
            midia = midias.adotar(
                _png(tmp_path / f"{i}.png"),
                tipo="imagem",
                papel=papel,
                prompt=prompt,
                dono_tipo="personagem" if dono else None,
                dono_id=dono,
            )
            ids.append(midia.id)
        return ids

    def test_listar_do_mais_novo_para_o_mais_antigo(self, midias: RepositorioMidias, tmp_path: Path) -> None:
        ids = self._criar(midias, tmp_path)
        assert [m.id for m in midias.listar()] == list(reversed(ids))
        assert midias.contar() == 4 and midias.contar(tipo="audio") == 0

    def test_filtros_por_tipo_papel_e_dono(self, midias: RepositorioMidias, tmp_path: Path) -> None:
        ids = self._criar(midias, tmp_path)
        assert len(midias.listar(tipo="imagem")) == 4 and midias.listar(tipo="video") == []
        assert {m.id for m in midias.listar(papeis=("cenario",))} == set(ids[:2])
        assert {m.id for m in midias.listar(papeis=("personagem", "recorte"))} == set(ids[2:])
        assert {m.id for m in midias.listar(dono_tipo="personagem", dono_id="p1")} == set(ids[2:])

    def test_o_filtro_de_dono_nenhum_devolve_so_as_avulsas(self, midias: RepositorioMidias, tmp_path: Path) -> None:
        ids = self._criar(midias, tmp_path)
        assert {m.id for m in midias.listar(dono_tipo="nenhum")} == set(ids[:2])
        assert midias.contar(dono_tipo="nenhum") == 2

    def test_busca_no_prompt_trata_percentual_e_sublinhado_como_texto(
        self, midias: RepositorioMidias, tmp_path: Path
    ) -> None:
        ids = self._criar(midias, tmp_path)
        assert [m.id for m in midias.listar(busca="jardim")] == [ids[0]]
        assert [m.id for m in midias.listar(busca="100%")] == [ids[1]]
        assert [m.id for m in midias.listar(busca="chuva_forte")] == [ids[1]]
        assert midias.listar(busca="%") == [midias.obter(ids[1])]  # só o que tem um "%" de verdade
        assert midias.listar(busca="chuva_forte'; DROP TABLE midias;--") == []
        assert midias.contar() == 4

    def test_paginacao(self, midias: RepositorioMidias, tmp_path: Path) -> None:
        ids = self._criar(midias, tmp_path)
        assert [m.id for m in midias.listar(limite=2)] == [ids[3], ids[2]]
        assert [m.id for m in midias.listar(limite=2, deslocamento=2)] == [ids[1], ids[0]]

    def test_obter_inexistente(self, midias: RepositorioMidias) -> None:
        assert midias.obter("0" * 32) is None


class TestAtualizarERemover:
    def test_metadados_sao_mesclados_e_o_papel_muda(self, midias: RepositorioMidias, tmp_path: Path) -> None:
        midia = midias.adotar(_png(tmp_path / "a.png"), tipo="imagem", papel="variacao", metadados={"a": 1})
        midias.atualizar_metadados(midia.id, b=2)
        midias.atualizar_papel(midia.id, "personagem")
        atual = midias.obter(midia.id)
        assert atual is not None and atual.metadados == {"a": 1, "b": 2} and atual.papel == "personagem"
        midias.atualizar_metadados("0" * 32, x=1)  # id que não existe: não faz nada

    def test_remover_apaga_o_registro_e_os_arquivos(self, midias: RepositorioMidias, tmp_path: Path) -> None:
        midia = midias.adotar(_png(tmp_path / "a.png"), tipo="imagem", papel="cenario")
        arquivo, miniatura = midias.caminho_absoluto(midia), midias.caminho_da_miniatura(midia)
        assert midias.remover(midia.id) is True
        assert midias.obter(midia.id) is None and not arquivo.exists()
        assert miniatura is not None and not miniatura.exists()
        assert midias.remover(midia.id) is False

    def test_remover_a_mae_deixa_a_filha_sem_pai(self, midias: RepositorioMidias, tmp_path: Path) -> None:
        mae = midias.adotar(_png(tmp_path / "m.png"), tipo="imagem", papel="personagem")
        filha = midias.adotar(_png(tmp_path / "f.png"), tipo="imagem", papel="recorte", pai_id=mae.id)
        midias.remover(mae.id)
        restante = midias.obter(filha.id)
        assert restante is not None and restante.pai_id is None

    def test_remover_do_dono(self, midias: RepositorioMidias, tmp_path: Path) -> None:
        for i in range(3):
            midias.adotar(_png(tmp_path / f"{i}.png"), tipo="imagem", papel="x", dono_tipo="personagem", dono_id="p1")
        outra = midias.adotar(_png(tmp_path / "z.png"), tipo="imagem", papel="x", dono_tipo="personagem", dono_id="p2")
        assert midias.remover_do_dono("personagem", "p1") == 3
        assert [m.id for m in midias.listar()] == [outra.id]


class TestSeguranca:
    def test_o_caminho_gravado_nao_pode_sair_da_pasta(
        self, midias: RepositorioMidias, servicos: Servicos, tmp_path: Path
    ) -> None:
        midia = midias.adotar(_png(tmp_path / "a.png"), tipo="imagem", papel="cenario")
        with servicos.db.transaction() as c:
            c.execute("UPDATE midias SET caminho = ? WHERE id = ?", ("../../fora.png", midia.id))
        adulterada = midias.obter(midia.id)
        assert adulterada is not None
        with pytest.raises(CaminhoInseguro):
            midias.caminho_absoluto(adulterada)
        with pytest.raises(CaminhoInseguro):
            midias.remover(midia.id)  # nunca apaga fora da pasta de mídias
