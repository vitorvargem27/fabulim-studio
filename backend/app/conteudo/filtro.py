"""Filtro de conteúdo para crianças de 2 a 5 anos (briefing, seção 8).

Todo prompt (personagem, imagem, enredo) e todo roteiro gerado passam por aqui **antes** de qualquer geração. Se reprovar,
o app bloqueia e explica o motivo em linguagem simples. A lista é conservadora de propósito e fica num lugar só, para o
usuário poder ler e ajustar. O texto colado nunca vira instrução para o sistema: aqui ele é só examinado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..prompts.parser import normalizar

# Personagens e marcas de terceiros (o YouTube desmonetiza, e a regra do briefing proíbe): nomes normalizados (sem acento).
MARCAS_DE_TERCEIROS = (
    "galinha pintadinha",
    "pintinho amarelinho",
    "peppa",
    "george pig",
    "bluey",
    "patrulha canina",
    "paw patrol",
    "mickey",
    "minnie",
    "pato donald",
    "donald duck",
    "pateta",
    "disney",
    "pixar",
    "frozen",
    "moana",
    "mufasa",
    "bambi",
    "dumbo",
    "toy story",
    "woody",
    "buzz lightyear",
    "lightning mcqueen",
    "relampago mcqueen",
    "marvel",
    "homem aranha",
    "spider man",
    "batman",
    "superman",
    "vingadores",
    "pikachu",
    "pokemon",
    "mario bros",
    "super mario",
    "luigi",
    "sonic the hedgehog",
    "hello kitty",
    "cocomelon",
    "baby shark",
    "masha e o urso",
    "ursinho pooh",
    "winnie the pooh",
    "bob esponja",
    "spongebob",
    "patati patata",
    "turma da monica",
    "cebolinha",
    "cascao",
    "backyardigans",
    "dora aventureira",
    "mundo bita",
    "power rangers",
    "ben 10",
    "minions",
    "shrek",
    "kung fu panda",
    "madagascar",
    "os incriveis",
    "hot wheels",
    "barbie",
    "lego",
    "peppa pig",
    "tom e jerry",
    "pica pau",
    "scooby",
    "looney tunes",
    "sitio do picapau",
    "pocoyo",
    "smurfs",
    "smurf",
    "os smurfs",
    "thomas e seus amigos",
    "thomas the tank",
    "sesame street",
    "vila sesamo",
    "cookie monster",
    "bananas de pijamas",
    "chapolin",
)

# Tema → palavras (sem acento) que não combinam com 2 a 5 anos.
TEMAS_PROIBIDOS: dict[str, tuple[str, ...]] = {
    "medo ou terror": (
        "terror",
        "horror",
        "assustador",
        "assustadora",
        "aterrorizante",
        "pesadelo",
        "assombracao",
        "assombrado",
        "demonio",
        "diabo",
        "caveira",
        "zumbi",
        "vampiro",
        "monstro assustador",
        "bruxa malvada",
        "fantasma assustador",
        "sinistro",
        "sombrio",
        "scary",
        "terrifying",
        "nightmare",
        "haunted",
    ),
    "violência": (
        "sangue",
        "sangrando",
        "matar",
        "matou",
        "morte",
        "morrer",
        "morreu",
        "assassin",
        "arma",
        "pistola",
        "revolver",
        "espingarda",
        "faca",
        "tiro",
        "explosao",
        "violencia",
        "violento",
        "briga",
        "socar",
        "bater em",
        "tortura",
        "guerra",
        "luta armada",
        "machucar",
        "ferido",
        "blood",
        "kill",
        "killed",
        "dead",
        "death",
        "gun",
        "weapon",
        "knife",
    ),
    "perigo ou situação arriscada": (
        "afogar",
        "afogamento",
        "incendio",
        "eletrocutar",
        "veneno",
        "envenenar",
        "sequestro",
        "sequestrar",
        "desaparecer sozinho",
        "suicidio",
        "droga",
        "cigarro",
        "cerveja",
        "alcool",
        "bebida alcoolica",
    ),
    "consumo ou propaganda": (
        "unboxing",
        "compre ja",
        "compre agora",
        "promocao",
        "oferta imperdivel",
        "use o cupom",
        "link na descricao",
        "patrocinado",
        "publicidade",
        "abrindo caixa surpresa",
    ),
    "conteúdo sensacionalista": ("pegadinha", "desafio perigoso", "chocante", "bizarro", "nojento"),
}
TEXTO_DO_TEMA = {
    "medo ou terror": "fala de algo assustador, e vídeos para crianças de 2 a 5 anos não podem dar medo",
    "violência": "fala de violência, e vídeos para crianças de 2 a 5 anos não podem ter isso",
    "perigo ou situação arriscada": "mostra uma situação de perigo, e vídeos para crianças de 2 a 5 anos não podem ter isso",
    "consumo ou propaganda": "parece propaganda ou incentivo a consumo, que não é permitido em vídeos para crianças pequenas",
    "conteúdo sensacionalista": "tem um tom sensacionalista, que não combina com vídeos calmos para crianças pequenas",
}

# Tentativas de mandar no sistema por dentro do texto colado (o app ignora; aqui só se registra que houve).
PADROES_DE_INJECAO = (
    r"ignor\w* (todas )?(as |suas )?(instrucoes|regras|ordens)",
    r"desconsider\w* (todas )?(as |suas )?(instrucoes|regras)",
    r"ignore (all |any )?(previous |prior |the )?(instructions|rules)",
    r"disregard (all |the )?(previous |prior )?(instructions|rules)",
    r"voce agora e",
    r"you are now",
    r"system prompt",
    r"prompt do sistema",
    r"modo desenvolvedor",
    r"developer mode",
)


@dataclass(frozen=True)
class Reprovacao:
    categoria: str  # marca | tema | injecao
    trecho: str
    motivo: str  # já em linguagem simples, para mostrar ao usuário

    def para_api(self) -> dict[str, str]:
        return {"category": self.categoria, "excerpt": self.trecho, "reason": self.motivo}


# Palavras que negam o termo logo depois: «sem violência», «nada assustador», «nothing scary» não são o problema.
NEGADORES = frozenset(
    {
        "nao",
        "nada",
        "sem",
        "nunca",
        "nem",
        "nenhum",
        "nenhuma",
        "zero",
        "no",
        "not",
        "never",
        "nor",
        "nothing",
        "non",
        "without",
        "free",
    }
)
JANELA_DE_NEGACAO = 3  # quantas palavras antes do termo ainda contam como negação (dentro da mesma frase)


def _negado(texto_normalizado: str, inicio: int) -> bool:
    frase = re.split(r"[.!?;:\n]", texto_normalizado[:inicio])[-1]
    anteriores = [p.strip(",()\"'«»-") for p in frase.split()][-JANELA_DE_NEGACAO:]
    return any(p in NEGADORES for p in anteriores)


def _procura(texto_normalizado: str, termo: str, *, aceita_negacao: bool = True) -> bool:
    """Palavra inteira (ou frase inteira): «arma» não pega «armário», «tiro» não pega «retiro».

    Tema precedido de negação («sem sangue», «nothing scary») não conta: o texto está dizendo o contrário. Marca de
    terceiros conta sempre, mesmo negada («não é o Bluey» ainda cita o Bluey).
    """
    for achado in re.finditer(rf"(?<![a-z0-9]){re.escape(termo)}(?![a-z0-9])", texto_normalizado):
        if not (aceita_negacao and _negado(texto_normalizado, achado.start())):
            return True
    return False


def verificar_texto(texto: str) -> Reprovacao | None:
    """Devolve o primeiro problema encontrado no texto, ou ``None`` se estiver tudo bem."""
    n = normalizar(texto)
    if not n:
        return None
    for marca in MARCAS_DE_TERCEIROS:
        if _procura(n, marca, aceita_negacao=False):
            return Reprovacao(
                "marca",
                marca,
                f"O texto cita «{marca}», que é personagem ou marca de terceiros. Crie um personagem original: "
                "o YouTube não monetiza conteúdo com personagens de outras pessoas.",
            )
    for tema, palavras in TEMAS_PROIBIDOS.items():
        for palavra in palavras:
            if _procura(n, palavra):
                return Reprovacao(
                    "tema",
                    palavra,
                    f"O texto usa «{palavra}» e {TEXTO_DO_TEMA[tema]}. Reescreva de um jeito tranquilo e alegre.",
                )
    return None


def verificar_campos(campos: dict[str, object]) -> Reprovacao | None:
    """Examina todos os campos de texto de um formulário (listas de nomes incluídas), na ordem em que vierem."""
    for valor in campos.values():
        partes = valor if isinstance(valor, list) else [valor]
        for parte in partes:
            if isinstance(parte, str) and (r := verificar_texto(parte)):
                return r
    return None


def tem_tentativa_de_injecao(texto: str) -> bool:
    n = normalizar(texto)
    return any(re.search(p, n) for p in PADROES_DE_INJECAO)
