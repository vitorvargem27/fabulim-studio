"""Instalador de ferramentas e modelos: fonte oficial, SHA-256, retomada, zip seguro, detecção e a API da tela Modelos."""

from __future__ import annotations

import hashlib
import io
import json
import stat
import zipfile
from collections import namedtuple
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.container import Servicos
from app.ferramentas import detectar
from app.ferramentas.catalogo import ITENS, GitHub, HuggingFace, Item, por_id
from app.ferramentas.instalador import (
    ErroDeInstalacao,
    Instalador,
    Origem,
    SemHashOficial,
    baixar,
    extrair_zip,
    resolver_github,
    resolver_huggingface,
)
from app.jobs.handlers import instalar_ferramenta
from app.security.downloads import DownloadInseguro, HashDiferente

Uso = namedtuple("Uso", "total used free")


def sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def zip_de(arquivos: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for nome, dados in arquivos.items():
            zf.writestr(nome, dados)
    return buffer.getvalue()


def cliente_falso(tratar: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(tratar), follow_redirects=False)


class TestCatalogo:
    def test_todo_item_vem_de_fonte_oficial_e_tem_licenca(self) -> None:
        from app.security.downloads import fonte_oficial

        ids = [i.id for i in ITENS]
        assert len(ids) == len(set(ids))
        for item in ITENS:
            assert item.licenca and item.marcador and item.para
            dominio = "https://github.com/" if isinstance(item.fonte, GitHub) else "https://huggingface.co/"
            assert fonte_oficial(dominio)
            assert not item.destino.startswith(("/", "\\")) and ".." not in item.destino

    def test_licencas_permitem_uso_comercial(self) -> None:
        for item in ITENS:
            assert any(k in item.licenca for k in ("MIT", "Apache", "GPL")), item.id
            assert "NC" not in item.licenca and "non-commercial" not in item.licenca.lower()

    def test_por_id(self) -> None:
        assert por_id("ffmpeg").grupo == "ffmpeg"
        with pytest.raises(KeyError):
            por_id("nao-existe")


class TestResolucao:
    def test_github_escolhe_a_versao_mais_alta_e_exige_o_hash(self) -> None:
        release = {
            "tag_name": "latest",
            "published_at": "2026-09-29T13:30:47Z",
            "assets": [
                {
                    "name": "ffmpeg-n8.1-latest-win64-gpl-8.1.zip",
                    "size": 10,
                    "digest": "sha256:" + "a" * 64,
                    "browser_download_url": "https://github.com/x/8.zip",
                },
                {
                    "name": "ffmpeg-n9.0-latest-win64-gpl-9.0.zip",
                    "size": 20,
                    "digest": "sha256:" + "b" * 64,
                    "browser_download_url": "https://github.com/x/9.zip",
                },
                {
                    "name": "ffmpeg-n9.0-latest-win64-lgpl-9.0.zip",
                    "size": 30,
                    "digest": "sha256:" + "c" * 64,
                    "browser_download_url": "https://github.com/x/l.zip",
                },
            ],
        }
        cliente = cliente_falso(lambda req: httpx.Response(200, json=release))
        origem = resolver_github(cliente, por_id("ffmpeg").fonte)  # type: ignore[arg-type]
        assert origem.url.endswith("9.zip") and origem.sha256 == "b" * 64 and origem.tamanho == 20
        assert "2026-09-29" in origem.versao

    def test_github_sem_hash_publicado_nao_instala(self) -> None:
        release = {
            "assets": [
                {
                    "name": "kokoro-v1.0.onnx",
                    "size": 1,
                    "digest": None,
                    "browser_download_url": "https://github.com/x/k",
                }
            ]
        }
        cliente = cliente_falso(lambda req: httpx.Response(200, json=release))
        with pytest.raises(SemHashOficial):
            resolver_github(cliente, GitHub("a/b", "t", r"^kokoro-v1\.0\.onnx$"))

    def test_github_sem_arquivo_que_combine(self) -> None:
        cliente = cliente_falso(lambda req: httpx.Response(200, json={"assets": []}))
        with pytest.raises(ErroDeInstalacao, match="não tem um arquivo"):
            resolver_github(cliente, GitHub("a/b", "t", r"^x$"))

    def test_huggingface_fixa_o_commit_e_usa_o_hash_do_lfs(self) -> None:
        commit = "c" * 40
        oid = "d" * 64

        def tratar(req: httpx.Request) -> httpx.Response:
            if req.url.path == "/api/models/org/modelo":
                return httpx.Response(200, json={"sha": commit, "gated": False})
            assert req.url.path == f"/api/models/org/modelo/tree/{commit}/onnx"
            return httpx.Response(
                200, json=[{"type": "file", "path": "onnx/model.onnx", "size": 99, "lfs": {"oid": oid}}]
            )

        origem = resolver_huggingface(cliente_falso(tratar), HuggingFace("org/modelo", "onnx/model.onnx"))
        assert origem.url == f"https://huggingface.co/org/modelo/resolve/{commit}/onnx/model.onnx"
        assert origem.sha256 == oid and origem.tamanho == 99 and commit[:10] in origem.versao

    def test_huggingface_recusa_repositorio_que_pede_login(self) -> None:
        cliente = cliente_falso(lambda req: httpx.Response(200, json={"sha": "1" * 40, "gated": "auto"}))
        with pytest.raises(ErroDeInstalacao, match="login"):
            resolver_huggingface(cliente, HuggingFace("org/fechado", "a.gguf"))

    def test_huggingface_sem_hash_oficial(self) -> None:
        def tratar(req: httpx.Request) -> httpx.Response:
            if req.url.path.endswith("/x"):
                return httpx.Response(200, json={"sha": "1" * 40})
            return httpx.Response(200, json=[{"type": "file", "path": "a.gguf", "size": 5}])

        with pytest.raises(SemHashOficial):
            resolver_huggingface(cliente_falso(tratar), HuggingFace("org/x", "a.gguf"))


class TestDownload:
    def test_segue_redirecionamentos_oficiais(self, tmp_path: Path) -> None:
        conteudo = b"pesos" * 1000

        def tratar(req: httpx.Request) -> httpx.Response:
            if req.url.host == "github.com":
                return httpx.Response(
                    302, headers={"location": "https://objects.githubusercontent.com/arquivo?token=1"}
                )
            return httpx.Response(200, content=conteudo)

        destino = tmp_path / "m.parte"
        baixar(cliente_falso(tratar), Origem("https://github.com/x/m", sha(conteudo), len(conteudo), "v1"), destino)
        assert destino.read_bytes() == conteudo

    def test_recusa_redirecionamento_para_fora_das_fontes_oficiais(self, tmp_path: Path) -> None:
        def tratar(req: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "https://site-malicioso.example/baixar"})

        with pytest.raises(DownloadInseguro, match="fora das fontes oficiais"):
            baixar(cliente_falso(tratar), Origem("https://github.com/x/m", "0" * 64, 10, "v"), tmp_path / "m.parte")

    def test_recusa_http_simples(self, tmp_path: Path) -> None:
        with pytest.raises(DownloadInseguro):
            baixar(
                cliente_falso(lambda req: httpx.Response(200)),
                Origem("http://github.com/x/m", "0" * 64, 10, "v"),
                tmp_path / "m.parte",
            )

    def test_retoma_de_onde_parou(self, tmp_path: Path) -> None:
        conteudo = bytes(range(256)) * 40
        pedidos: list[str | None] = []

        def tratar(req: httpx.Request) -> httpx.Response:
            faixa = req.headers.get("range")
            pedidos.append(faixa)
            inicio = int(faixa.removeprefix("bytes=").split("-")[0]) if faixa else 0
            return httpx.Response(206 if faixa else 200, content=conteudo[inicio:])

        parcial = tmp_path / "m.parte"
        parcial.write_bytes(conteudo[:3000])
        baixar(cliente_falso(tratar), Origem("https://github.com/x/m", sha(conteudo), len(conteudo), "v"), parcial)
        assert pedidos == ["bytes=3000-"] and parcial.read_bytes() == conteudo

    def test_servidor_que_ignora_a_retomada_recomeca_do_zero(self, tmp_path: Path) -> None:
        conteudo = b"abcdefgh" * 500
        parcial = tmp_path / "m.parte"
        parcial.write_bytes(b"lixo antigo")
        baixar(
            cliente_falso(lambda req: httpx.Response(200, content=conteudo)),
            Origem("https://github.com/x/m", sha(conteudo), len(conteudo), "v"),
            parcial,
        )
        assert parcial.read_bytes() == conteudo

    def test_relata_o_progresso(self, tmp_path: Path) -> None:
        conteudo = b"x" * (3 * 1024 * 1024)
        etapas: list[tuple[str, int, int]] = []
        baixar(
            cliente_falso(lambda req: httpx.Response(200, content=conteudo)),
            Origem("https://github.com/x/m", sha(conteudo), len(conteudo), "v"),
            tmp_path / "m.parte",
            lambda etapa, feitos, total: etapas.append((etapa, feitos, total)),
        )
        assert etapas[-1] == ("baixando", len(conteudo), len(conteudo)) and len(etapas) >= 2


