"""Serviço do Windows do Fabulim Studio: sobe o servidor junto com o Windows e o mantém sempre no ar.

Uso (numa janela de administrador; o `servico.bat` da raiz faz o mesmo):
    python scripts/servico_windows.py instalar   # cria o serviço «FabulimStudio» (inicia com o Windows) e já o liga
    python scripts/servico_windows.py remover    # para e apaga o serviço
    python scripts/servico_windows.py iniciar | parar | status

Como funciona: o serviço é só um **supervisor**. Ele roda `scripts/servidor.py` (o mesmo do `iniciar.bat`, só em 127.0.0.1)
como processo filho e, se o filho morrer ou parar de responder em `/api/health`, encerra o que sobrou e sobe de novo, com
espera crescente entre as tentativas (2, 5, 10 e 30 s) para não ficar num laço apertado se algo estiver quebrado. Se o próprio
supervisor cair, o Windows o reinicia (ação de recuperação do serviço). O que o servidor escreve fica em `data/logs/`.

Depende do `pywin32` (só no Windows; `pip install -r backend/requirements-servico.txt`). Nada é instalado no sistema além do
próprio serviço.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
NOME = "FabulimStudio"
NOME_NA_TELA = "Fabulim Studio (servidor local)"
DESCRICAO = (
    "Mantém o servidor local do Fabulim Studio sempre no ar em 127.0.0.1: sobe com o Windows e sobe de novo se cair."
)
PYTHON = RAIZ / ".venv" / "Scripts" / "python.exe"
SERVIDOR = RAIZ / "scripts" / "servidor.py"
PASTA_DE_LOGS = RAIZ / "data" / "logs"
ESPERAS = (2, 5, 10, 30)  # segundos entre uma tentativa e a próxima
TOLERANCIA_DE_INICIO = 180  # o servidor leva mais para subir com o computador ocupado: só cobra a saúde depois disso
INTERVALO_DA_SAUDE = 30
FALHAS_SEGUIDAS = 3
ESTAVEL_DEPOIS_DE = 120  # rodou tanto tempo sem cair: zera a espera crescente

# o serviço em si precisa estar no nível do módulo (o Windows importa a classe pelo nome)
try:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil

    TEM_PYWIN32 = True
except ImportError:  # sem o pywin32 dá para usar o resto (e os testes do supervisor)
    TEM_PYWIN32 = False


def porta_do_servidor() -> int:
    """A porta em que o servidor vai escutar (vale a variável de ambiente, depois o `.env`, depois 8765)."""
    proc = subprocess.run(
        [str(PYTHON), str(SERVIDOR), "--porta"], capture_output=True, text=True, timeout=120, cwd=RAIZ, check=False
    )
    try:
        return int(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return 8765


def esta_saudavel(porta: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/health", timeout=5) as resposta:
            return bool(resposta.status == 200)
    except OSError:
        return False


def subir_o_servidor() -> subprocess.Popen[bytes]:
    PASTA_DE_LOGS.mkdir(parents=True, exist_ok=True)
    saida = (PASTA_DE_LOGS / "servico-servidor.log").open("ab")
    ambiente = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    return subprocess.Popen(  # lista de argumentos, nunca shell
        [str(PYTHON), str(SERVIDOR)],
        cwd=RAIZ,
        env=ambiente,
        stdout=saida,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def encerrar(filho: subprocess.Popen[bytes]) -> None:
    if filho.poll() is not None:
        return
    filho.terminate()
    try:
        filho.wait(15)
    except subprocess.TimeoutExpired:
        filho.kill()
        filho.wait()


def supervisionar(parar: Callable[[float], bool], avisar: Callable[[str], None]) -> None:
    """O laço do supervisor. `parar(segundos)` espera esse tempo e devolve True se o serviço foi mandado parar."""
    porta = porta_do_servidor()
    tentativa = 0
    while True:
        avisar(f"Subindo o servidor na porta {porta}")
        filho = subir_o_servidor()
        inicio = time.monotonic()
        falhas = 0
        proxima_saude = inicio + TOLERANCIA_DE_INICIO
        while True:
            if parar(2):
                encerrar(filho)
                return
            if filho.poll() is not None:
                motivo = f"o servidor terminou (código {filho.returncode})"
                break
            if time.monotonic() >= proxima_saude:
                proxima_saude = time.monotonic() + INTERVALO_DA_SAUDE
                falhas = 0 if esta_saudavel(porta) else falhas + 1
                if falhas >= FALHAS_SEGUIDAS:
                    motivo = "o servidor parou de responder"
                    break
        encerrar(filho)
        rodou = time.monotonic() - inicio
        tentativa = 0 if rodou >= ESTAVEL_DEPOIS_DE else min(tentativa + 1, len(ESPERAS))
        espera = ESPERAS[max(tentativa - 1, 0)]
        avisar(f"{motivo.capitalize()} depois de {rodou:.0f} s; subindo de novo em {espera} s")
        if parar(espera):
            return


if TEM_PYWIN32:

    class ServicoFabulim(win32serviceutil.ServiceFramework):  # type: ignore[misc]
        _svc_name_ = NOME
        _svc_display_name_ = NOME_NA_TELA
        _svc_description_ = DESCRICAO

        def __init__(self, args: list[str]) -> None:
            super().__init__(args)
            self._parar = win32event.CreateEvent(None, 0, 0, None)

        def SvcStop(self) -> None:
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, waitHint=30000)
            win32event.SetEvent(self._parar)

        def SvcDoRun(self) -> None:
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE, servicemanager.PYS_SERVICE_STARTED, (NOME, "")
            )

            def parar(segundos: float) -> bool:
                return bool(
                    win32event.WaitForSingleObject(self._parar, int(segundos * 1000)) == win32event.WAIT_OBJECT_0
                )

            try:
                supervisionar(parar, lambda texto: servicemanager.LogInfoMsg(f"{NOME}: {texto}"))
            except (
                Exception
            ) as exc:  # o Windows reinicia o serviço (recuperação); o motivo fica no Visualizador de Eventos
                servicemanager.LogErrorMsg(f"{NOME}: o supervisor caiu: {exc!r}")
                raise
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE, servicemanager.PYS_SERVICE_STOPPED, (NOME, "")
            )


def _sc(*argumentos: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["sc.exe", *argumentos], capture_output=True, text=True, errors="replace", check=False)


def _ambiente_do_servico() -> list[str]:
    """PATH e PYTHONPATH do serviço. Ele roda como sistema, que não enxerga o Python instalado só para o seu usuário nem o
    `.venv`: sem isto o `pythonservice.exe` não acha o `python312.dll` (erro 1053, «não respondeu em tempo hábil»)."""
    base = ""
    for linha in (RAIZ / ".venv" / "pyvenv.cfg").read_text(encoding="utf-8").splitlines():
        if linha.strip().lower().startswith("home"):
            base = linha.split("=", 1)[1].strip()
    pacotes = RAIZ / ".venv" / "Lib" / "site-packages"
    caminho = os.pathsep.join(
        [base, str(pacotes / "pywin32_system32"), str(pacotes / "win32"), os.environ.get("PATH", "")]
    )
    pythonpath = os.pathsep.join(str(pacotes / p) for p in ("", "win32", "win32\\lib", "Pythonwin"))
    return [f"PATH={caminho}", f"PYTHONPATH={pythonpath}", "PYTHONUTF8=1"]


def _gravar_ambiente() -> None:
    import winreg

    with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, rf"SYSTEM\CurrentControlSet\Services\{NOME}") as chave:
        winreg.SetValueEx(chave, "Environment", 0, winreg.REG_MULTI_SZ, _ambiente_do_servico())


def instalar() -> int:
    if not TEM_PYWIN32:
        print("Falta o pywin32: rode `.venv\\Scripts\\python -m pip install -r backend\\requirements-servico.txt`.")
        return 1
    win32serviceutil.HandleCommandLine(ServicoFabulim, argv=[sys.argv[0], "--startup", "auto", "install"])
    _gravar_ambiente()
    # se o supervisor cair, o Windows o sobe de novo (5 s depois, sem limite de vezes por dia)
    _sc("failure", NOME, "reset=", "86400", "actions=", "restart/5000/restart/5000/restart/5000")
    _sc("failureflag", NOME, "1")
    win32serviceutil.StartService(NOME)
    print(f"Serviço «{NOME_NA_TELA}» instalado e iniciado. Ele sobe com o Windows e reinicia o servidor se ele cair.")
    return 0


def remover() -> int:
    if not TEM_PYWIN32:
        return 1
    _sc("stop", NOME)
    time.sleep(3)
    win32serviceutil.HandleCommandLine(ServicoFabulim, argv=[sys.argv[0], "remove"])
    return 0


def main() -> int:
    comando = sys.argv[1] if len(sys.argv) > 1 else ""
    if comando == "instalar":
        return instalar()
    if comando == "remover":
        return remover()
    if comando in {"iniciar", "parar", "status"}:
        r = _sc({"iniciar": "start", "parar": "stop", "status": "query"}[comando], NOME)
        print(r.stdout or r.stderr)
        return r.returncode
    if comando == "" or not TEM_PYWIN32:
        print(__doc__)
        return 0
    win32serviceutil.HandleCommandLine(ServicoFabulim)  # debug, update e os demais comandos do pywin32
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
