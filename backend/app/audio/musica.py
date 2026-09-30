"""Música infantil instrumental original, gerada por código: melodia simples e repetitiva sobre acordes alegres.

Segue o briefing (seção 8): refrão repetitivo, melodia simples, andamento moderado, tom alegre. A escala é a pentatônica
maior de Dó (nenhuma nota "errada" contra os acordes) e o timbre é macio: marimba ou caixinha de música na melodia,
violão de cordas dedilhadas (Karplus-Strong) nos acordes, baixo suave e um chocalho leve. Mesma semente, mesma música.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

TAXA = 44_100
Onda = npt.NDArray[np.float32]

# notas MIDI da escala pentatônica maior de Dó (C D E G A) em duas oitavas, para a melodia
PENTATONICA = (60, 62, 64, 67, 69, 72, 74, 76, 79, 81)
# acordes (raiz, terça, quinta) em oitava baixa (violão e baixo)
ACORDES = {
    "C": (48, 52, 55),
    "F": (53, 57, 60),
    "G": (55, 59, 62),
    "Am": (57, 60, 64),
}


@dataclass(frozen=True)
class EstiloMusical:
    nome: str
    descricao: str
    bpm: int
    progressao: tuple[str, ...]  # um acorde por compasso (se repete)
    timbre: str  # marimba | caixinha
    percussao: bool
    volume_do_violao: float
    esparso: bool = False  # melodia com pausas (ninar)


ESTILOS: dict[str, EstiloMusical] = {
    "alegre": EstiloMusical("alegre", "Alegre e saltitante", 104, ("C", "F", "G", "C"), "marimba", True, 0.55),
    "calma": EstiloMusical(
        "calma", "Calma, para ninar", 76, ("C", "Am", "F", "G"), "caixinha", False, 0.4, esparso=True
    ),
    "aventura": EstiloMusical("aventura", "Animada, de aventura", 120, ("C", "G", "Am", "F"), "marimba", True, 0.6),
}
ESTILO_PADRAO = "alegre"


def _frequencia(midi: int) -> float:
    return float(440.0 * 2 ** ((midi - 69) / 12))


def _tempo(n: int) -> npt.NDArray[np.float64]:
    return np.arange(n, dtype=np.float64) / TAXA


def _ataque(n: int, ms: float = 3.0) -> npt.NDArray[np.float64]:
    """Subida rápida no começo de cada nota (sem "clique")."""
    rampa = max(1, int(TAXA * ms / 1000))
    envelope = np.ones(n)
    envelope[: min(rampa, n)] = np.linspace(0.0, 1.0, min(rampa, n))
    return envelope


def nota_de_marimba(midi: int, duracao_s: float, forca: float = 1.0) -> Onda:
    n = int(TAXA * duracao_s)
    t = _tempo(n)
    f = _frequencia(midi)
    onda = (
        np.sin(2 * np.pi * f * t) * np.exp(-t / 0.32)
        + 0.32 * np.sin(2 * np.pi * f * 4.0 * t) * np.exp(-t / 0.10)
        + 0.06 * np.sin(2 * np.pi * f * 10.0 * t) * np.exp(-t / 0.04)
    )
    return (onda * _ataque(n) * forca * 0.8).astype(np.float32)


def nota_de_caixinha(midi: int, duracao_s: float, forca: float = 1.0) -> Onda:
    """Caixinha de música: sino com parciais inarmônicos, brilhante e que apaga devagar."""
    n = int(TAXA * duracao_s)
    t = _tempo(n)
    f = _frequencia(midi + 12)
    onda = (
        np.sin(2 * np.pi * f * t) * np.exp(-t / 0.7)
        + 0.30 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t / 0.35)
        + 0.10 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t / 0.15)
    )
    return (onda * _ataque(n) * forca * 0.8).astype(np.float32)


def corda_dedilhada(midi: int, duracao_s: float) -> Onda:
    """Uma corda de violão pelo algoritmo Karplus-Strong (ruído que vira tom ao ser filtrado em laço)."""
    n = int(TAXA * duracao_s)
    periodo = max(2, round(TAXA / _frequencia(midi)))
    acaso = np.random.default_rng(midi * 31 + 7)
    bloco = acaso.uniform(-1.0, 1.0, periodo)
    bloco -= bloco.mean()
    blocos = [bloco]
    while sum(len(b) for b in blocos) < n:
        anterior = blocos[-1]
        blocos.append(0.996 * 0.5 * (anterior + np.roll(anterior, 1)))
    corda = np.concatenate(blocos)[:n]
    return (corda * _ataque(n, 2.0) * 0.55).astype(np.float32)


def acorde_de_violao(acorde: str, duracao_s: float, para_baixo: bool = True) -> Onda:
    """As três cordas do acorde tocadas em sequência rápida (a "batida" do violão)."""
    notas = [n + 12 for n in ACORDES[acorde]]
    if not para_baixo:
        notas = notas[::-1]
    saida = np.zeros(int(TAXA * duracao_s), dtype=np.float32)
    for i, nota in enumerate(notas):
        inicio = int(TAXA * 0.012 * i)
        corda = corda_dedilhada(nota, duracao_s - 0.012 * i)
        saida[inicio : inicio + len(corda)] += corda[: len(saida) - inicio]
    return saida * 0.6


def nota_de_baixo(midi: int, duracao_s: float) -> Onda:
    n = int(TAXA * duracao_s)
    t = _tempo(n)
    f = _frequencia(midi - 12)
    onda = (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * f * 2 * t)) * np.exp(-t / 0.55)
    return (onda * _ataque(n, 6.0) * 0.7).astype(np.float32)


def chocalho(duracao_s: float = 0.06, forca: float = 1.0, semente: int = 1) -> Onda:
    n = int(TAXA * duracao_s)
    ruido = np.random.default_rng(semente).uniform(-1, 1, n)
    agudo = np.diff(ruido, prepend=0.0)  # tira os graves: só o "tss"
    envelope = np.exp(-_tempo(n) / 0.02)
    return (agudo * envelope * 0.25 * forca).astype(np.float32)


def bumbo(forca: float = 1.0) -> Onda:
    n = int(TAXA * 0.16)
    t = _tempo(n)
    frequencia = 50 + 80 * np.exp(-t / 0.03)
    fase = 2 * np.pi * np.cumsum(frequencia) / TAXA
    return (np.sin(fase) * np.exp(-t / 0.07) * 0.6 * forca).astype(np.float32)


def _colocar(faixa: Onda, som: Onda, inicio: int) -> None:
    if inicio >= len(faixa):
        return
    fim = min(len(faixa), inicio + len(som))
    faixa[inicio:fim] += som[: fim - inicio]


# --- melodia -----------------------------------------------------------------------------------------------------------
RITMOS = (  # divisões de um compasso em batidas (soma 4): q = 1 batida, e = meia batida, h = 2
    (1, 1, 1, 1),
    (1, 1, 2),
    (0.5, 0.5, 1, 1, 1),
    (2, 1, 1),
    (1, 0.5, 0.5, 1, 1),
    (1, 1, 0.5, 0.5, 1),
)


def _nota_mais_proxima(alvos: list[int], referencia: int) -> int:
    return min(alvos, key=lambda n: abs(n - referencia))


def melodia(estilo: EstiloMusical, compassos: int, semente: int) -> list[tuple[float, int, float]]:
    """A melodia como lista de (batida de início, nota MIDI, duração em batidas). Frases de 4 compassos, ABAB, fim na tônica."""
    acaso = random.Random(semente)
    notas: list[tuple[float, int, float]] = []
    atual = PENTATONICA[2]
    frases: dict[int, list[tuple[float, ...]]] = {}
    for compasso in range(compassos):
        frase, posicao = divmod(compasso, 4)
        chave = frase % 2  # A B A B: a frase A e a B se repetem
        ritmos = frases.setdefault(chave, [])
        if len(ritmos) <= posicao:
            ritmos.append(acaso.choice(RITMOS))
        ritmo = ritmos[posicao]
        acorde = ACORDES[estilo.progressao[compasso % len(estilo.progressao)]]
        tons_do_acorde = [n + 12 * o for n in acorde for o in (1, 2) if n + 12 * o in PENTATONICA]
        batida = 0.0
        for indice, duracao in enumerate(ritmo):
            if estilo.esparso and indice % 2 == 1 and acaso.random() < 0.5:
                batida += duracao
                continue  # uma pausa (ninar: nem toda batida tem nota)
            if indice == 0:
                atual = _nota_mais_proxima(tons_do_acorde or list(PENTATONICA), atual)
            else:
                posicao_na_escala = PENTATONICA.index(atual)
                passo = acaso.choice((-1, 0, 1, 1, -2, 2))
                atual = PENTATONICA[min(max(posicao_na_escala + passo, 0), len(PENTATONICA) - 1)]
            notas.append((compasso * 4 + batida, atual, duracao))
            batida += duracao
    if notas:  # a música termina em casa: a última nota é a tônica
        ultima = notas[-1]
        notas[-1] = (ultima[0], 72, max(ultima[2], 2.0))
    return notas


def _padrao(estilo: EstiloMusical, compassos: int, semente: int) -> Onda:
    batida_s = 60.0 / estilo.bpm
    total = int(TAXA * compassos * 4 * batida_s)
    faixa = np.zeros(total + TAXA * 2, dtype=np.float32)  # sobra de 2 s para o "rabo" das últimas notas
    nota = nota_de_caixinha if estilo.timbre == "caixinha" else nota_de_marimba
    for inicio_batida, midi, duracao in melodia(estilo, compassos, semente):
        _colocar(faixa, nota(midi, max(0.5, duracao * batida_s * 1.6), 0.9), int(TAXA * inicio_batida * batida_s))
    for compasso in range(compassos):
        acorde = estilo.progressao[compasso % len(estilo.progressao)]
        base = int(TAXA * compasso * 4 * batida_s)
        for batida in range(4):
            inicio = base + int(TAXA * batida * batida_s)
            if estilo.timbre == "caixinha":  # ninar: só o acorde no início do compasso e no meio, bem suave
                if batida in (0, 2):
                    _colocar(faixa, acorde_de_violao(acorde, 1.6, batida == 0) * estilo.volume_do_violao * 0.7, inicio)
            else:
                _colocar(faixa, acorde_de_violao(acorde, 0.9, batida % 2 == 0) * estilo.volume_do_violao, inicio)
            if batida in (0, 2):
                _colocar(faixa, nota_de_baixo(ACORDES[acorde][0], 1.0) * (0.55 if estilo.esparso else 0.8), inicio)
            if estilo.percussao:
                _colocar(faixa, chocalho(0.06, 1.0 if batida % 2 else 0.6, semente + compasso * 4 + batida), inicio)
                _colocar(
                    faixa, chocalho(0.05, 0.5, semente + 99 + compasso * 4 + batida), inicio + int(TAXA * batida_s / 2)
                )
                if batida in (0, 2):
                    _colocar(faixa, bumbo(0.7), inicio)
    return faixa


def duracao_do_padrao(estilo: str = ESTILO_PADRAO, compassos: int = 8) -> float:
    return compassos * 4 * 60.0 / ESTILOS[estilo].bpm


def gerar_musica(
    duracao_s: float, estilo: str = ESTILO_PADRAO, semente: int = 1, entrada_s: float = 1.0, saida_s: float = 2.0
) -> Onda:
    """A trilha com ``duracao_s`` segundos: seções ABAB de 8 compassos, entrada suave e final que apaga devagar."""
    e = ESTILOS.get(estilo, ESTILOS[ESTILO_PADRAO])
    total = int(TAXA * max(duracao_s, 0.5))
    trilha = np.zeros(total, dtype=np.float32)
    secao = 0
    posicao = 0
    while posicao < total:
        pedaco = _padrao(e, 8, semente + (secao % 2) * 1000)
        _colocar(trilha, pedaco, posicao)
        posicao += int(TAXA * 8 * 4 * 60.0 / e.bpm)
        secao += 1
    pico = float(np.abs(trilha).max()) or 1.0
    trilha = trilha / pico * 0.85
    n_entrada, n_saida = min(int(TAXA * entrada_s), total), min(int(TAXA * saida_s), total)
    if n_entrada:
        trilha[:n_entrada] *= np.linspace(0.0, 1.0, n_entrada, dtype=np.float32)
    if n_saida:
        trilha[-n_saida:] *= np.linspace(1.0, 0.0, n_saida, dtype=np.float32)
    return trilha


# --- efeitos sonoros ---------------------------------------------------------------------------------------------------
def _pop() -> Onda:
    n = int(TAXA * 0.18)
    t = _tempo(n)
    frequencia = 200 + 700 * np.exp(-t / 0.02)
    return (np.sin(2 * np.pi * np.cumsum(frequencia) / TAXA) * np.exp(-t / 0.05) * 0.8).astype(np.float32)


def _boing() -> Onda:
    n = int(TAXA * 0.55)
    t = _tempo(n)
    frequencia = (
        260 + 260 * np.sin(np.pi * np.minimum(t / 0.25, 1.0)) * np.exp(-t / 0.5) + 14 * np.sin(2 * np.pi * 22 * t)
    )
    return (np.sin(2 * np.pi * np.cumsum(frequencia) / TAXA) * np.exp(-t / 0.28) * _ataque(n, 4.0) * 0.7).astype(
        np.float32
    )


def _brilho() -> Onda:
    saida = np.zeros(int(TAXA * 1.1), dtype=np.float32)
    for i, midi in enumerate((84, 88, 91, 96)):
        n = int(TAXA * 0.6)
        t = _tempo(n)
        som = np.sin(2 * np.pi * _frequencia(midi) * t) * np.exp(-t / 0.18) * _ataque(n, 2.0) * 0.45
        _colocar(saida, som.astype(np.float32), int(TAXA * 0.07 * i))
    return saida


def _splash() -> Onda:
    n = int(TAXA * 0.7)
    t = _tempo(n)
    ruido = np.random.default_rng(5).uniform(-1, 1, n)
    suave = np.convolve(ruido, np.ones(6) / 6, mode="same")  # tira o agudo: "plosh"
    return (suave * np.exp(-t / 0.18) * _ataque(n, 6.0) * 0.9).astype(np.float32)


def _whoosh() -> Onda:
    n = int(TAXA * 0.8)
    t = _tempo(n)
    ruido = np.random.default_rng(9).uniform(-1, 1, n)
    janela = np.sin(np.pi * t / 0.8) ** 2
    largura = 4 + (np.arange(n) * 20 // n)  # o "vento" muda de timbre ao passar
    saida = np.zeros(n)
    for w in np.unique(largura):
        mascara = largura == w
        saida[mascara] = np.convolve(ruido, np.ones(int(w)) / w, mode="same")[mascara]
    resultado: Onda = (saida * janela * 0.7).astype(np.float32)
    return resultado


def _ding() -> Onda:
    n = int(TAXA * 1.2)
    t = _tempo(n)
    f = _frequencia(84)
    onda = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.5) + 0.3 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t / 0.25)
    return (onda * _ataque(n, 2.0) * 0.5).astype(np.float32)


def _passos() -> Onda:
    saida = np.zeros(int(TAXA * 1.0), dtype=np.float32)
    for i in range(4):
        n = int(TAXA * 0.07)
        t = _tempo(n)
        toque = np.sin(2 * np.pi * 110 * t) * np.exp(-t / 0.02) * 0.6
        _colocar(saida, toque.astype(np.float32), int(TAXA * 0.25 * i))
    return saida


def _chuva() -> Onda:
    n = int(TAXA * 3.0)
    ruido = np.random.default_rng(11).uniform(-1, 1, n)
    suave = np.convolve(ruido, np.ones(3) / 3, mode="same")
    return (suave * 0.18).astype(np.float32)


EFEITOS: dict[str, tuple[str, object]] = {
    "pop": ("Estouro", _pop),
    "boing": ("Pulo", _boing),
    "brilho": ("Brilho mágico", _brilho),
    "splash": ("Respingo", _splash),
    "whoosh": ("Vento", _whoosh),
    "ding": ("Sininho", _ding),
    "passos": ("Passinhos", _passos),
    "chuva": ("Chuva", _chuva),
}
PALAVRAS_DOS_EFEITOS = (
    ("boing", ("boing", "pul", "salt", "quic")),
    ("splash", ("splash", "poca", "agua", "mergulh", "resping", "chapinh")),
    ("brilho", ("brilh", "magi", "estrel", "fada", "encant")),
    ("chuva", ("chuv", "chov", "gotas")),
    ("whoosh", ("vento", "whoosh", "voa", "voar", "zum")),
    ("ding", ("sino", "ding", "campainh")),
    ("passos", ("passos", "passinh", "anda", "camin", "corr")),
    ("pop", ("pop", "estour", "bolha", "balao")),
)


def gerar_efeito(nome: str) -> Onda:
    if nome not in EFEITOS:
        raise KeyError(nome)
    fabrica = EFEITOS[nome][1]
    onda: Onda = fabrica()  # type: ignore[operator]
    return onda


def efeito_do_texto(texto: str) -> str | None:
    """O efeito sonoro que combina com o texto do roteiro (palavras-chave); ``None`` se nada combina."""
    import re

    from ..prompts.parser import normalizar

    n = normalizar(texto)
    if n in EFEITOS:
        return n
    for efeito, radicais in PALAVRAS_DOS_EFEITOS:
        if any(re.search(rf"\b{r}", n) for r in radicais):
            return efeito
    return None
