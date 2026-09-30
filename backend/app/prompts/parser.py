"""Lê o prompt colado (briefing, seção 6) e preenche o formulário.

Formato estruturado (``### PERSONAGEM``, ``### ENREDO``, ``### IMAGEM`` com ``Campo: valor``): reconhecido aqui, sem modelo
de IA. Texto livre: o LLM local extrai os campos (``livre.py``) e o usuário revisa o formulário antes de gerar.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from .formatos import TIPOS, FichaEnredo, FichaImagem, FichaPersonagem

# rótulo (sem acento e em minúsculas) → campo da ficha
ROTULOS: dict[str, dict[str, str]] = {
    "personagem": {
        "nome": "name",
        "estilo": "style",
        "tipo/especie": "species",
        "tipo": "species",
        "especie": "species",
        "idade aparente": "apparent_age",
        "idade": "apparent_age",
        "aparencia": "appearance",
        "roupas e acessorios": "clothing",
        "roupas": "clothing",
        "roupa": "clothing",
        "acessorios": "clothing",
        "paleta de cores": "palette",
        "paleta": "palette",
        "cores": "palette",
        "personalidade": "personality",
        "voz": "voice",
        "expressoes desejadas": "expressions",
        "expressoes": "expressions",
        "observacoes": "notes",
        "obs": "notes",
    },
    "enredo": {
        "titulo": "title",
        "formato": "format",
        "duracao alvo": "target_duration",
        "duracao": "target_duration",
        "idioma": "language",
        "estilo": "style",
        "personagens": "characters",
        "tema ou licao": "theme",
        "tema": "theme",
        "licao": "theme",
        "cenario(s)": "settings",
        "cenarios": "settings",
        "cenario": "settings",
        "historia": "story",
        "musica": "music",
        "observacoes": "notes",
    },
    "imagem": {
        "tipo": "kind",
        "estilo": "style",
        "formato": "format",
        "personagens": "characters",
        "descricao": "description",
        "observacoes": "notes",
    },
}
OBRIGATORIOS = {
    "personagem": ("name", "appearance"),
    "enredo": ("story",),
    "imagem": ("description",),
}
MARCADORES_DE_TIPO = {"personagem": "personagem", "enredo": "enredo", "imagem": "imagem"}
PLACEHOLDERS = ("nomes cadastrados", "opcional", "texto livre", "ideia da musica")
# dicas entre parênteses do modelo de prompt (briefing, seção 6) que sobram quando o campo não foi preenchido
DICAS_DO_MODELO = frozenset(
    {
        "(texto livre, do inicio ao fim)",
        "(nomes cadastrados na biblioteca)",
        "(opcional, nomes da biblioteca)",
        "(ideia da musica, se houver)",
        "(corpo, rosto, olhos, cabelo/pelo)",
        "(tom, velocidade, idioma)",
    }
)


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento e sem espaços duplicados: para comparar rótulos e procurar palavras."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return " ".join(sem_acento.lower().split())


@dataclass
class Interpretacao:
    tipo: str
    ficha: BaseModel
    origem: str  # estruturado | ia
    faltando: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def para_api(self) -> dict[str, Any]:
        return {
            "type": self.tipo,
            "form": self.ficha.model_dump(),
            "source": self.origem,
            "missing": self.faltando,
            "warnings": self.avisos,
        }


def detectar_tipo(texto: str) -> str | None:
    """Acha o tipo pelo cabeçalho ``### PERSONAGEM|ENREDO|IMAGEM`` (com ou sem acento, com ou sem ``#``)."""
    for linha in texto.splitlines():
        achou = re.match(r"^\s*#{1,4}\s*([A-Za-zÀ-ÿ]+)\s*$", linha)
        if achou:
            tipo = MARCADORES_DE_TIPO.get(normalizar(achou.group(1)))
            if tipo:
                return tipo
    return None


def _rotulo_e_valor(linha: str, rotulos: dict[str, str]) -> tuple[str, str] | None:
    limpa = linha.strip().lstrip("-*• ").replace("**", "").replace("__", "")
    achou = re.match(r"^([^:\n]{1,70}?)\s*:\s*(.*)$", limpa)
    if not achou:
        return None
    bruto = achou.group(1)
    sem_dica = re.sub(r"\s*\([^)]*\)", "", bruto)  # "Voz (tom, velocidade, idioma)" → "Voz"; "Cenário(s)" → "Cenário"
    for candidato in (normalizar(sem_dica), normalizar(bruto)):
        if candidato in rotulos:
            return rotulos[candidato], achou.group(2).strip()
    return None


def contar_rotulos(texto: str, tipo: str) -> int:
    """Quantas linhas do texto são ``Campo: valor`` de um formulário conhecido (2 ou mais = prompt estruturado)."""
    rotulos = ROTULOS[tipo]
    return sum(1 for linha in texto.splitlines() if _rotulo_e_valor(linha, rotulos))


