@echo off
rem =====================================================================================================
rem  Fabulim Studio: servico do Windows que mantem o servidor sempre no ar (sobe com o Windows e sobe de
rem  novo se cair). Rode como ADMINISTRADOR (botao direito, "Executar como administrador").
rem  Uso: servico.bat instalar | remover | iniciar | parar | status
rem =====================================================================================================
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" (
  echo   Uso: servico.bat instalar ^| remover ^| iniciar ^| parar ^| status
  exit /b 1
)
net session >nul 2>&1
if errorlevel 1 if /I not "%~1"=="status" (
  echo   [ERRO] Abra este arquivo como administrador: o Windows so deixa criar servicos assim.
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo   [ERRO] Nao encontrei o ambiente Python do projeto ^(.venv^). Veja docs\SETUP.md.
  exit /b 1
)
".venv\Scripts\python.exe" -c "import win32serviceutil" >nul 2>&1 || ".venv\Scripts\python.exe" -m pip install -r backend\requirements-servico.txt || exit /b 1
".venv\Scripts\python.exe" scripts\servico_windows.py %*
exit /b %errorlevel%
