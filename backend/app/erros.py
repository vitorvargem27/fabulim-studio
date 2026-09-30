"""Erros com mensagem pronta para o usuário: já dizem o que aconteceu e como resolver, em português simples."""

from __future__ import annotations


class ErroParaOUsuario(RuntimeError):
    """A mensagem pode ser mostrada como está (a Fila não acrescenta o nome da classe do erro)."""
