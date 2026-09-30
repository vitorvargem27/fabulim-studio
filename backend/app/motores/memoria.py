"""Memória: só um modelo pesado por vez. Antes de gerar imagem, voz ou vídeo, o modelo de texto (Ollama) sai da memória."""

from __future__ import annotations

from ..services.ollama import OllamaClient, OllamaIndisponivel


def liberar_llm(ollama: OllamaClient) -> list[str]:
    """Descarrega os modelos do Ollama que estão na memória (briefing 2.6). Nunca falha: sem Ollama, não há o que liberar."""
    liberados: list[str] = []
    try:
        for modelo in ollama.carregados():
            nome = str(modelo.get("name") or "")
            if nome:
                ollama.descarregar(nome)
                liberados.append(nome)
    except OllamaIndisponivel:
        pass
    return liberados
