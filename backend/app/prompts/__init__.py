"""Prompts do usuário (personagem, enredo, imagem): formulários, leitura do formato estruturado e do texto livre, prompt técnico."""

from .formatos import FichaEnredo, FichaImagem, FichaPersonagem
from .parser import Interpretacao, detectar_tipo, interpretar_estruturado

__all__ = [
    "FichaEnredo",
    "FichaImagem",
    "FichaPersonagem",
    "Interpretacao",
    "detectar_tipo",
    "interpretar_estruturado",
]