def _lista_de_nomes(texto: str) -> list[str]:
    nomes: list[str] = []
    for parte in re.split(r"[,;\n]|\s+e\s+|\s+and\s+|\s+&\s+", texto):
        limpo = parte.strip(" -*•.\t")
        if limpo and not any(p in normalizar(limpo) for p in PLACEHOLDERS):
            nomes.append(limpo)
    return nomes


def _estilo(texto: str) -> str | None:
    n = normalizar(texto)
    tem3, tem2 = "3d" in n, "2d" in n
    if tem3 and not tem2:
        return "3D"
    if tem2 and not tem3:
        return "2D"
    return None  # vazio ou "2D | 3D" (o modelo do formulário deixado como está): mantém o padrão


def _normalizar_valor(campo: str, valor: str) -> Any:
    n = normalizar(valor)
    if campo == "style":
        return _estilo(valor)
    if campo in ("format", "language", "kind") and " | " in valor:
        return None  # "Short | Longo", "16:9 | 9:16 | 1:1"...: o modelo foi deixado como está; vale o padrão
    if campo == "characters":
        return _lista_de_nomes(valor)
    if campo == "format":  # enredo: short|longo; imagem: 16:9|9:16|1:1
        for proporcao in ("16:9", "9:16", "1:1"):
            if proporcao in valor.replace(" ", ""):
                return proporcao
        if "longo" in n or "long" in n:
            return "short" if "short" in n else "longo"
        return "short" if "short" in n else None
    if campo == "language":
        if re.search(r"\b(en|ingles|english|en-us)\b", n) and "pt" not in n:
            return "en"
        return "pt-BR" if n else None
    if campo == "kind":
        for chave, tipo in (
            ("cenario", "cenario"),
            ("objeto", "objeto"),
            ("thumbnail", "thumbnail"),
            ("miniatura", "thumbnail"),
        ):
            if chave in n:
                return tipo
        return "livre" if n else None
    return valor.strip()


def interpretar_estruturado(texto: str, tipo: str | None = None) -> Interpretacao:
    """Preenche a ficha a partir de ``Campo: valor``. Sem cabeçalho, ``tipo`` diz qual formulário usar."""
    tipo = tipo or detectar_tipo(texto)
    if tipo not in TIPOS:
        raise ValueError("não sei de qual formulário se trata: informe o tipo (personagem, enredo ou imagem)")
    rotulos = ROTULOS[tipo]
    valores: dict[str, list[str]] = {}
    atual: str | None = None
    for linha in texto.splitlines():
        if re.match(r"^\s*#{1,4}\s*\S", linha):
            atual = None
            continue
        achou = _rotulo_e_valor(linha, rotulos)
        if achou:
            atual = achou[0]
            valores.setdefault(atual, []).append(achou[1])
        elif atual and linha.strip():
            valores[atual].append(linha.strip())  # continuação do campo anterior (ex.: a história em vários parágrafos)
    campos: dict[str, Any] = {}
    for campo, partes in valores.items():
        uteis = [p for p in partes if p and normalizar(p) not in DICAS_DO_MODELO]
        normalizado = _normalizar_valor(campo, "\n".join(uteis).strip())
        if normalizado not in (None, "", []):
            campos[campo] = normalizado
    return _montar(tipo, campos, "estruturado")


def _montar(tipo: str, campos: dict[str, Any], origem: str) -> Interpretacao:
    modelo = TIPOS[tipo]
    avisos: list[str] = []
    try:
        ficha = modelo.model_validate(campos)
    except ValidationError as exc:
        # campo inválido: descarta só ele, mantém o resto e avisa
        for erro in exc.errors():
            campo = str(erro["loc"][0]) if erro["loc"] else "?"
            campos.pop(campo, None)
            avisos.append(f"O campo «{campo}» tinha um valor que não consegui usar; confira no formulário.")
        ficha = modelo.model_validate(campos)
    faltando = [c for c in OBRIGATORIOS[tipo] if not getattr(ficha, c)]
    return Interpretacao(tipo=tipo, ficha=ficha, origem=origem, faltando=faltando, avisos=avisos)


def montar_de_campos(tipo: str, campos: dict[str, Any], origem: str) -> Interpretacao:
    """Usado pela extração por IA: valida o que o modelo devolveu contra o esquema, do mesmo jeito."""
    limpos = {k: v for k, v in campos.items() if k in TIPOS[tipo].model_fields and v not in (None, "", [])}
    if "style" in limpos:
        limpos["style"] = _estilo(str(limpos["style"])) or "2D"
    return _montar(tipo, limpos, origem)


__all__ = [
    "FichaEnredo",
    "FichaImagem",
    "FichaPersonagem",
    "Interpretacao",
    "contar_rotulos",
    "detectar_tipo",
    "interpretar_estruturado",
    "montar_de_campos",
    "normalizar",
]