class TestZip:
    def test_extrai_e_sobe_a_pasta_unica_da_raiz(self, tmp_path: Path) -> None:
        pacote = tmp_path / "p.zip"
        pacote.write_bytes(zip_de({"ffmpeg-9.0/bin/ffmpeg.exe": b"exe", "ffmpeg-9.0/LICENSE": b"gpl"}))
        n = extrair_zip(pacote, tmp_path / "saida", remover_pasta_raiz=True)
        assert n == 2 and (tmp_path / "saida" / "bin" / "ffmpeg.exe").read_bytes() == b"exe"

    def test_sem_remover_a_raiz_mantem_as_pastas(self, tmp_path: Path) -> None:
        pacote = tmp_path / "p.zip"
        pacote.write_bytes(zip_de({"a/x.txt": b"1"}))
        extrair_zip(pacote, tmp_path / "saida")
        assert (tmp_path / "saida" / "a" / "x.txt").exists()

    @pytest.mark.parametrize("nome", ["../fora.txt", "a/../../fora.txt", "/abs.txt", "C:/abs.txt", "\\\\servidor\\x"])
    def test_zip_slip_e_barrado(self, tmp_path: Path, nome: str) -> None:
        pacote = tmp_path / "p.zip"
        pacote.write_bytes(zip_de({nome: b"mal"}))
        with pytest.raises(ValueError):
            extrair_zip(pacote, tmp_path / "saida")
        assert not (tmp_path / "fora.txt").exists()

    def test_link_simbolico_dentro_do_pacote_e_barrado(self, tmp_path: Path) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            info = zipfile.ZipInfo("atalho")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, "/etc/passwd")
        pacote = tmp_path / "p.zip"
        pacote.write_bytes(buffer.getvalue())
        with pytest.raises(DownloadInseguro, match="link simbólico"):
            extrair_zip(pacote, tmp_path / "saida")

    def test_zip_bomb_e_barrado(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.ferramentas.instalador.LIMITE_DESCOMPACTADO", 100)
        pacote = tmp_path / "p.zip"
        pacote.write_bytes(zip_de({"a.bin": b"0" * 1000}))
        with pytest.raises(DownloadInseguro, match="zip bomb"):
            extrair_zip(pacote, tmp_path / "saida")


def item_de_teste(**mudancas: Any) -> Item:
    base: dict[str, Any] = {
        "id": "modelo-teste",
        "nome": "Modelo de teste",
        "para": "testar",
        "fonte": HuggingFace("org/modelo", "m.gguf"),
        "licenca": "Apache-2.0",
        "base": "models",
        "destino": "teste/m.gguf",
        "marcador": "teste/m.gguf",
    }
    return Item(**{**base, **mudancas})


def instalador_com(settings: Settings, item: Item, conteudo: bytes, *, hash_publicado: str | None = None) -> Instalador:
    """Instalador cujo único servidor é falso: a API devolve `hash_publicado` e o download devolve `conteudo`."""
    oid = hash_publicado or sha(conteudo)

    def tratar(req: httpx.Request) -> httpx.Response:
        if (
            req.url.host == "huggingface.co"
            and req.url.path.startswith("/api/models/")
            and "/tree/" not in req.url.path
        ):
            return httpx.Response(200, json={"sha": "e" * 40})
        if "/tree/" in req.url.path:
            return httpx.Response(
                200, json=[{"type": "file", "path": "m.gguf", "size": len(conteudo), "lfs": {"oid": oid}}]
            )
        if "/resolve/" in req.url.path:
            return httpx.Response(200, content=conteudo)
        if req.url.host == "api.github.com":
            return httpx.Response(
                200,
                json={
                    "published_at": "2026-01-01T00:00:00Z",
                    "assets": [
                        {
                            "name": "p.zip",
                            "size": len(conteudo),
                            "digest": "sha256:" + oid,
                            "browser_download_url": "https://github.com/o/r/releases/download/t/p.zip",
                        }
                    ],
                },
            )
        return httpx.Response(200, content=conteudo)

    return Instalador(settings, cliente_falso(tratar))


class TestInstalar:
    def test_instala_um_modelo_e_registra_no_manifesto(self, settings: Settings) -> None:
        item = item_de_teste()
        conteudo = b"pesos do modelo" * 100
        resultado = instalador_com(settings, item, conteudo).instalar(item)
        assert resultado.situacao == "instalado" and resultado.arquivo is not None
        assert resultado.arquivo.read_bytes() == conteudo
        registro = json.loads((settings.models_dir / "manifesto.json").read_text(encoding="utf-8"))[0]
        assert (
            registro["sha256"] == sha(conteudo)
            and registro["license"] == "Apache-2.0"
            and registro["size_bytes"] == len(conteudo)
        )
        assert "huggingface.co" in registro["url"]

    def test_segunda_vez_nao_baixa_de_novo(self, settings: Settings) -> None:
        item = item_de_teste()
        instalador = instalador_com(settings, item, b"x" * 50)
        instalador.instalar(item)
        assert instalador.instalar(item).situacao == "ja_instalado"

    def test_hash_diferente_apaga_o_arquivo_e_falha(self, settings: Settings) -> None:
        item = item_de_teste()
        instalador = instalador_com(settings, item, b"conteudo adulterado", hash_publicado="0" * 64)
        with pytest.raises(HashDiferente):
            instalador.instalar(item)
        assert not (settings.models_dir / "teste" / "m.gguf").exists()
        assert not instalador.instalado(item)

    def test_formato_perigoso_e_recusado(self, settings: Settings) -> None:
        item = item_de_teste(destino="teste/m.ckpt", marcador="teste/m.ckpt", fonte=HuggingFace("org/modelo", "m.gguf"))
        with pytest.raises(DownloadInseguro, match="formato não permitido"):
            instalador_com(settings, item, b"pickle").instalar(item)
        assert not (settings.models_dir / "teste" / "m.ckpt").exists()

    def test_programa_compactado_e_extraido_e_o_zip_some(self, settings: Settings) -> None:
        pacote = zip_de({"ffmpeg-9.0/bin/ffmpeg.exe": b"exe", "ffmpeg-9.0/README": b"oi"})
        item = item_de_teste(
            id="prog",
            fonte=GitHub("o/r", "t", r"^p\.zip$"),
            base="tools",
            destino="prog",
            marcador="prog/bin/ffmpeg.exe",
            compactado=True,
            remover_pasta_raiz=True,
        )
        instalador = instalador_com(settings, item, pacote)
        assert instalador.instalar(item).situacao == "instalado"
        assert (settings.tools_dir / "prog" / "bin" / "ffmpeg.exe").read_bytes() == b"exe"
        assert not list((settings.tools_dir / ".downloads").glob("*.zip"))
        assert instalador.tamanho(item) == len(b"exe") + len(b"oi")

    def test_pacote_que_mudou_de_formato_avisa(self, settings: Settings) -> None:
        item = item_de_teste(
            fonte=GitHub("o/r", "t", r"^p\.zip$"),
            base="tools",
            destino="prog",
            marcador="prog/nao-existe.exe",
            compactado=True,
        )
        with pytest.raises(ErroDeInstalacao, match="mudou de formato"):
            instalador_com(settings, item, zip_de({"x.txt": b"1"})).instalar(item)

    def test_pouco_espaco_em_disco_avisa_antes_de_baixar(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        item = item_de_teste()
        monkeypatch.setattr("app.ferramentas.instalador.shutil.disk_usage", lambda _p: Uso(10**12, 10**12 - 1000, 1000))
        with pytest.raises(ErroDeInstalacao, match="pouco espaço em disco"):
            instalador_com(settings, item, b"x" * 10).instalar(item)

    def test_vozes_com_codigo_escondido_sao_barradas(self, settings: Settings) -> None:
        """O arquivo de vozes do Kokoro é .npz: se não abrir como dado puro (sem pickle), é apagado."""
        item = item_de_teste(
            id="kokoro-vozes",
            fonte=HuggingFace("org/modelo", "m.gguf"),
            destino="voz/voices.bin",
            marcador="voz/voices.bin",
            permitir_pickle=True,
        )
        with pytest.raises(DownloadInseguro, match="dados puros"):
            instalador_com(settings, item, b"isto nao e um npz").instalar(item)
        assert not (settings.models_dir / "voz" / "voices.bin").exists()

    def test_situacao_lista_todo_o_catalogo(self, settings: Settings) -> None:
        situacao = Instalador(settings).situacao()
        assert [s["id"] for s in situacao] == [i.id for i in ITENS]
        assert all(s["installed"] for s in situacao)  # a fixture instala tudo (arquivos de mentira)
        assert all(s["size_bytes"] for s in situacao)
        assert not any(s["size_estimated"] for s in situacao)  # instalado: o tamanho é o do disco, não uma estimativa

    def test_antes_de_instalar_mostra_o_tamanho_aproximado_do_download(self, settings: Settings) -> None:
        (settings.models_dir / "voz" / "kokoro-v1.0.onnx").unlink()
        kokoro = next(s for s in Instalador(settings).situacao() if s["id"] == "kokoro-modelo")
        assert kokoro["installed"] is False and kokoro["size_estimated"] is True
        assert kokoro["size_bytes"] == por_id("kokoro-modelo").aprox_bytes

    def test_todo_item_do_catalogo_informa_o_tamanho_do_download(self) -> None:
        """A tela mostra o tamanho antes de instalar: nenhum item pode ficar sem esse número (nem ser absurdo)."""
        for item in ITENS:
            assert 10 * 1024**2 < item.aprox_bytes < 4 * 1024**3, item.id


class TestDeteccao:
    def test_todos_os_motores_prontos(self, settings: Settings) -> None:
        assert detectar.motores_instalados(settings) == {"imagem", "voz", "recorte"}

    def test_falta_um_arquivo_do_motor_de_imagem(self, settings: Settings) -> None:
        (settings.models_dir / "imagem" / "Qwen3-4B-Q4_K_M.gguf").unlink()
        assert "imagem" not in detectar.motores_instalados(settings)
        assert detectar.faltando(settings, "imagem") == ["Qwen3 4B (entende o texto das imagens)"]

    def test_falta_a_biblioteca_python(self, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.ferramentas.detectar.tem_modulo", lambda nome: nome != "kokoro_onnx")
        assert "voz" not in detectar.motores_instalados(settings)
        assert detectar.faltando(settings, "voz") == ["biblioteca Python kokoro_onnx"]

    def test_nada_instalado(self, tmp_path: Path, settings: Settings) -> None:
        for arquivo in [*settings.tools_dir.rglob("*"), *settings.models_dir.rglob("*")]:
            if arquivo.is_file():
                arquivo.unlink()
        assert detectar.motores_instalados(settings) == set()


class TestApiDasFerramentas:
    def test_lista_o_catalogo_com_o_estado(self, client: TestClient) -> None:
        dados = client.get("/api/tools").json()
        assert len(dados["items"]) == len(ITENS) and dados["items"][0]["id"] == "ffmpeg"
        assert all(i["installed"] and i["job_id"] is None for i in dados["items"])

    def test_instalar_enfileira_um_job_e_nao_duplica(self, client: TestClient, servicos: Servicos) -> None:
        marcador = servicos.settings.tools_dir / "ffmpeg" / "bin" / "ffmpeg.exe"
        marcador.unlink()
        primeiro = client.post("/api/tools/ffmpeg/install")
        assert primeiro.status_code == 202 and primeiro.json()["kind"] == "ferramentas.instalar"
        assert primeiro.json()["params"] == {"id": "ffmpeg"}
        segundo = client.post("/api/tools/ffmpeg/install")
        assert segundo.json()["id"] == primeiro.json()["id"]
        lista = {i["id"]: i for i in client.get("/api/tools").json()["items"]}
        assert lista["ffmpeg"]["installed"] is False and lista["ffmpeg"]["job_id"] == primeiro.json()["id"]

    def test_item_desconhecido_ja_instalado_e_id_invalido(self, client: TestClient) -> None:
        assert client.post("/api/tools/nao-existe/install").status_code == 404
        assert client.post("/api/tools/ffmpeg/install").status_code == 409  # a fixture já o instalou
        assert client.post("/api/tools/..%2Fetc/install").status_code in (404, 422)
        assert client.post("/api/tools/FFMPEG/install").status_code == 422

    def test_instalar_de_outro_site_e_barrado(self, client: TestClient) -> None:
        resposta = client.post("/api/tools/ffmpeg/install", headers={"Origin": "http://site-malicioso.example"})
        assert resposta.status_code == 403

    def test_meta_mostra_a_pasta_de_programas(self, client: TestClient, servicos: Servicos) -> None:
        assert client.get("/api/meta").json()["tools_dir"] == str(servicos.settings.tools_dir)


class TestHandlerDeInstalacao:
    def _contexto(self, servicos: Servicos) -> Any:
        registros: list[tuple[float, str | None]] = []

        class Ctx:
            def __init__(self) -> None:
                self.servicos = servicos
                self.mensagens = registros

            def progresso(self, fracao: float, mensagem: str | None = None) -> None:
                registros.append((fracao, mensagem))

            def log(self, mensagem: str, nivel: str = "INFO") -> None:
                registros.append((-1, mensagem))

            def ponto_de_controle(self) -> None:
                return None

        return Ctx()

    def test_instala_mostra_o_progresso_e_pede_o_diagnostico_leve(
        self, servicos: Servicos, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        instalado: list[str] = []

        class Falso:
            def __init__(self, settings: Settings) -> None:
                pass

            def instalar(self, item: Item, progresso: Any) -> Any:
                progresso("consultando a fonte oficial", 0, 0)
                progresso("baixando", 500_000_000, 1_000_000_000)
                progresso("conferindo o SHA-256", 1, 1)
                instalado.append(item.id)
                return type("R", (), {"situacao": "instalado"})()

        monkeypatch.setattr("app.jobs.handlers.Instalador", Falso)
        ctx = self._contexto(servicos)
        resultado = instalar_ferramenta(ctx, {"id": "ffmpeg"})
        assert resultado == {"id": "ffmpeg", "status": "instalado"} and instalado == ["ffmpeg"]
        progressos = [p for p in ctx.mensagens if p[0] >= 0]
        assert any("500 de 1000 MB" in (m or "") for _, m in progressos) and progressos[-1][0] == 1.0
        diagnosticos = [j for j in servicos.store.listar() if j.kind == "system.diagnostico"]
        assert len(diagnosticos) == 1 and diagnosticos[0].params == {"leve": True}

    def test_falha_vira_erro_legivel(self, servicos: Servicos, monkeypatch: pytest.MonkeyPatch) -> None:
        class Quebrado:
            def __init__(self, settings: Settings) -> None:
                pass

            def instalar(self, item: Item, progresso: Any) -> Any:
                raise ErroDeInstalacao("pouco espaço em disco")

        monkeypatch.setattr("app.jobs.handlers.Instalador", Quebrado)
        with pytest.raises(RuntimeError, match="pouco espaço em disco"):
            instalar_ferramenta(self._contexto(servicos), {"id": "ffmpeg"})

    def test_id_desconhecido(self, servicos: Servicos) -> None:
        with pytest.raises(RuntimeError, match="desconhecida"):
            instalar_ferramenta(self._contexto(servicos), {"id": "nada"})


class TestMotoresNoStatusENasCapacidades:
    def test_motores_prontos_aparecem_como_funcionando(self, servicos: Servicos) -> None:
        from app.services.status import EstadoServico, coletar_status

        por_id = {s.id: s for s in coletar_status(servicos).services}
        for id_ in ("image_engine", "tts_engine", "cutout_engine"):
            assert por_id[id_].state == EstadoServico.OK and por_id[id_].summary == "Instalado"

    def test_motor_ausente_ensina_onde_instalar(self, servicos: Servicos) -> None:
        from app.services.status import EstadoServico, coletar_status

        for pasta in (servicos.settings.models_dir, servicos.settings.tools_dir):
            for arquivo in pasta.rglob("*"):
                if arquivo.is_file():
                    arquivo.unlink()
        por_id = {s.id: s for s in coletar_status(servicos).services}
        for id_ in ("image_engine", "tts_engine", "cutout_engine"):
            # nada instalado é "ainda não instalado", não "incompleto": as bibliotecas Python vêm com o app e não contam
            assert por_id[id_].state == EstadoServico.INACTIVE and por_id[id_].summary == "Ainda não instalado", id_
            assert any("Modelos" in passo for passo in por_id[id_].how_to_fix), id_

    def test_instalacao_incompleta_e_um_aviso(self, servicos: Servicos) -> None:
        from app.services.status import EstadoServico, coletar_status

        (servicos.settings.models_dir / "imagem" / "flux2-vae.safetensors").unlink()
        s = {s.id: s for s in coletar_status(servicos).services}["image_engine"]
        assert s.state == EstadoServico.WARNING and s.detail is not None and "small-decoder" in s.detail
        assert any("Modelos" in passo for passo in s.how_to_fix)

    def test_arquivos_instalados_mas_sem_a_biblioteca_python_ensina_o_pip(
        self, servicos: Servicos, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.status import EstadoServico, coletar_status

        monkeypatch.setattr("app.ferramentas.detectar.tem_modulo", lambda nome: nome != "kokoro_onnx")
        s = {s.id: s for s in coletar_status(servicos).services}["tts_engine"]
        assert s.state == EstadoServico.WARNING and s.detail == "Falta: biblioteca Python kokoro_onnx"
        assert s.how_to_fix and "pip install -r backend" in s.how_to_fix[0]
        assert not any("Modelos" in passo for passo in s.how_to_fix)  # os arquivos já estão lá: o caminho é outro

    def test_sem_arquivos_e_sem_biblioteca_continua_sendo_so_nao_instalado(
        self, servicos: Servicos, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.status import EstadoServico, coletar_status

        for arquivo in (servicos.settings.models_dir / "voz").rglob("*"):
            arquivo.unlink()
        monkeypatch.setattr("app.ferramentas.detectar.tem_modulo", lambda _nome: False)
        s = {s.id: s for s in coletar_status(servicos).services}["tts_engine"]
        assert s.state == EstadoServico.INACTIVE and s.summary == "Ainda não instalado"

    def test_um_arquivo_de_dois_e_incompleto(self, servicos: Servicos) -> None:
        from app.services.status import EstadoServico, coletar_status

        (servicos.settings.models_dir / "voz" / "voices-v1.0.bin").unlink()
        s = {s.id: s for s in coletar_status(servicos).services}["tts_engine"]
        assert s.state == EstadoServico.WARNING and s.detail == "Falta: Vozes do Kokoro"

    def test_capacidades_sem_motor_ficam_indisponiveis_com_o_caminho_para_instalar(self, servicos: Servicos) -> None:
        for arquivo in (servicos.settings.models_dir / "voz").rglob("*"):
            arquivo.unlink()
        caps = {c["id"]: c for c in servicos.hardware.snapshot()["capabilities"]}
        assert caps["voz"]["state"] == "unavailable" and "Modelos" in caps["voz"]["reason"]
        assert caps["imagem"]["state"] == "slow"  # o motor de imagem continua instalado

    def test_a_animacao_por_codigo_precisa_de_node_e_ffmpeg(self, servicos: Servicos) -> None:
        from app.services.status import EstadoServico, coletar_status

        por_id = {s.id: s for s in coletar_status(servicos).services}
        assert por_id["animation_engine"].state in (EstadoServico.OK, EstadoServico.INACTIVE)
