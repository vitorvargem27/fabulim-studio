from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from ..container import Servicos


def obter_servicos(request: Request) -> Servicos:
    sv: Servicos = request.app.state.servicos
    return sv


ServicosDep = Annotated[Servicos, Depends(obter_servicos)]
