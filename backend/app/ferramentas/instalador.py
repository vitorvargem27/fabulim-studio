"""Instalador de ferramentas e modelos (briefing, seção 11: só fonte oficial, SHA-256 conferido, nada de pickle).

Fluxo de cada item: resolve o endereço, o tamanho e o SHA-256 **na API da própria fonte** → confere o espaço em disco →
baixa (com retomada, validando cada redirecionamento) → confere o hash → extrai (zip com proteção contra zip slip) →
registra no manifesto (origem, hash, tamanho e licença). Sem hash oficial o item não é instalado.

O app só chama isto quando o usuário pede (botão na tela Modelos ou ``scripts/instalar.py``): nunca baixa sozinho.
"""

from __future__ import annotations

import posixpath
import re
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from ..config import Settings
from ..security.caminhos import dentro_da_pasta, entrada_de_pacote_segura
from ..security.downloads import DownloadInseguro, ManifestoDeDownloads, fonte_oficial
from .catalogo import ITENS, GitHub, HuggingFace, Item, por_id

Progresso = Callable[[str, int, int], None]  # (o que está fazendo, bytes feitos, bytes totais)

LIMITE_DESCOMPACTADO = 3 * 1024**3  # protege contra zip bomb
MARGEM_DISCO = 2 * 1024**3  # sobra mínima depois da instalação
ESPERA_REDIRECIONAMENTOS = 6


class ErroDeInstalacao(RuntimeError):
    """Algo impediu a instalação; a mensagem já é em português e diz o que fazer."""


class SemHashOficial(ErroDeInstalacao):
    """A fonte não publica o SHA-256 deste arquivo: sem ele não dá para conferir e o item não é instalado."""


@dataclass(frozen=True)
class Origem:
    url: str
    sha256: str
    tamanho: int
    versao: str


@dataclass(frozen=True)
class Resultado:
    id: str
    situacao: str  # instalado | ja_instalado
    arquivo: Path | None = None
    origem: Origem | None = None


def novo_cliente() -> httpx.Client:
    # Sem seguir redirecionamentos sozinho: cada salto é conferido contra a lista de fontes oficiais.
    return httpx.Client(
        headers={"User-Agent": "fabulim-studio-instalador"},
        timeout=httpx.Timeout(30.0, read=120.0),
        follow_redirects=False,
    )


def _json(cliente: httpx.Client, url: str, **kwargs: Any) -> Any:
    if not fonte_oficial(url):
        raise DownloadInseguro(f"fonte não oficial: {url}")
    resposta = cliente.get(url, headers={"Accept": "application/json"}, **kwargs)
    if resposta.status_code == 404:
        raise ErroDeInstalacao(f"não encontrei na fonte oficial: {url}")
    resposta.raise_for_status()
    return resposta.json()


def resolver_github(cliente: httpx.Client, fonte: GitHub) -> Origem:
    release = _json(cliente, f"https://api.github.com/repos/{fonte.repo}/releases/tags/{fonte.tag}")
    padrao = re.compile(fonte.arquivo)
    candidatos = sorted(
        (a for a in release.get("assets", []) if padrao.search(a.get("name", ""))), key=lambda a: a["name"]
    )
    if not candidatos:
        raise ErroDeInstalacao(
            f"o release {fonte.tag} de {fonte.repo} não tem um arquivo que combine com {fonte.arquivo!r}"
        )
    ativo = candidatos[-1]  # o de versão mais alta
    digest = str(ativo.get("digest") or "")
    if not digest.startswith("sha256:"):
        raise SemHashOficial(f"{ativo['name']}: o GitHub não publica o SHA-256 deste arquivo")
    publicado = str(release.get("published_at") or "")[:10]
    return Origem(
        ativo["browser_download_url"], digest.removeprefix("sha256:"), int(ativo["size"]), f"{fonte.tag} ({publicado})"
    )


