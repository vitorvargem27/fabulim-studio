"""Instala as ferramentas e os modelos do Fabulim dentro do projeto (pastas `tools/` e `models/`).

Uso:
    python scripts/instalar.py --lista              # o que existe e o que já está instalado
    python scripts/instalar.py --tudo               # instala tudo o que falta (leva algum tempo: ~6 GB)
    python scripts/instalar.py ffmpeg sd-cpp        # só estes itens (ids da lista)

Tudo vem de fonte oficial (GitHub e Hugging Face) e o SHA-256 é conferido contra o que a própria fonte publica; o que não
tiver hash publicado não é instalado. Nada é instalado no sistema: só dentro da pasta do projeto. As bibliotecas Python
dos modelos (numpy, onnxruntime, kokoro-onnx...) vêm com o app: `pip install -r backend/requirements.txt`.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

from app.config import carregar_configuracao  # noqa: E402
from app.ferramentas.catalogo import ITENS, por_id  # noqa: E402
from app.ferramentas.instalador import ErroDeInstalacao, Instalador  # noqa: E402
from app.security.downloads import DownloadInseguro  # noqa: E402


def _tamanho(n: int | float) -> str:
    return f"{n / 1024**3:.2f} GB" if n >= 1024**3 else f"{n / 1024**2:.0f} MB"


class Painel:
    """Uma linha de progresso por item, atualizada no máximo a cada 2 segundos."""

    def __init__(self, nome: str) -> None:
        self.nome = nome
        self.ultimo = 0.0
        self.inicio = time.monotonic()

    def __call__(self, etapa: str, feitos: int, total: int) -> None:
        agora = time.monotonic()
        if etapa != "baixando":
            print(f"    {self.nome}: {etapa}...", flush=True)
            return
        if agora - self.ultimo < 2 and feitos < total:
            return
        self.ultimo = agora
        velocidade = feitos / max(agora - self.inicio, 0.1)
        print(
            f"    {self.nome}: {_tamanho(feitos)} de {_tamanho(total)} ({100 * feitos / total:.0f}%), {_tamanho(velocidade)}/s",
            flush=True,
        )


def listar(inst: Instalador) -> None:
    print(f"{'id':16} {'estado':12} {'tamanho':>9}  o que é")
    for item, situacao in zip(ITENS, inst.situacao(), strict=True):
        estado = "instalado" if situacao["installed"] else "falta"
        tamanho = _tamanho(situacao["size_bytes"]) if situacao["size_bytes"] else "-"
        print(f"{item.id:16} {estado:12} {tamanho:>9}  {item.nome} [{item.licenca}]")


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            fluxo.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("itens", nargs="*", help="ids a instalar (veja --lista)")
    ap.add_argument("--lista", action="store_true", help="mostra o que existe e o que já está instalado")
    ap.add_argument("--tudo", action="store_true", help="instala tudo o que falta")
    args = ap.parse_args(argv)

    settings = carregar_configuracao()
    inst = Instalador(settings)
    if args.lista or not (args.itens or args.tudo):
        listar(inst)
        return 0

    escolhidos = list(ITENS) if args.tudo else [por_id(i) for i in args.itens]
    falhas = 0
    for n, item in enumerate(escolhidos, 1):
        print(f"[{n}/{len(escolhidos)}] {item.nome}", flush=True)
        try:
            resultado = inst.instalar(item, Painel(item.id))
        except (ErroDeInstalacao, DownloadInseguro) as exc:
            print(f"    NÃO INSTALADO: {exc}", flush=True)
            falhas += 1
            continue
        print(f"    {'já estava instalado' if resultado.situacao == 'ja_instalado' else 'instalado'}", flush=True)
    print(f"\nPronto: {len(escolhidos) - falhas} de {len(escolhidos)} itens em ordem.")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
