@echo off
rem =====================================================================================================
rem  Fabulim Studio: sobe o app (backend + interface) e abre o navegador.
rem  Uso: iniciar.bat            uso normal (serve a interface ja compilada)
rem       iniciar.bat --compilar recompila a interface antes de subir (use depois de mudar o frontend)
rem       iniciar.bat --sem-navegador   nao abre o navegador
rem  Nada aqui instala coisas no sistema: usa o .venv e o node_modules do proprio projeto.
rem =====================================================================================================
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title Fabulim Studio

set "COMPILAR=0"
set "ABRIR=1"
:args
if "%~1"=="" goto args_fim
if /I "%~1"=="--compilar" set "COMPILAR=1"
if /I "%~1"=="--sem-navegador" set "ABRIR=0"
shift
goto args
:args_fim

set "PYEXE=.venv\Scripts\python.exe"
set "PYTHONIOENCODING=utf-8"

echo.
echo   Fabulim Studio
echo   ------------------------------------------------------------

rem --- 1. ambiente Python -------------------------------------------------------------------------------
if not exist "%PYEXE%" (
  echo   [ERRO] Nao encontrei o ambiente Python do projeto ^(.venv^).
  echo          Veja docs\SETUP.md, secao "Reinstalar do zero".
  goto falhou
)

rem --- 1b. configuracao valida e porta efetiva (vale a variavel de ambiente, depois o .env, depois 8765) ----------
"%PYEXE%" scripts\servidor.py --porta >"%TEMP%\fabulim-porta.txt" 2>"%TEMP%\fabulim-porta-erro.txt"
if errorlevel 1 (
  echo   [ERRO] Configuracao invalida:
  type "%TEMP%\fabulim-porta-erro.txt"
  echo          Corrija o arquivo .env ^(veja .env.example^) e rode de novo.
  goto falhou
)
set /p FABULIM_PORT=<"%TEMP%\fabulim-porta.txt"
set "URL=http://127.0.0.1:%FABULIM_PORT%"

rem --- 2. interface compilada ---------------------------------------------------------------------------
if not exist "frontend\dist\frontend\browser\index.html" set "COMPILAR=1"
if "%COMPILAR%"=="1" (
  where node >nul 2>&1 || ( echo   [ERRO] Node.js nao encontrado. Veja docs\SETUP.md. & goto falhou )
  if not exist "frontend\node_modules" (
    echo   Instalando as dependencias da interface ^(so na primeira vez^)...
    call npm --prefix frontend ci || goto falhou
  )
  echo   Compilando a interface...
  call npm --prefix frontend run build || goto falhou
)

rem --- 3. ja esta rodando? ------------------------------------------------------------------------------
"%PYEXE%" -c "import sys,urllib.request as u; sys.exit(0 if u.urlopen('%URL%/api/health', timeout=2).status==200 else 1)" >nul 2>&1
if not errorlevel 1 (
  echo   O Fabulim ja esta no ar em %URL%
  goto abrir
)

rem --- 4. sobe o servidor (so em 127.0.0.1) ---------------------------------------------------------------
echo   Subindo o servidor em %URL% ...
start "Fabulim Studio: servidor (feche esta janela para encerrar)" /min "%PYEXE%" scripts\servidor.py

rem --- 5. espera a saude do servidor ---------------------------------------------------------------------
set "TENTATIVAS=0"
:esperar
"%PYEXE%" -c "import sys,urllib.request as u; sys.exit(0 if u.urlopen('%URL%/api/health', timeout=2).status==200 else 1)" >nul 2>&1
if not errorlevel 1 goto no_ar
set /a TENTATIVAS+=1
if %TENTATIVAS% GEQ 40 (
  echo   [ERRO] O servidor nao respondeu em 40 segundos.
  echo          Veja a janela do servidor ^(minimizada^) ou os logs em data\logs\app.jsonl.
  goto falhou
)
rem espera ~1 s (o "timeout" do Windows falha quando a entrada esta redirecionada; o ping local funciona sempre)
ping -n 2 127.0.0.1 >nul
goto esperar

:no_ar
echo   Servidor no ar.
echo   Uma coleta leve do hardware roda ao iniciar: acompanhe em Fila e em Status.

:abrir
if "%ABRIR%"=="1" start "" "%URL%"
echo.
echo   Abra:   %URL%
echo   Status: %URL%/status/servicos
echo   Para encerrar, feche a janela "Fabulim Studio: servidor".
echo.
exit /b 0

:falhou
echo.
echo   Nao foi possivel iniciar. Corrija o item acima e rode iniciar.bat de novo.
pause
exit /b 1
