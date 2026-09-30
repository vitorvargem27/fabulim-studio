"""Lista as dependências (Python e npm) com versão e licença lidas dos metadados dos próprios pacotes.

Uso:
    python scripts/licencas.py               # imprime a tabela em Markdown
    python scripts/licencas.py --atualizar   # grava a tabela em docs/LICENCAS.md (entre os marcadores)

Rode com o Python do .venv (é dele que vêm os metadados). Licença fora da lista de permitidas aparece como "revisar".
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.metadata as md
import json
import re
import sys
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
INICIO = "<!-- deps:inicio -->"
FIM = "<!-- deps:fim -->"

# Licenças que permitem uso comercial sem restrição sobre os resultados (briefing, seção 5). MPL-2.0 é copyleft fraco
# (por arquivo): aceito porque não modificamos nem distribuímos esses pacotes (certifi em execução; o resto só em
# desenvolvimento). A observação fica em docs/LICENCAS.md.
PERMITIDAS = (
    "MIT",
    "BSD",
    "APACHE",
    "ISC",
    "OFL",
    "PSF",
    "PYTHON",
    "0BSD",
    "BLUEOAK",
    "UNLICENSE",
    "CC0",
    "MPL-2.0",
    "MPL 2.0",
    "ZLIB",
)


# Pacotes cuja licença o gerador não reconhece sozinho e que já foram conferidos na fonte (o texto completo de cada caso
# está em docs/LICENCAS.md). Sem isto eles apareceriam como "revisar" para sempre.
REVISADOS: dict[str, tuple[str, str]] = {
    "kokoro-onnx": ("MIT (conferida no GitHub; o PyPI não informa)", "sim"),
    "espeakng-loader": ("MIT (o carregador; leva o espeak-ng, GPL-3.0, junto)", "sim, com ressalva (GPL embutida)"),
    "phonemizer": ("GPL-3.0-or-later", "sim, com ressalva (GPL, uso local)"),
}


def _nome(n: str) -> str:
    return re.sub(r"[-_.]+", "-", n).lower()


def _requisitos(arquivo: Path) -> set[str]:
    nomes: set[str] = set()
    if arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith(("#", "-")):
                nomes.add(_nome(re.split(r"[=<>!~\[ ;]", linha, maxsplit=1)[0]))
    return nomes


def _licenca_python(dist: md.Distribution) -> str:
    meta = dist.metadata
    if expr := meta.get("License-Expression"):
        return str(expr)
    if (lic := meta.get("License")) and len(lic) < 60:
        return lic.strip().splitlines()[0]
    classes = [c.split("::")[-1].strip() for c in (meta.get_all("Classifier") or []) if c.startswith("License ::")]
    return "; ".join(classes) or "desconhecida"


def _permitida(licenca: str) -> bool:
    texto = licenca.upper()
    return any(p in texto for p in PERMITIDAS)


def python_deps() -> list[dict[str, str]]:
    runtime = _requisitos(RAIZ / "backend" / "requirements.txt")
    linhas: list[dict[str, str]] = []
    for dist in sorted(md.distributions(), key=lambda d: _nome(d.metadata["Name"] or "")):
        nome = dist.metadata["Name"] or "?"
        chave = _nome(nome)
        if chave in ("pip", "setuptools", "wheel"):
            continue
        licenca, comercial = REVISADOS.get(chave, (_licenca_python(dist), ""))
        linhas.append(
            {
                "nome": nome,
                "versao": dist.version,
                "licenca": licenca,
                "uso": "execução" if chave in runtime else "desenvolvimento",
                "revisado": comercial,
            }
        )
    return linhas


def npm_deps() -> list[dict[str, str]]:
    pacote = json.loads((RAIZ / "frontend" / "package.json").read_text(encoding="utf-8"))
    linhas: list[dict[str, str]] = []
    for uso, chave in (("execução", "dependencies"), ("desenvolvimento", "devDependencies")):
        for nome in sorted(pacote.get(chave, {})):
            arquivo = RAIZ / "frontend" / "node_modules" / nome / "package.json"
            if not arquivo.exists():
                linhas.append({"nome": nome, "versao": "?", "licenca": "não instalado", "uso": uso})
                continue
            info: dict[str, Any] = json.loads(arquivo.read_text(encoding="utf-8"))
            lic = info.get("license") or info.get("licenses") or "desconhecida"
            if isinstance(lic, dict):
                lic = lic.get("type", "desconhecida")
            if isinstance(lic, list):
                lic = " OR ".join(str(x.get("type", x)) if isinstance(x, dict) else str(x) for x in lic)
            linhas.append({"nome": nome, "versao": str(info.get("version", "?")), "licenca": str(lic), "uso": uso})
    return linhas


def tabela(titulo: str, linhas: list[dict[str, str]]) -> str:
    saida = [f"### {titulo}", "", "| Pacote | Versão | Licença | Uso | Comercial |", "|---|---|---|---|---|"]
    for d in linhas:
        ok = d.get("revisado") or ("sim" if _permitida(d["licenca"]) else "**revisar**")
        saida.append(f"| {d['nome']} | {d['versao']} | {d['licenca']} | {d['uso']} | {ok} |")
    return "\n".join(saida)


def gerar() -> tuple[str, int]:
    py, js = python_deps(), npm_deps()
    revisar = sum(not (d.get("revisado") or _permitida(d["licenca"])) for d in py + js)
    texto = f"{tabela('Python (.venv)', py)}\n\n{tabela('Frontend (npm, dependências diretas)', js)}\n"
    return texto, revisar


def main() -> int:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--atualizar", action="store_true", help="grava em docs/LICENCAS.md")
    args = ap.parse_args()
    texto, revisar = gerar()
    if not args.atualizar:
        print(texto)
        return 1 if revisar else 0
    alvo = RAIZ / "docs" / "LICENCAS.md"
    conteudo = alvo.read_text(encoding="utf-8")
    novo = f"{INICIO}\n\n{texto}\n{FIM}"
    if INICIO in conteudo and FIM in conteudo:
        conteudo = re.sub(f"{re.escape(INICIO)}.*?{re.escape(FIM)}", lambda _m: novo, conteudo, flags=re.DOTALL)
    else:
        conteudo = conteudo.rstrip() + f"\n\n{novo}\n"
    alvo.write_text(conteudo, encoding="utf-8", newline="\n")
    print(f"docs/LICENCAS.md atualizado ({revisar} pacote(s) para revisar).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