def resolver_huggingface(cliente: httpx.Client, fonte: HuggingFace) -> Origem:
    modelo = _json(cliente, f"https://huggingface.co/api/models/{fonte.repo}")
    if modelo.get("gated") or modelo.get("private"):
        raise ErroDeInstalacao(f"{fonte.repo} exige login no Hugging Face; não instalo nada que peça credenciais")
    commit = str(modelo["sha"])
    pasta = posixpath.dirname(fonte.arquivo)
    listagem = _json(
        cliente, f"https://huggingface.co/api/models/{fonte.repo}/tree/{commit}" + (f"/{pasta}" if pasta else "")
    )
    entrada = next((e for e in listagem if e.get("path") == fonte.arquivo and e.get("type") == "file"), None)
    if entrada is None:
        raise ErroDeInstalacao(f"{fonte.arquivo} não existe em {fonte.repo}")
    oid = str((entrada.get("lfs") or {}).get("oid") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", oid):
        raise SemHashOficial(f"{fonte.arquivo}: o Hugging Face não publica o SHA-256 deste arquivo")
    return Origem(
        f"https://huggingface.co/{fonte.repo}/resolve/{commit}/{fonte.arquivo}",
        oid,
        int(entrada["size"]),
        f"commit {commit[:10]}",
    )


def resolver(cliente: httpx.Client, item: Item) -> Origem:
    if isinstance(item.fonte, GitHub):
        return resolver_github(cliente, item.fonte)
    return resolver_huggingface(cliente, item.fonte)


def baixar(cliente: httpx.Client, origem: Origem, parcial: Path, progresso: Progresso | None = None) -> None:
    """Baixa para ``parcial`` retomando de onde parou. Cada redirecionamento precisa ser de fonte oficial."""
    parcial.parent.mkdir(parents=True, exist_ok=True)
    feitos = parcial.stat().st_size if parcial.exists() else 0
    if feitos > origem.tamanho:
        parcial.unlink()
        feitos = 0
    if feitos == origem.tamanho:
        return
    url = origem.url
    for _ in range(ESPERA_REDIRECIONAMENTOS):
        if not fonte_oficial(url):
            raise DownloadInseguro(f"redirecionamento para fora das fontes oficiais: {url}")
        cabecalhos = {"Range": f"bytes={feitos}-"} if feitos else {}
        with cliente.stream("GET", url, headers=cabecalhos) as resposta:
            if resposta.is_redirect:
                url = urljoin(url, resposta.headers["location"])
                continue
            resposta.raise_for_status()
            if feitos and resposta.status_code != 206:  # o servidor ignorou o pedido de retomada: recomeça
                feitos = 0
            with parcial.open("ab" if feitos else "wb") as saida:
                for pedaco in resposta.iter_bytes(1024 * 1024):
                    saida.write(pedaco)
                    feitos += len(pedaco)
                    if progresso:
                        progresso("baixando", feitos, origem.tamanho)
            return
    raise ErroDeInstalacao("redirecionamentos demais ao baixar")


def extrair_zip(arquivo: Path, destino: Path, *, remover_pasta_raiz: bool = False) -> int:
    """Extrai com proteção contra zip slip, links simbólicos e zip bomb. Devolve quantos arquivos foram extraídos."""
    with zipfile.ZipFile(arquivo) as zf:
        entradas = [i for i in zf.infolist() if not i.is_dir()]
        if sum(i.file_size for i in entradas) > LIMITE_DESCOMPACTADO:
            raise DownloadInseguro("o pacote descompactado é grande demais (possível zip bomb)")
        nomes = [entrada_de_pacote_segura(i.filename) for i in entradas]
        raiz = ""
        if remover_pasta_raiz and nomes and len({n.split("/")[0] for n in nomes}) == 1 and all("/" in n for n in nomes):
            raiz = nomes[0].split("/")[0] + "/"
        destino.mkdir(parents=True, exist_ok=True)
        for info, nome in zip(entradas, nomes, strict=True):
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise DownloadInseguro(f"o pacote contém um link simbólico: {info.filename}")
            alvo = dentro_da_pasta(destino, nome.removeprefix(raiz))
            alvo.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as origem, alvo.open("wb") as saida:
                shutil.copyfileobj(origem, saida, 1024 * 1024)
    return len(entradas)


def vozes_sao_dados_puros(arquivo: Path) -> None:
    """O `voices-*.bin` do Kokoro é um .npz; abrir com ``allow_pickle=False`` prova que não há código escondido."""
    codigo = "import sys, numpy as np; d = np.load(sys.argv[1], allow_pickle=False); print(len(d.files))"
    proc = subprocess.run([sys.executable, "-c", codigo, str(arquivo)], capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise DownloadInseguro(
            "o arquivo de vozes não abre como dados puros (sem pickle): " + " ".join(proc.stderr.split())[-200:]
        )


VERIFICACOES: dict[str, Callable[[Path], None]] = {"kokoro-vozes": vozes_sao_dados_puros}


class Instalador:
    def __init__(self, settings: Settings, cliente: httpx.Client | None = None) -> None:
        self._settings = settings
        self._cliente_dado = cliente
        self._cliente_criado: httpx.Client | None = None

    @property
    def _cliente(self) -> httpx.Client:
        """O cliente HTTP só nasce quando algo precisa baixar (listar o catálogo não abre conexão nenhuma)."""
        if self._cliente_dado is not None:
            return self._cliente_dado
        if self._cliente_criado is None:
            self._cliente_criado = novo_cliente()
        return self._cliente_criado

    def base(self, item: Item) -> Path:
        return self._settings.tools_dir if item.base == "tools" else self._settings.models_dir

    def manifesto(self, item: Item) -> ManifestoDeDownloads:
        return ManifestoDeDownloads(self.base(item) / "manifesto.json")

    def instalado(self, item: Item) -> bool:
        return dentro_da_pasta(self.base(item), item.marcador).exists()

    def instalar(self, item: Item | str, progresso: Progresso | None = None) -> Resultado:
        item = por_id(item) if isinstance(item, str) else item
        base = self.base(item)
        if self.instalado(item):
            return Resultado(item.id, "ja_instalado", dentro_da_pasta(base, item.marcador))
        if progresso:
            progresso("consultando a fonte oficial", 0, 0)
        origem = resolver(self._cliente, item)
        self._conferir_espaco(base, origem.tamanho)

        destino = dentro_da_pasta(base, item.destino)
        arquivo = (base / ".downloads" / Path(origem.url.split("?")[0]).name) if item.compactado else destino
        parcial = arquivo.with_name(arquivo.name + ".parte")
        baixar(self._cliente, origem, parcial, progresso)
        if parcial.stat().st_size != origem.tamanho:
            parcial.unlink()
            raise ErroDeInstalacao(f"{item.nome}: o download veio incompleto; tente de novo")
        parcial.replace(arquivo)
        if progresso:
            progresso("conferindo o SHA-256", origem.tamanho, origem.tamanho)
        try:
            self.manifesto(item).registrar(
                arquivo, origem.url, item.licenca, sha256_esperado=origem.sha256, permitir_pickle=item.permitir_pickle
            )
        except DownloadInseguro:
            arquivo.unlink(missing_ok=True)  # não deixa no disco um arquivo que não passou na conferência
            raise
        if item.compactado:
            if progresso:
                progresso("extraindo", 0, 0)
            novo = destino.with_name(destino.name + ".novo")
            shutil.rmtree(novo, ignore_errors=True)
            extrair_zip(arquivo, novo, remover_pasta_raiz=item.remover_pasta_raiz)
            shutil.rmtree(destino, ignore_errors=True)
            novo.replace(destino)
            arquivo.unlink(missing_ok=True)
        marcador = dentro_da_pasta(base, item.marcador)
        if not marcador.exists():
            raise ErroDeInstalacao(f"{item.nome}: instalei, mas não achei {item.marcador}; o pacote mudou de formato")
        verificar = VERIFICACOES.get(item.id)
        if verificar:
            try:
                verificar(marcador)
            except DownloadInseguro:
                marcador.unlink(missing_ok=True)
                raise
        return Resultado(item.id, "instalado", marcador, origem)

    def _conferir_espaco(self, base: Path, necessario: int) -> None:
        base.mkdir(parents=True, exist_ok=True)
        livre = shutil.disk_usage(base).free
        if livre < necessario * 2 + MARGEM_DISCO:  # arquivo compactado + extraído
            raise ErroDeInstalacao(
                f"pouco espaço em disco: preciso de cerca de {(necessario * 2 + MARGEM_DISCO) / 1024**3:.1f} GB livres "
                f"e há {livre / 1024**3:.1f} GB. Libere espaço ou aponte FABULIM_MODELS_DIR / FABULIM_TOOLS_DIR para outro disco."
            )

    def tamanho(self, item: Item) -> int | None:
        """Espaço que o item ocupa no disco (a pasta inteira, quando é um programa extraído)."""
        if not self.instalado(item):
            return None
        alvo = dentro_da_pasta(self.base(item), item.destino)
        if alvo.is_file():
            return alvo.stat().st_size
        return sum(f.stat().st_size for f in alvo.rglob("*") if f.is_file())

    def situacao(self) -> list[dict[str, Any]]:
        """Cada item do catálogo com o estado atual (para a tela Modelos).

        ``size_bytes`` é o espaço no disco quando o item já está instalado; antes disso é o tamanho aproximado do
        download (``size_estimated``), para o usuário saber o que vai baixar antes de clicar em Instalar.
        """
        itens: list[dict[str, Any]] = []
        for item in ITENS:
            instalado = self.instalado(item)
            no_disco = self.tamanho(item) if instalado else None
            itens.append(
                {
                    "id": item.id,
                    "name": item.nome,
                    "purpose": item.para,
                    "group": item.grupo,
                    "license": item.licenca,
                    "installed": instalado,
                    "size_bytes": no_disco if instalado else (item.aprox_bytes or None),
                    "size_estimated": not instalado,
                }
            )
        return itens
