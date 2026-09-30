"""O prompt técnico: o texto que vai de fato para o modelo de imagem (briefing, seção 6.4).

O FLUX.2 klein entende português (o codificador de texto dele é o Qwen3), então o conteúdo do criador entra como está, dentro de
uma moldura em inglês com as marcas de estilo 2D ou 3D e as regras para crianças pequenas (formas arredondadas, nada
assustador). Fica visível e editável na tela, e é salvo junto com a imagem.
"""

from __future__ import annotations

from .formatos import FichaImagem, FichaPersonagem
from .parser import normalizar

ESTILOS = {
    "2D": (
        "flat 2D cartoon illustration for toddlers, thick clean outlines, vibrant harmonious colors, simple rounded shapes, "
        "children's picture book style"
    ),
    "3D": (
        "cute 3D animated character render, soft studio lighting, smooth rounded shapes, friendly pastel-bright colors, "
        "children's animated movie style"
    ),
}
REGRAS_INFANTIS = "friendly, cute, big expressive eyes, rounded shapes, cheerful, nothing scary"
NEGATIVO = (
    "scary, horror, violence, blood, weapons, dark gloomy mood, sharp teeth, realistic human face, text, watermark, logo, "
    "deformed, extra limbs"
)
FUNDO_LIMPO = "plain solid white background, no shadow, no ground, no text"

POSES = {
    "frente": "front view, facing the viewer, standing relaxed, full body",
    "tres_quartos": "three-quarter view, body turned slightly to the side, facing right, full body",
    "lado": "side profile view, facing right, full body",
}
EXPRESSOES = {
    "feliz": "a big happy smile, bright joyful eyes",
    "triste": "a gentle sad expression, soft eyes",
    "surpreso": "a surprised expression, mouth open in a small 'o', wide eyes",
    "sono": "a sleepy expression, eyes half closed, small yawn",
    "bravo": "a mildly grumpy expression, puffed cheeks, cute not angry",
}
POSES_PADRAO = ("frente", "tres_quartos", "lado")
# Para onde cada recorte olha na imagem: a animação vira o personagem (espelha) para ele olhar para o centro da cena.
# O modelo nem sempre obedece ao «facing right»; a interface deixa corrigir por recorte (rota /cutouts/{id}/facing).
DIRECOES = ("front", "left", "right")
DIRECAO_DO_SLOT = {"tres_quartos": "right", "lado": "right"}


def direcao_do_slot(slot: str) -> str:
    """De frente para a câmera, salvo as poses de perfil e de três quartos, que o prompt pede olhando para a direita."""
    return DIRECAO_DO_SLOT.get(slot, "front")


EXPRESSOES_PADRAO = ("feliz", "triste", "surpreso")


def _junta(*partes: str) -> str:
    return " ".join(p.strip().rstrip(".") + "." for p in partes if p and p.strip())


# O modelo de imagem entende bem cores e roupas em português, mas erra a espécie (a «coelha» virava ursa). Os bichos e
# personagens mais comuns em histórias infantis ganham a tradução ao lado, sem trocar o texto do criador.
ESPECIES_EM_INGLES = {
    "coelho": "rabbit", "coelha": "rabbit", "coelhinho": "rabbit", "coelhinha": "rabbit",
    "urso": "bear", "ursa": "bear", "ursinho": "teddy bear", "ursinha": "teddy bear",
    "gato": "cat", "gata": "cat", "gatinho": "kitten", "gatinha": "kitten",
    "cachorro": "dog", "cachorra": "dog", "cachorrinho": "puppy", "cachorrinha": "puppy", "cao": "dog",
    "leao": "lion", "leoa": "lioness", "elefante": "elephant", "elefantinho": "baby elephant", "girafa": "giraffe",
    "macaco": "monkey", "macaca": "monkey", "macaquinho": "monkey",
    "porco": "pig", "porquinho": "little pig", "porquinha": "little pig", "vaca": "cow", "boi": "ox",
    "cavalo": "horse", "egua": "horse", "ovelha": "sheep", "ovelhinha": "little sheep", "carneiro": "sheep", "cabra": "goat",
    "pato": "duck", "pata": "duck", "patinho": "duckling", "patinha": "duckling", "galinha": "hen", "galo": "rooster",
    "pinto": "chick", "pintinho": "chick", "pintinha": "chick", "passaro": "bird", "passarinho": "little bird",
    "coruja": "owl", "papagaio": "parrot", "pinguim": "penguin", "cisne": "swan",
    "sapo": "frog", "sapinho": "frog", "perereca": "tree frog", "tartaruga": "turtle", "jacare": "crocodile",
    "cobra": "snake", "peixe": "fish", "peixinho": "little fish", "baleia": "whale", "golfinho": "dolphin",
    "polvo": "octopus", "tubarao": "shark", "caranguejo": "crab", "estrela-do-mar": "starfish",
    "borboleta": "butterfly", "abelha": "bee", "abelhinha": "little bee", "joaninha": "ladybug", "lagarta": "caterpillar",
    "formiga": "ant", "aranha": "spider", "raposa": "fox", "raposinha": "fox", "lobo": "wolf", "panda": "panda",
    "coala": "koala", "tigre": "tiger", "zebra": "zebra", "hipopotamo": "hippo", "rinoceronte": "rhinoceros",
    "camelo": "camel", "esquilo": "squirrel", "rato": "mouse", "ratinho": "mouse", "ratinha": "mouse",
    "morcego": "bat", "veado": "deer", "cervo": "deer", "dinossauro": "dinosaur", "dragao": "friendly dragon",
    "unicornio": "unicorn", "fada": "fairy", "menino": "boy", "menina": "girl", "bebe": "baby", "robo": "robot",
}  # fmt: skip


