"""Classifica o perfil da máquina e gera docs/AMBIENTE.md a partir de config/hardware.json.

Uso:
    python scripts/perfil.py [--hardware config/hardware.json] [--docs docs/AMBIENTE.md] [--json] [--sem-docs]

Só biblioteca padrão. Chamado por scripts/diagnostico.ps1|.sh depois da coleta.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

from app.hardware import (  # o sys.path precisa ser ajustado antes deste import
    HardwareInvalido,
    classificar,
    ferramentas_pendentes,
    python_do_projeto,
    renderizar_ambiente,
)


def _console_utf8() -> None:
    for fluxo in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            fluxo.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]


def main(argv: list[str] | None = None) -> int:
    _console_utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hardware", type=Path, default=RAIZ / "config" / "hardware.json")
    ap.add_argument("--docs", type=Path, default=RAIZ / "docs" / "AMBIENTE.md")
    ap.add_argument("--json", action="store_true", help="imprime a classificação em JSON e sai")
    ap.add_argument("--sem-docs", action="store_true", help="não escreve o AMBIENTE.md")
    args = ap.parse_args(argv)

    try:
        hw = json.loads(args.hardware.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        print(f"Não achei {args.hardware}. Rode scripts/diagnostico primeiro.", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"{args.hardware} não é um JSON válido: {exc}", file=sys.stderr)
        return 2

    try:
        c = classificar(hw)
    except HardwareInvalido as exc:
        print("hardware.json inválido:", file=sys.stderr)
        for erro in exc.erros:
            print(f"  - {erro}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(c.para_dict(), ensure_ascii=False, indent=2))
        return 0

    print(f"Perfil {c.perfil}: {c.nome}")
    for j in c.justificativa:
        print(f"  - {j}")
    for a in c.avisos:
        print(f"  ! {a}")
    python_do_app = python_do_projeto(RAIZ)  # o ambiente virtual do projeto, se já existe
    pendencias = ferramentas_pendentes(hw, python_do_app)
    if pendencias:
        print("Pendências do ambiente:")
        for p in pendencias:
            print(f"  - {p.item} ({p.estado}): {p.acao}")

    if not args.sem_docs:
        args.docs.parent.mkdir(parents=True, exist_ok=True)
        args.docs.write_text(renderizar_ambiente(hw, c, python_do_app), encoding="utf-8", newline="\n")
        try:
            destino = args.docs.relative_to(RAIZ)
        except ValueError:
            destino = args.docs
        print(f"Relatório gravado em {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
