"""Regras de download de modelos e ferramentas (briefing, seção 11).

Só fontes oficiais, hash SHA-256 registrado e verificado, e nada de formatos que executam código ao carregar
(pickle: ``.ckpt``, ``.pt``, ``.bin``...). O app **nunca baixa nada sozinho**: estas funções validam o que o
usuário autorizou.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

FONTES_OFICIAIS: tuple[str, ...] = (
    "huggingface.co",
    "hf.co",
    "github.com",
    "githubusercontent.com",
    "registry.ollama.ai",
    "ollama.com",
    "pypi.org",
    "files.pythonhosted.org",
    "registry.npmjs.org",
)
# `.zip` é só para programas de fonte oficial (com SHA-256 conferido); a extração barra zip slip, links e zip bomb.
FORMATOS_SEGUROS = frozenset(
    {".safetensors", ".gguf", ".onnx", ".json", ".txt", ".md", ".yaml", ".yml", ".model", ".zip"}
)
FORMATOS_PICKLE = frozenset({".ckpt", ".pt", ".pth", ".bin", ".pkl", ".pickle", ".joblib", ".npy"})


class DownloadInseguro(ValueError):
    pass


class HashDiferente(DownloadInseguro):
    pass


def fonte_oficial(url: str) -> bool:
    """HTTPS e domínio (ou subdomínio) da lista de fontes oficiais. Nada de HTTP, IP puro ou domínios parecidos."""
    partes = urlparse(url)
    host = (partes.hostname or "").lower()
    if partes.scheme != "https" or not host:
        return False
    return any(host == d or host.endswith("." + d) for d in FONTES_OFICIAIS)


def formato_permitido(nome: str, *, permitir_pickle: bool = False) -> bool:
    """``.safetensors``, GGUF e ONNX passam; pickle só com autorização explícita (e origem confiável)."""
    extensao = Path(nome).suffix.lower()
    if extensao in FORMATOS_PICKLE:
        return permitir_pickle
    return extensao in FORMATOS_SEGUROS


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def verificar_sha256(caminho: Path, esperado: str) -> str:
    """Confere o hash; devolve o hash calculado ou levanta ``HashDiferente``."""
    calculado = sha256_arquivo(caminho)
    if calculado.lower() != esperado.strip().lower():
        raise HashDiferente(
            f"SHA-256 de {caminho.name} não confere (esperado {esperado[:12]}…, veio {calculado[:12]}…)"
        )
    return calculado


class ManifestoDeDownloads:
    """Registro (JSON) de tudo o que foi baixado: origem, hash, tamanho e licença. Escrita atômica."""

    def __init__(self, caminho: Path) -> None:
        self._caminho = caminho

    def itens(self) -> list[dict[str, Any]]:
        try:
            dados = json.loads(self._caminho.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        return [d for d in dados if isinstance(d, dict)] if isinstance(dados, list) else []

    def registrar(
        self,
        arquivo: Path,
        url: str,
        licenca: str,
        *,
        sha256_esperado: str | None = None,
        permitir_pickle: bool = False,
    ) -> dict[str, Any]:
        if not fonte_oficial(url):
            raise DownloadInseguro(f"fonte não oficial: {url}")
        if not formato_permitido(arquivo.name, permitir_pickle=permitir_pickle):
            raise DownloadInseguro(f"formato não permitido (pode executar código ao carregar): {arquivo.name}")
        sha = verificar_sha256(arquivo, sha256_esperado) if sha256_esperado else sha256_arquivo(arquivo)
        entrada = {
            "file": arquivo.name,
            "url": url,
            "sha256": sha,
            "size_bytes": arquivo.stat().st_size,
            "license": licenca,
            "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        todos = [i for i in self.itens() if i.get("file") != arquivo.name] + [entrada]
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        fd, temporario = tempfile.mkstemp(dir=self._caminho.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                json.dump(todos, f, ensure_ascii=False, indent=2)
            os.replace(temporario, self._caminho)
        finally:
            if os.path.exists(temporario):
                os.unlink(temporario)
        return entrada