def especie_em_ingles(especie: str) -> str | None:
    """A tradução da espécie ou do tipo do personagem, se for um dos comuns (procura palavra por palavra)."""
    for palavra in normalizar(especie).replace("/", " ").replace(",", " ").split():
        if palavra in ESPECIES_EM_INGLES:
            return ESPECIES_EM_INGLES[palavra]
    return None


def prompt_personagem(ficha: FichaPersonagem) -> str:
    traducao = especie_em_ingles(ficha.species)
    especie = f"{ficha.species} ({traducao})" if traducao and ficha.species else ficha.species
    quem = ", ".join(p for p in (especie, ficha.apparent_age) if p) or "character"
    return _junta(
        ESTILOS[ficha.style],
        f"Full-body character design of {ficha.name or 'a character'}, {quem}",
        ficha.appearance,
        f"Wearing {ficha.clothing}" if ficha.clothing else "",
        f"Color palette: {ficha.palette}" if ficha.palette else "",
        f"Personality: {ficha.personality}" if ficha.personality else "",
        REGRAS_INFANTIS,
        "Standing in a neutral pose, facing the viewer, centered, full body visible",
        FUNDO_LIMPO,
    )


def prompt_pose(ficha: FichaPersonagem, pose: str) -> str:
    """Pose ou expressão nova do mesmo personagem, a partir da imagem de referência (o modelo edita a referência)."""
    if pose in POSES:
        variacao = POSES[pose]
    elif pose in EXPRESSOES:
        variacao = f"same standing pose, with {EXPRESSOES[pose]}, full body"
    else:
        variacao = pose
    return _junta(
        f"The same character as in the reference image, {variacao}",
        "Keep exactly the same design, colors, proportions, clothing and art style",
        ESTILOS[ficha.style],
        FUNDO_LIMPO,
    )


def prompt_outro_estilo(ficha: FichaPersonagem, estilo_novo: str) -> str:
    """O mesmo personagem no outro estilo (2D para 3D ou o contrário), partindo da referência atual."""
    return _junta(
        f"The same character as in the reference image, redrawn in a different art style. {ESTILOS[estilo_novo]}",
        "Keep the same character design, colors, proportions and clothing",
        "Full body, neutral pose facing the viewer",
        FUNDO_LIMPO,
    )


def prompt_cenario(descricao: str, estilo: str, tem_referencias: bool = False) -> str:
    if tem_referencias:  # o cenário parte de imagens de referência (uma variação, ou com personagens da biblioteca)
        return _junta(
            ESTILOS[estilo],
            "Use the reference image(s) as the visual base, keeping the exact appearance of any character in them",
            f"Background scene for a children's video: {descricao}",
            "Clean uncluttered composition, bright cheerful colors, soft depth, wide view, no text",
        )
    return _junta(
        ESTILOS[estilo],
        f"Background scene for a children's video: {descricao}",
        "No characters, no people, no animals unless described, no text",
        "Clean uncluttered composition, bright cheerful colors, soft depth, wide view",
    )


def prompt_imagem(ficha: FichaImagem, tem_referencias: bool = False) -> str:
    base = ESTILOS[ficha.style]
    if ficha.kind == "cenario":
        return prompt_cenario(ficha.description, ficha.style, tem_referencias) + (
            f" {ficha.notes}" if ficha.notes else ""
        )
    if ficha.kind == "objeto":
        corpo = f"Single object for a children's video: {ficha.description}. Centered, plain solid light background, no text"
    elif ficha.kind == "thumbnail":
        corpo = (
            f"Eye-catching thumbnail for a children's video: {ficha.description}. Bold simple composition, bright colors, "
            "large friendly characters, no text"
        )
    else:
        corpo = ficha.description
    if tem_referencias:
        corpo = f"Include the character(s) from the reference image(s), keeping their exact appearance. {corpo}"
    return _junta(base, corpo, ficha.notes, REGRAS_INFANTIS)


SINONIMOS_DE_EXPRESSAO = {
    "feliz": ("feliz", "alegre", "contente", "sorrindo", "sorriso", "happy"),
    "triste": ("triste", "chateado", "chateada", "sad"),
    "surpreso": ("surpres", "surprised"),
    "sono": ("sono", "sonolent", "sleepy"),
    "bravo": ("bravo", "brava", "bravinh", "zangad", "grumpy"),
}


def expressoes_pedidas(ficha: FichaPersonagem) -> list[str]:
    """As expressões da ficha que o app sabe desenhar (feliz, triste, surpreso...); sem pedido, as três padrão."""
    texto = normalizar(ficha.expressions)
    pedidas = [nome for nome, palavras in SINONIMOS_DE_EXPRESSAO.items() if any(p in texto for p in palavras)]
    return pedidas or list(EXPRESSOES_PADRAO)
