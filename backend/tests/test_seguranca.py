"""Segurança (briefing, seção 11 e 12.4): loopback, Host, CORS, CSRF, cabeçalhos, código perigoso e servidor real."""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import ClassVar

import httpx
import pytest
from fastapi.testclient import TestClient

from app.security.caminhos import (
    CaminhoInseguro,
    dentro_da_pasta,
    entrada_de_pacote_segura,
    nome_de_arquivo_seguro,
)
from app.security.downloads import (
    DownloadInseguro,
    HashDiferente,
    ManifestoDeDownloads,
    fonte_oficial,
    formato_permitido,
    sha256_arquivo,
    verificar_sha256,
)
from app.security.uploads import UploadInvalido, tipo_real_da_imagem, validar_upload_imagem

from .conftest import RAIZ

ORIGEM_OK = "http://127.0.0.1:8765"
ORIGEM_MA = "http://site-malicioso.example"


class TestRedeEOrigem:
    def test_host_estranho_e_recusado(self, client: TestClient) -> None:
        for host in ("evil.com", "127.0.0.1.evil.com", "192.168.0.10:8765", "attacker.local"):
            r = client.get("/api/health", headers={"Host": host})
            assert r.status_code == 400, host

    def test_hosts_locais_passam(self, client: TestClient) -> None:
        for host in ("127.0.0.1:8765", "localhost:8765", "localhost"):
            assert client.get("/api/health", headers={"Host": host}).status_code == 200, host

    def test_post_de_outro_site_e_barrado_mesmo_sem_cors(self, client: TestClient) -> None:
        # Um formulário ou fetch "simples" de outro site não faz preflight: só a checagem de origem o para.
        for rota in ("/api/benchmark/run", "/api/machine/diagnostic", "/api/jobs/" + "0" * 32 + "/cancel"):
            r = client.post(rota, headers={"Origin": ORIGEM_MA})
            assert r.status_code == 403, rota
        assert client.post("/api/benchmark/run", headers={"Origin": "null"}).status_code == 403
        assert client.post("/api/benchmark/run", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
        assert client.delete("/api/jobs/finished", headers={"Origin": ORIGEM_MA}).status_code == 403
        assert client.get("/api/jobs").json() == []  # nada foi enfileirado

    def test_post_do_proprio_app_ou_de_ferramentas_locais_passa(self, client: TestClient) -> None:
        assert client.post("/api/benchmark/run", headers={"Origin": ORIGEM_OK}).status_code == 202
        assert client.post("/api/machine/diagnostic", headers={"Origin": "http://localhost:4200"}).status_code == 202
        assert client.post("/api/machine/diagnostic").status_code == 202  # curl e testes não mandam Origin

    def test_cors_so_libera_o_frontend_local(self, client: TestClient) -> None:
        ruim = client.options("/api/jobs", headers={"Origin": ORIGEM_MA, "Access-Control-Request-Method": "POST"})
        assert "access-control-allow-origin" not in ruim.headers
        bom = client.options("/api/jobs", headers={"Origin": ORIGEM_OK, "Access-Control-Request-Method": "POST"})
        assert bom.headers["access-control-allow-origin"] == ORIGEM_OK
        leitura = client.get("/api/status", headers={"Origin": ORIGEM_MA})
        assert "access-control-allow-origin" not in leitura.headers  # o outro site não consegue ler a resposta

    def test_cabecalhos_de_seguranca(self, client: TestClient) -> None:
        h = client.get("/api/health").headers
        assert h["x-content-type-options"] == "nosniff"
        assert h["x-frame-options"] == "DENY"
        assert h["referrer-policy"] == "no-referrer"
        csp = h["content-security-policy"]
        assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp
        assert "http" not in csp.replace("'self'", "")  # nada de CDN ou domínio externo

    def test_erro_interno_nao_vaza_detalhes(self, client: TestClient) -> None:
        r = client.get("/api/jobs?limit=abc")
        assert r.status_code == 422 and "Traceback" not in r.text


class TestCodigoPerigoso:
    """Guarda estática: o briefing proíbe shell=True, eval/exec e pickle no código do app."""

    PADROES: ClassVar[dict[str, re.Pattern[str]]] = {
        "shell=True": re.compile(r"shell\s*=\s*True"),
        "os.system": re.compile(r"\bos\.system\s*\("),
        "os.popen": re.compile(r"\bos\.popen\s*\("),
        "eval": re.compile(r"(?<![\w.])eval\s*\("),
        "exec": re.compile(r"(?<![\w.])exec\s*\("),
        "pickle": re.compile(r"\b(pickle|cPickle|marshal)\.loads?\s*\("),
        "yaml.load": re.compile(r"\byaml\.load\s*\("),
        "torch.load": re.compile(r"\btorch\.load\s*\((?![^)]*weights_only\s*=\s*True)"),
    }

    def _arquivos(self) -> list[Path]:
        return [*RAIZ.glob("backend/app/**/*.py"), *RAIZ.glob("scripts/*.py")]

    def test_nenhum_padrao_perigoso(self) -> None:
        achados = []
        for arquivo in self._arquivos():
            texto = arquivo.read_text(encoding="utf-8")
            for nome, padrao in self.PADROES.items():
                if padrao.search(texto):
                    achados.append(f"{arquivo.relative_to(RAIZ)}: {nome}")
        assert achados == []

    def test_a_guarda_funciona(self) -> None:
        assert self.PADROES["shell=True"].search("subprocess.run(cmd, shell=True)")
        assert self.PADROES["eval"].search("x = eval(entrada)")
        assert not self.PADROES["eval"].search("avaliar(x); retrieval(x)")

    def test_ps1_e_sh_nao_executam_texto_externo(self) -> None:
        ps1 = (RAIZ / "scripts" / "diagnostico.ps1").read_text(encoding="utf-8-sig")
        assert "Invoke-Expression" not in ps1 and "iex " not in ps1.lower()
        assert not re.search(r"\beval\b", (RAIZ / "scripts" / "diagnostico.sh").read_text(encoding="utf-8"))


class TestCredenciaisDoClaude:
    """Briefing 11 e 15.2: nada de ler credenciais do Claude Code, fazer OAuth próprio ou usar client IDs da Anthropic.

    O único contato permitido com a conta é o comando oficial `claude auth status` (só o estado, sem e-mail nem tokens).
    """

    PADROES: ClassVar[dict[str, re.Pattern[str]]] = {
        "arquivo de credenciais do Claude Code": re.compile(r"\.credentials\.json|\.claude\.json", re.IGNORECASE),
        "cofre de credenciais do Claude Code": re.compile(r"Claude Code-credentials", re.IGNORECASE),
        "fluxo OAuth próprio": re.compile(
            r"grant_type|refresh_token|access_token|oauth/(authorize|token)", re.IGNORECASE
        ),
        "client ID": re.compile(r"client[_-]?id", re.IGNORECASE),
    }

    def _arquivos(self) -> list[Path]:
        return [
            *RAIZ.glob("backend/app/**/*.py"),
            *RAIZ.glob("scripts/**/*.py"),
            *RAIZ.glob("scripts/*.ps1"),
            *RAIZ.glob("scripts/*.sh"),
            *(p for p in RAIZ.glob("frontend/src/**/*.ts") if not p.name.endswith(".spec.ts")),
            *RAIZ.glob("frontend/src/**/*.html"),
        ]

    def test_nenhum_acesso_a_credenciais_ou_oauth_proprio(self) -> None:
        achados = []
        for arquivo in self._arquivos():
            texto = arquivo.read_text(encoding="utf-8-sig")
            for nome, padrao in self.PADROES.items():
                if padrao.search(texto):
                    achados.append(f"{arquivo.relative_to(RAIZ)}: {nome}")
        assert achados == []

    def test_a_guarda_funciona(self) -> None:
        assert self.PADROES["arquivo de credenciais do Claude Code"].search(
            r"open(home / '.claude' / '.credentials.json')"
        )
        assert self.PADROES["cofre de credenciais do Claude Code"].search(
            "security find-generic-password -s 'Claude Code-credentials'"
        )
        assert self.PADROES["fluxo OAuth próprio"].search("data = {'grant_type': 'refresh_token'}")
        assert self.PADROES["client ID"].search("CLIENT_ID = 'abc'")
        assert not self.PADROES["client ID"].search("client.get('/api/status')")

    def test_o_coletor_so_usa_o_comando_oficial(self) -> None:
        ps1 = (RAIZ / "scripts" / "diagnostico.ps1").read_text(encoding="utf-8-sig")
        sh = (RAIZ / "scripts" / "diagnostico.sh").read_text(encoding="utf-8")
        assert re.search(r"auth\s+status", ps1) and re.search(r"auth\s+status", sh)


class TestCaminhos:
    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            ("../../etc/passwd", "passwd"),
            ("..\\..\\Windows\\system32\\config", "config"),
            ("C:\\Users\\x\\foto.png", "foto.png"),
            ("/abs/caminho/arquivo.mp4", "arquivo.mp4"),
            ("nome com espaços.png", "nome_com_espaços.png"),
            ("CON", "_CON"),
            ("nul.txt", "_nul.txt"),
            ("...", "arquivo"),
            ("", "arquivo"),
            ("a<b>c:d|e?f*g.png", "abcdefg.png"),
            ("com\x00nulo.png", "comnulo.png"),
            (".oculto", "oculto"),
        ],
    )
    def test_nome_de_arquivo_seguro(self, entrada: str, esperado: str) -> None:
        assert nome_de_arquivo_seguro(entrada) == esperado

    def test_nome_muito_longo_e_cortado_mantendo_a_extensao(self) -> None:
        nome = nome_de_arquivo_seguro("a" * 500 + ".png", max_len=50)
        assert len(nome) <= 50 and nome.endswith(".png")

    def test_dentro_da_pasta(self, tmp_path: Path) -> None:
        assert dentro_da_pasta(tmp_path, "sub/arquivo.txt") == (tmp_path / "sub" / "arquivo.txt").resolve()
        for ruim in (
            "../fora.txt",
            "sub/../../fora.txt",
            str(tmp_path.parent / "fora.txt"),
            "/etc/passwd",
            "C:\\Windows",
        ):
            with pytest.raises(CaminhoInseguro):
                dentro_da_pasta(tmp_path, ruim)

    def test_link_simbolico_para_fora_e_barrado(self, tmp_path: Path) -> None:
        fora = tmp_path.parent / f"{tmp_path.name}_fora"
        fora.mkdir()
        try:
            (tmp_path / "atalho").symlink_to(fora, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("este sistema não permite criar links simbólicos sem privilégio")
        with pytest.raises(CaminhoInseguro):
            dentro_da_pasta(tmp_path, "atalho/segredo.txt")

    @pytest.mark.parametrize(
        "entrada", ["../x", "a/../../x", "/abs", "C:/x", "\\\\servidor\\pasta\\x", "a/./../..", "", "..", "x\x00y"]
    )
    def test_zip_slip_em_pacote_fabulim(self, entrada: str) -> None:
        with pytest.raises(CaminhoInseguro):
            entrada_de_pacote_segura(entrada)

    def test_entradas_normais_de_pacote(self) -> None:
        assert entrada_de_pacote_segura("characters/bolinho/ref.png") == "characters/bolinho/ref.png"
        assert entrada_de_pacote_segura("./a\\b/c.json") == "a/b/c.json"


class TestDownloads:
    @pytest.mark.parametrize(
        "url,esperado",
        [
            ("https://huggingface.co/black-forest-labs/FLUX.2-klein-4B/resolve/main/x.safetensors", True),
            ("https://github.com/leejet/stable-diffusion.cpp/releases/download/x/sd.zip", True),
            ("https://release-assets.githubusercontent.com/abc", True),
            ("https://registry.ollama.ai/v2/library/qwen3/blobs/sha256-abc", True),
            ("http://huggingface.co/x", False),
            ("https://huggingface.co.evil.com/x", False),
            ("https://evilhuggingface.co/x", False),
            ("https://192.168.0.5/x.safetensors", False),
            ("https://exemplo.com/modelo.gguf", False),
            ("ftp://github.com/x", False),
            ("file:///C:/x", False),
            ("", False),
        ],
    )
    def test_fonte_oficial(self, url: str, esperado: bool) -> None:
        assert fonte_oficial(url) is esperado

    @pytest.mark.parametrize(
        "nome,pickle,esperado",
        [
            ("modelo.safetensors", False, True),
            ("modelo-Q4_K_M.gguf", False, True),
            ("birefnet.onnx", False, True),
            ("modelo.ckpt", False, False),
            ("pesos.pt", False, False),
            ("pesos.bin", False, False),
            ("pesos.PKL", False, False),
            ("pesos.pt", True, True),
            ("programa.exe", False, False),
            ("script.ps1", False, False),
        ],
    )
    def test_formato_permitido(self, nome: str, pickle: bool, esperado: bool) -> None:
        assert formato_permitido(nome, permitir_pickle=pickle) is esperado

    def test_hash_confere_e_diverge(self, tmp_path: Path) -> None:
        arquivo = tmp_path / "m.gguf"
        arquivo.write_bytes(b"conteudo de teste")
        sha = sha256_arquivo(arquivo)
        assert len(sha) == 64 and verificar_sha256(arquivo, sha.upper()) == sha
        with pytest.raises(HashDiferente):
            verificar_sha256(arquivo, "0" * 64)

    def test_manifesto_registra_e_recusa(self, tmp_path: Path) -> None:
        arquivo = tmp_path / "m.safetensors"
        arquivo.write_bytes(b"pesos")
        manifesto = ManifestoDeDownloads(tmp_path / "config" / "downloads.json")
        url = "https://huggingface.co/x/y/resolve/main/m.safetensors"
        entrada = manifesto.registrar(arquivo, url, "Apache-2.0", sha256_esperado=sha256_arquivo(arquivo))
        assert entrada["license"] == "Apache-2.0" and entrada["size_bytes"] == 5
        assert [i["file"] for i in manifesto.itens()] == ["m.safetensors"]
        manifesto.registrar(arquivo, url, "Apache-2.0")  # registrar de novo substitui, não duplica
        assert len(manifesto.itens()) == 1
        with pytest.raises(DownloadInseguro, match="fonte"):
            manifesto.registrar(arquivo, "https://exemplo.com/m.safetensors", "MIT")
        with pytest.raises(HashDiferente):
            manifesto.registrar(arquivo, url, "MIT", sha256_esperado="f" * 64)
        pickle = tmp_path / "p.ckpt"
        pickle.write_bytes(b"x")
        with pytest.raises(DownloadInseguro, match="formato"):
            manifesto.registrar(pickle, "https://huggingface.co/x/p.ckpt", "MIT")

    def test_manifesto_ilegivel_vira_lista_vazia(self, tmp_path: Path) -> None:
        caminho = tmp_path / "d.json"
        caminho.write_text("{ quebrado", encoding="utf-8")
        assert ManifestoDeDownloads(caminho).itens() == []


class TestUploads:
    PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
    WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 16
    GIF = b"GIF89a" + b"\x00" * 16

    def test_reconhece_o_tipo_pelo_conteudo(self) -> None:
        assert tipo_real_da_imagem(self.PNG) == "png"
        assert tipo_real_da_imagem(self.JPG) == "jpeg"
        assert tipo_real_da_imagem(self.WEBP) == "webp"
        assert tipo_real_da_imagem(self.GIF) == "gif"
        assert tipo_real_da_imagem(b"MZ\x90\x00 executavel") is None
        assert tipo_real_da_imagem(b"") is None

    def test_validacoes(self) -> None:
        assert validar_upload_imagem(self.PNG, "coelho.png") == "png"
        assert validar_upload_imagem(self.JPG, "coelho.JPEG") == "jpeg"
        with pytest.raises(UploadInvalido, match="vazio"):
            validar_upload_imagem(b"", "a.png")
        with pytest.raises(UploadInvalido, match="não é uma imagem"):
            validar_upload_imagem(b"MZ" + b"\x00" * 100, "malware.png")  # extensão mente
        with pytest.raises(UploadInvalido, match="não combina"):
            validar_upload_imagem(self.PNG, "foto.jpg")
        with pytest.raises(UploadInvalido, match="maior"):
            validar_upload_imagem(self.PNG + b"\x00" * 2000, "grande.png", max_bytes=1000)
        with pytest.raises(UploadInvalido):
            validar_upload_imagem(self.PNG, "semextensao")


class TestServidorReal:
    """Sobe o servidor de verdade: só pode responder em 127.0.0.1, nunca pelo IP da rede."""

    @staticmethod
    def _porta_livre() -> int:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])

    @staticmethod
    def _ip_da_rede() -> str | None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("192.0.2.1", 9))  # endereço de documentação: nenhum pacote sai
                ip = str(s.getsockname()[0])
        except OSError:
            return None
        return None if ip.startswith("127.") else ip

    def _ambiente(self, tmp_path: Path, **extra: str) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            FABULIM_DATA_DIR=str(tmp_path / "data"),
            FABULIM_HARDWARE_JSON=str(tmp_path / "hardware.json"),
            FABULIM_FRONTEND_DIST=str(tmp_path / "dist"),
            FABULIM_AUTO_DIAGNOSTICO="0",
            PYTHONIOENCODING="utf-8",
        )
        env.update(extra)
        return env

    def test_recusa_subir_fora_do_loopback(self, tmp_path: Path) -> None:
        r = subprocess.run(
            [sys.executable, str(RAIZ / "scripts" / "servidor.py")],
            env=self._ambiente(tmp_path, FABULIM_HOST="0.0.0.0", FABULIM_PORT=str(self._porta_livre())),
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
        )
        assert r.returncode == 2 and "127.0.0.1" in r.stdout

    def test_so_responde_em_127_0_0_1(self, tmp_path: Path) -> None:
        porta = self._porta_livre()
        proc = subprocess.Popen(
            [sys.executable, str(RAIZ / "scripts" / "servidor.py")],
            env=self._ambiente(tmp_path, FABULIM_PORT=str(porta)),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            url = f"http://127.0.0.1:{porta}/api/health"
            resposta = None
            limite = time.monotonic() + 120  # o servidor de verdade leva bem mais para subir com o notebook carregado
            while time.monotonic() < limite and resposta is None:
                try:
                    resposta = httpx.get(url, timeout=2)
                except httpx.HTTPError:
                    time.sleep(0.3)
            assert resposta is not None and resposta.json() == {"status": "ok"}
            assert "server" not in resposta.headers  # não anuncia a versão do uvicorn
            ip = self._ip_da_rede()
            if ip is None:
                pytest.skip("sem interface de rede além do loopback para testar")
            with pytest.raises(OSError), socket.create_connection((ip, porta), timeout=3):
                pass  # se conectasse, o servidor estaria exposto à rede
        finally:
            proc.terminate()
            try:
                proc.wait(15)
            except subprocess.TimeoutExpired:
                proc.kill()
