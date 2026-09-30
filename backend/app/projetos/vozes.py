"""As falas de um projeto: a voz de cada personagem e do narrador, e a geração (com reaproveitamento) de cada linha."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..midias.repositorio import Midia
from ..midias.servico import adotar_e_avisar
from ..motores.audio import preparar_voz
from ..motores.tipos import Contexto, ItemDeVoz
from ..personagens.repositorio import Personagem
from ..personagens.servico import ficha_do_personagem, voz_sugerida, voz_valida
from .cenas import DadosDaCena
from .pipeline import hash_da_fala
from .repositorio import Cena, Projeto

if TYPE_CHECKING:
    from ..container import Servicos

# a voz equivalente ao trocar de idioma (o Kokoro tem vozes diferentes em português e em inglês)
EQUIVALENTE_EM_INGLES = {"pf_dora": "af_heart", "pm_alex": "am_adam", "pm_santa": "am_adam"}
EQUIVALENTE_EM_PORTUGUES = {"af_heart": "pf_dora", "af_bella": "pf_dora", "am_adam": "pm_alex", "bf_emma": "pf_dora"}
NARRADOR_PADRAO = {
    "pt-BR": {"id": "pm_alex", "speed": 0.95, "pitch": 1.0},
    "en": {"id": "am_adam", "speed": 0.95, "pitch": 1.0},
}


def _no_idioma(voz: dict[str, Any], idioma: str) -> dict[str, Any]:
    em_ingles = voz.get("language") == "en"
    if idioma == "en" and not em_ingles:
        return voz_valida({**voz, "id": EQUIVALENTE_EM_INGLES.get(str(voz.get("id")), "af_heart")})
    if idioma != "en" and em_ingles:
        return voz_valida({**voz, "id": EQUIVALENTE_EM_PORTUGUES.get(str(voz.get("id")), "pf_dora")})
    return voz_valida(voz)


def voz_do_personagem(projeto: Projeto, personagem: Personagem) -> dict[str, Any]:
    """A voz cadastrada no personagem (ou uma que a ficha sugere), no idioma do projeto; o projeto pode trocar a de um personagem."""
    ajuste = (projeto.configuracoes.get("voices") or {}).get(personagem.id)
    base = ajuste or personagem.voz or voz_sugerida(ficha_do_personagem(personagem))
    return _no_idioma(base, projeto.idioma)


def voz_do_narrador(projeto: Projeto) -> dict[str, Any]:
    escolhida = projeto.configuracoes.get("narrator") or NARRADOR_PADRAO["en" if projeto.idioma == "en" else "pt-BR"]
    return _no_idioma(escolhida, projeto.idioma)


def texto_para_falar(texto: str) -> str:
    """Tira marcações que o sintetizador leria em voz alta (asteriscos, hashtags, emojis, aspas de lista)."""
    limpo = re.sub(r"[*_#`~<>\[\]{}|\\^]+", " ", texto)
    limpo = re.sub(r"[\U0001F000-\U0001FFFF☀-➿]+", " ", limpo)
    return " ".join(limpo.split())


@dataclass(frozen=True)
class FalaPronta:
    indice: int
    character_id: str | None
    texto: str
    midia: Midia
    duracao_s: float


def _fala_existente(sv: Servicos, cena_id: str, codigo: str) -> Midia | None:
    for midia in sv.midias.listar(papeis=("fala",), dono_tipo="cena", dono_id=cena_id, limite=300):
        if midia.metadados.get("hash") == codigo:
            return midia
    return None


def gerar_falas(
    ctx: Contexto,
    sv: Servicos,
    projeto: Projeto,
    cenas: list[tuple[Cena, DadosDaCena]],
    personagens: dict[str, Personagem],
    faixa: tuple[float, float] = (0.0, 1.0),
) -> dict[str, list[FalaPronta]]:
    """Fala todas as linhas das cenas. Linha que já foi falada com o mesmo texto e a mesma voz é reaproveitada (não gasta tempo)."""
    prontas: dict[str, dict[int, FalaPronta]] = {cena.id: {} for cena, _ in cenas}
    pendentes: list[tuple[Cena, int, str | None, str, dict[str, Any], str]] = []
    for cena, dados in cenas:
        for indice, fala in enumerate(dados.falas()):
            personagem = personagens.get(fala.character_id) if fala.character_id else None
            voz = voz_do_personagem(projeto, personagem) if personagem else voz_do_narrador(projeto)
            texto = texto_para_falar(fala.text)
            if not texto:
                continue
            codigo = hash_da_fala(texto, voz, projeto.idioma)
            existente = _fala_existente(sv, cena.id, codigo)
            if existente is not None:
                prontas[cena.id][indice] = FalaPronta(
                    indice, fala.character_id, texto, existente, float(existente.duracao_s or 0.0)
                )
            else:
                pendentes.append((cena, indice, fala.character_id, texto, voz, codigo))
    if pendentes:
        sv.settings.temp_dir.mkdir(parents=True, exist_ok=True)
        base = faixa[0] + (faixa[1] - faixa[0]) * 0.0
        meio = faixa[0] + (faixa[1] - faixa[0]) * 0.75
        brutos = [
            sv.settings.temp_dir / f"fala-{cena.id[:8]}-{indice}-{codigo}.wav"
            for cena, indice, _, _, _, codigo in pendentes
        ]
        itens = [
            ItemDeVoz(texto, voz["id"], voz["speed"], voz["lang_code"], bruto)
            for (_, _, _, texto, voz, _), bruto in zip(pendentes, brutos, strict=True)
        ]
        ctx.log(f"Falando {len(itens)} linha(s) com o Kokoro")
        sv.motores.voz.falar(ctx, itens, faixa=(base, meio))
        for i, ((cena, indice, personagem_id, texto, voz, codigo), bruto) in enumerate(
            zip(pendentes, brutos, strict=True)
        ):
            ctx.ponto_de_controle()
            ctx.progresso(meio + (faixa[1] - meio) * (i / len(pendentes)), None)
            final = sv.settings.temp_dir / f"voz-{cena.id[:8]}-{indice}-{codigo}.wav"
            try:
                preparar_voz(sv.motores.ffmpeg, ctx, bruto, final, float(voz["pitch"]))
            finally:
                bruto.unlink(missing_ok=True)
            duracao = sv.motores.ffmpeg.sondar(final).duracao_s
            midia = adotar_e_avisar(
                sv,
                final,
                tipo="audio",
                papel="fala",
                extensao="wav",
                duracao_s=duracao,
                dono_tipo="cena",
                dono_id=cena.id,
                prompt=texto,
                modelo="Kokoro 82M",
                job_id=getattr(ctx, "job_id", None),
                metadados={
                    "hash": codigo,
                    "index": indice,
                    "character_id": personagem_id,
                    "voice": voz,
                    "project_id": projeto.id,
                },
            )
            prontas[cena.id][indice] = FalaPronta(indice, personagem_id, texto, midia, duracao)
    return {cena_id: [f for _, f in sorted(itens.items())] for cena_id, itens in prontas.items()}
