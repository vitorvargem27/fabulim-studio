"""Cliente do Ollama (só 127.0.0.1). Trocar de runtime depois não afeta o resto: o app fala por esta interface."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import httpx


class OllamaIndisponivel(RuntimeError):
    """O servidor do Ollama não respondeu (parado, porta errada ou erro)."""


class OllamaClient:
    def __init__(self, base_url: str, *, transport: httpx.BaseTransport | None = None, timeout: float = 3.0) -> None:
        self._http = httpx.Client(base_url=base_url, transport=transport, timeout=timeout)

    def _pedir(
        self, metodo: str, caminho: str, *, json: dict[str, Any] | None = None, timeout: float | None = None
    ) -> dict[str, Any]:
        try:
            resposta = self._http.request(
                metodo, caminho, json=json, timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT
            )
            resposta.raise_for_status()
            dados = resposta.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaIndisponivel(str(exc) or type(exc).__name__) from exc
        if not isinstance(dados, dict):
            raise OllamaIndisponivel("resposta inesperada do Ollama")
        return dados

    def versao(self) -> str:
        return str(self._pedir("GET", "/api/version").get("version", "?"))

    def modelos(self) -> list[dict[str, Any]]:
        lista = self._pedir("GET", "/api/tags").get("models") or []
        return [m for m in lista if isinstance(m, dict)]

    def carregados(self) -> list[dict[str, Any]]:
        lista = self._pedir("GET", "/api/ps").get("models") or []
        return [m for m in lista if isinstance(m, dict)]

    def gerar(self, modelo: str, prompt: str, *, num_predict: int, timeout: float = 900.0) -> dict[str, Any]:
        """Uma geração sem streaming e sem 'thinking', determinística (temperatura 0, seed fixa)."""
        corpo = {
            "model": modelo,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "keep_alive": "5m",
            "options": {"temperature": 0, "num_predict": num_predict, "seed": 1},
        }
        return self._pedir("POST", "/api/generate", json=corpo, timeout=timeout)

    def conversar(
        self,
        modelo: str,
        mensagens: list[dict[str, str]],
        *,
        formato: dict[str, Any] | str | None = None,
        num_predict: int = 1024,
        temperatura: float = 0.4,
        seed: int | None = None,
        timeout: float = 1800.0,
    ) -> Generator[dict[str, Any], None, None]:
        """Uma conversa em streaming (cada item é um pedaço da resposta; o último traz as contagens de tokens).

        ``formato`` pode ser ``"json"`` ou um esquema JSON: o Ollama então só produz texto que obedece ao esquema.
        Sem 'thinking', para não gastar tokens pensando. Feche o gerador para interromper a geração.
        """
        opcoes: dict[str, Any] = {"temperature": temperatura, "num_predict": num_predict}
        if seed is not None:
            opcoes["seed"] = seed
        corpo: dict[str, Any] = {
            "model": modelo,
            "messages": mensagens,
            "stream": True,
            "think": False,
            "keep_alive": "5m",
            "options": opcoes,
        }
        if formato is not None:
            corpo["format"] = formato
        try:
            with self._http.stream("POST", "/api/chat", json=corpo, timeout=timeout) as resposta:
                resposta.raise_for_status()
                for linha in resposta.iter_lines():
                    if not linha.strip():
                        continue
                    pedaco = json.loads(linha)
                    if isinstance(pedaco, dict):
                        yield pedaco
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaIndisponivel(str(exc) or type(exc).__name__) from exc

    def descarregar(self, modelo: str) -> None:
        """Libera a memória do modelo (regra do briefing: descarregar o LLM antes de jobs de imagem, vídeo ou áudio)."""
        self._pedir("POST", "/api/generate", json={"model": modelo, "keep_alive": 0}, timeout=30.0)

    def fechar(self) -> None:
        self._http.close()
