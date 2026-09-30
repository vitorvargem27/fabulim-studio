"""Roda a qualidade do projeto com um comando: lint, tipos, testes, cobertura, build e ponta a ponta.

Uso:
    python scripts/testar.py               # tudo (o ponta a ponta usa o Edge e leva alguns minutos)
    python scripts/testar.py --rapido      # sem build e sem ponta a ponta
    python scripts/testar.py --hw          # inclui o coletor de hardware na máquina real (lento)
    python scripts/testar.py --auditoria   # inclui pip-audit e npm audit (precisa de internet)
    python scripts/testar.py -x            # para no primeiro passo que falhar (é o que o pre-commit usa)

Nada é fingido: o que não puder rodar aparece como PULOU, com o motivo. Sai com código 1 se algum passo FALHOU.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BACKEND = RAIZ / "backend"
FRONTEND = RAIZ / "frontend"
PY = RAIZ / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PYTHON = str(PY) if PY.exists() else sys.executable
NPM = shutil.which("npm")
NODE = shutil.which("node")
PASTA_TEMP = RAIZ / "tmp" / f"testar-{os.getpid()}"


def _ambiente_temporario() -> dict[str, str]:
    """TMP, TEMP e TMPDIR próprios desta execução, dentro do projeto (a pasta `tmp/` é ignorada pelo git).

    Os testes de Python ficam independentes do TEMP da máquina, que pode estar sem permissão de escrita (sandbox, ou
    hook do git rodado por um shell que troca o TEMP por /tmp), e não deixam lixo na pasta temporária do usuário.
    """
    PASTA_TEMP.mkdir(parents=True, exist_ok=True)
    return {"TMP": str(PASTA_TEMP), "TEMP": str(PASTA_TEMP), "TMPDIR": str(PASTA_TEMP)}


@dataclass
class Resultado:
    nome: str
    estado: str  # PASSOU | FALHOU | PULOU
    detalhe: str = ""
    segundos: float = 0.0
    saida: str = ""


def _rodar(
    comando: list[str], *, cwd: Path = RAIZ, env: dict[str, str] | None = None, timeout: int = 2400
) -> subprocess.CompletedProcess[str]:
    ambiente = dict(os.environ)
    ambiente["PYTHONPATH"] = str(BACKEND) + os.pathsep + ambiente.get("PYTHONPATH", "")
    ambiente["PYTHONIOENCODING"] = "utf-8"
    ambiente["NG_CLI_ANALYTICS"] = "false"
    ambiente["NO_COLOR"] = "1"
    ambiente.pop("FORCE_COLOR", None)
    if env:
        ambiente.update(env)
    return subprocess.run(
        comando,
        cwd=cwd,
        env=ambiente,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _resultado(p: subprocess.CompletedProcess[str], detalhe: str = "") -> Resultado:
    return Resultado("", "PASSOU" if p.returncode == 0 else "FALHOU", detalhe, 0.0, p.stdout + p.stderr)


def _pulou(motivo: str) -> Resultado:
    return Resultado("", "PULOU", motivo)


def _ferramenta_python(modulo: str) -> bool:
    return subprocess.run([PYTHON, "-c", f"import {modulo}"], capture_output=True).returncode == 0


def _tem_frontend() -> str | None:
    """Motivo para pular os passos do frontend, ou None se dá para rodar."""
    if not NPM:
        return "npm não encontrado (instale o Node.js 22)"
    if not (FRONTEND / "node_modules").exists():
        return "frontend/node_modules ausente: rode `npm --prefix frontend ci`"
    return None


# --- passos de Python ---------------------------------------------------------------------------------------------
def passo_lint_python() -> Resultado:
    if not _ferramenta_python("ruff"):
        return _pulou("ruff não instalado no .venv (`pip install -r backend/requirements-dev.txt`)")
    a = _rodar([PYTHON, "-m", "ruff", "check", "backend", "scripts"])
    b = _rodar([PYTHON, "-m", "ruff", "format", "--check", "backend", "scripts"])
    ok = a.returncode == 0 and b.returncode == 0
    return Resultado("", "PASSOU" if ok else "FALHOU", "", 0.0, a.stdout + a.stderr + b.stdout + b.stderr)


def passo_tipos_python() -> Resultado:
    if not _ferramenta_python("mypy"):
        return _pulou("mypy não instalado no .venv")
    p = _rodar([PYTHON, "-m", "mypy"])
    return _resultado(p, (re.search(r"(Success:.*|Found \d+ errors?.*)", p.stdout) or [""])[0])


def passo_testes_python() -> Resultado:
    if not _ferramenta_python("pytest"):
        return _pulou("pytest não instalado no .venv")
    cobertura = _ferramenta_python("pytest_cov")
    # o -q já vem do addopts do pyproject (com dois, some o resumo); -rfEs lista os que falharam, os com erro e os pulados
    # (com o motivo). O -r sozinho troca o padrão do pytest: sem o «fE» a falha sumiria da lista.
    comando = [PYTHON, "-m", "pytest", "-p", "no:cacheprovider", "-rfEs", "--tb=short"]
    if cobertura:
        comando += ["--cov", "--cov-report=term:skip-covered"]
    p = _rodar(comando, env=_ambiente_temporario())
    return _resultado(p, resumo_pytest(p.stdout + p.stderr, cobertura))


def resumo_pytest(texto: str, cobertura_medida: bool = True) -> str:
    """Uma linha com o número de testes, a cobertura e os testes pulados (com o motivo, para nada sumir em silêncio)."""
    passou = re.search(r"(\d+) passed", texto)
    total = re.search(r"TOTAL\s+.*?(\d+)%", texto)
    detalhe = f"{passou.group(1)} testes" if passou else "sem resumo"
    if total:
        detalhe += f"; cobertura {total.group(1)}% (mínimo 80%)"
    elif not cobertura_medida:
        detalhe += "; cobertura não medida (pytest-cov ausente)"
    motivos = sorted({m.group(1).strip() for m in re.finditer(r"^SKIPPED \[\d+\] .+?:\d+: (.*)$", texto, re.MULTILINE)})
    if motivos:
        detalhe += f"; pulado(s) neste ambiente: {'; '.join(motivos)}"
    return detalhe


# --- passos do frontend -------------------------------------------------------------------------------------------
def passo_lint_frontend() -> Resultado:
    if (motivo := _tem_frontend()) or not NPM:
        return _pulou(motivo or "npm ausente")
    return _resultado(_rodar([NPM, "--prefix", str(FRONTEND), "run", "lint"]))


def passo_testes_frontend() -> Resultado:
    if (motivo := _tem_frontend()) or not NPM:
        return _pulou(motivo or "npm ausente")
    comando = [NPM, "--prefix", str(FRONTEND), "run", "test", "--", "--watch=false"]
    com_cobertura = (FRONTEND / "node_modules" / "@vitest" / "coverage-v8").exists()
    if com_cobertura:
        comando.append("--coverage")
    p = _rodar(comando)
    texto = p.stdout + p.stderr
    testes = re.search(r"Tests\s+(\d+) passed", texto)
    total = re.search(r"All files\s*\|\s*([\d.]+)", texto)
    detalhe = f"{testes.group(1)} testes" if testes else "sem resumo"
    if total:
        detalhe += f"; cobertura {float(total.group(1)):.0f}% de instruções (mínimo 70%)"
    elif not com_cobertura:
        detalhe += "; cobertura não medida (@vitest/coverage-v8 ausente)"
    return _resultado(p, detalhe)


def passo_build_frontend() -> Resultado:
    if (motivo := _tem_frontend()) or not NPM:
        return _pulou(motivo or "npm ausente")
    p = _rodar([NPM, "--prefix", str(FRONTEND), "run", "build"])
    tempo = re.search(r"complete\. \[([\d.]+) seconds\]", p.stdout + p.stderr)
    inicial = re.search(r"Initial total\s*\|\s*([\d.]+ \w+)\s*\|\s*([\d.]+ \w+)", p.stdout + p.stderr)
    detalhe = ""
    if inicial:
        detalhe = f"inicial {inicial.group(1)} ({inicial.group(2)} transferidos)"
    if tempo:
        detalhe += f"; {tempo.group(1)} s"
    return _resultado(p, detalhe)


def passo_e2e() -> Resultado:
    if (motivo := _tem_frontend()) or not NPM or not NODE:
        return _pulou(motivo or "node ausente")
    if not (FRONTEND / "dist" / "frontend" / "browser" / "index.html").exists():
        return _pulou("interface não compilada (rode sem --rapido para compilar antes)")
    prep = _rodar([NODE, "e2e/preparar.mjs"], cwd=FRONTEND)
    if prep.returncode != 0:
        return _resultado(prep)
    p = _rodar(
        [NPM, "exec", "--", "playwright", "test", "app", "ferramentas", "--reporter=line"], cwd=FRONTEND, timeout=3600
    )
    texto = p.stdout + p.stderr
    passou = re.search(r"(\d+) passed", texto)
    falhou = re.search(r"(\d+) failed", texto)
    pulou = re.search(r"(\d+) skipped", texto)
    detalhe = ", ".join(
        x
        for x in (
            f"{passou.group(1)} passaram" if passou else "",
            f"{falhou.group(1)} falharam" if falhou else "",
            f"{pulou.group(1)} pulados" if pulou else "",
        )
        if x
    )
    return _resultado(
        p,
        detalhe
        + " (Edge; desktop, tablet e celular, mais o percurso das ferramentas com motores falsos; axe incluído)",
    )


# --- opcionais ----------------------------------------------------------------------------------------------------
def passo_hardware_real() -> Resultado:
    p = _rodar([PYTHON, "-m", "pytest", "-p", "no:cacheprovider", "-m", "hw"], env=_ambiente_temporario(), timeout=1800)
    return _resultado(p, (re.search(r"\d+ passed.*", p.stdout) or [""])[0])


def passo_auditoria() -> Resultado:
    saidas = []
    estado = "PASSOU"
    if _ferramenta_python("pip_audit"):
        p = _rodar(
            [PYTHON, "-m", "pip_audit", "-r", str(BACKEND / "requirements.txt"), "--progress-spinner", "off"],
            timeout=600,
        )
        saidas.append("pip-audit (dependências de execução):\n" + p.stdout + p.stderr)
        if p.returncode != 0:
            estado = "FALHOU"
    else:
        saidas.append("pip-audit ausente")
    if NPM and not _tem_frontend():
        p = _rodar([NPM, "--prefix", str(FRONTEND), "audit", "--audit-level=high"], timeout=600)
        saidas.append("npm audit (nível alto ou crítico):\n" + p.stdout + p.stderr)
        if p.returncode != 0:
            estado = "FALHOU"
    return Resultado(
        "",
        estado,
        "sem vulnerabilidades altas ou críticas" if estado == "PASSOU" else "veja a saída",
        0.0,
        "\n".join(saidas),
    )


PASTA_DAS_SAIDAS = RAIZ / "tmp" / "testar-ultimo"


def trecho_da_saida(saida: str, limite: int = 6000) -> str:
    """O que interessa da saída de um passo que falhou: o fim dela, sem a tabela de cobertura (que ocupa o lugar da falha)."""
    texto = saida.rstrip()
    tabela = re.search(r"^-+ coverage: .*$", texto, re.MULTILINE)
    if not tabela:
        return texto[-limite:]
    antes = texto[: tabela.start()].rstrip()
    resumo = texto.splitlines()[-1]  # a linha «N failed, M passed in ...»
    return f"{antes[-limite:]}\n... (tabela de cobertura omitida)\n{resumo}"


def guardar_saidas(falhas: list[Resultado]) -> Path:
    """Grava a saída completa de cada passo que falhou (a tela só mostra o fim); apaga o que sobrou da execução anterior."""
    shutil.rmtree(PASTA_DAS_SAIDAS, ignore_errors=True)
    PASTA_DAS_SAIDAS.mkdir(parents=True, exist_ok=True)
    for posicao, r in enumerate(falhas, start=1):
        nome = re.sub(r"[^a-z0-9]+", "-", r.nome.lower()).strip("-")
        (PASTA_DAS_SAIDAS / f"{posicao:02d}-{nome}.txt").write_text(r.saida, encoding="utf-8")
    return PASTA_DAS_SAIDAS


def _medir(nome: str, funcao: Callable[[], Resultado]) -> Resultado:
    inicio = time.perf_counter()
    r = funcao()
    r.nome = nome
    r.segundos = time.perf_counter() - inicio
    return r


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            fluxo.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rapido", action="store_true", help="pula o build e o ponta a ponta")
    ap.add_argument("--hw", action="store_true", help="inclui o coletor na máquina real (lento)")
    ap.add_argument("--auditoria", action="store_true", help="inclui pip-audit e npm audit")
    ap.add_argument("-x", "--parar-no-primeiro-erro", action="store_true", help="para no primeiro passo que falhar")
    args = ap.parse_args(argv)

    passos: list[tuple[str, Callable[[], Resultado]]] = [
        ("Python: lint e formatação (ruff)", passo_lint_python),
        ("Python: tipos (mypy strict)", passo_tipos_python),
        ("Python: testes e cobertura (pytest)", passo_testes_python),
        ("Frontend: lint (ESLint + acessibilidade de templates)", passo_lint_frontend),
        ("Frontend: testes e cobertura (Vitest)", passo_testes_frontend),
    ]
    if not args.rapido:
        passos += [
            ("Frontend: build de produção", passo_build_frontend),
            ("Ponta a ponta (Playwright no Edge)", passo_e2e),
        ]
    if args.hw:
        passos.append(("Hardware real (coletor nesta máquina)", passo_hardware_real))
    if args.auditoria:
        passos.append(("Auditoria de dependências", passo_auditoria))

    resultados = []
    interrompido = False
    try:
        for nome, funcao in passos:
            print(f"... {nome}", flush=True)
            resultados.append(_medir(nome, funcao))
            if args.parar_no_primeiro_erro and resultados[-1].estado == "FALHOU":
                interrompido = len(resultados) < len(passos)
                break
    finally:
        shutil.rmtree(PASTA_TEMP, ignore_errors=True)  # a pasta temporária desta execução não fica para trás

    print()
    print("Resumo do testar")
    print("-" * 100)
    for r in resultados:
        detalhe = f" ({r.detalhe})" if r.detalhe else ""
        print(f"[{r.estado:<6}] {r.nome:<54} {r.segundos:7.1f}s{detalhe}")
    print("-" * 100)

    falhas = [r for r in resultados if r.estado == "FALHOU"]
    for r in falhas:
        print(f"\n===== saída de: {r.nome} =====")
        print(trecho_da_saida(r.saida))
    if falhas:
        print(f"\nA saída completa de cada passo que falhou ficou em {guardar_saidas(falhas).relative_to(RAIZ)}")
    pulados = [r for r in resultados if r.estado == "PULOU"]
    if falhas:
        print(f"\nFALHOU: {len(falhas)} passo(s)." + (" Os passos seguintes não rodaram (-x)." if interrompido else ""))
        return 1
    print(f"\nTUDO CERTO ({len(resultados) - len(pulados)} passos rodaram; {len(pulados)} pulado(s) com motivo).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
