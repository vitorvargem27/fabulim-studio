@echo off
rem Fabulim Studio: roda lint, tipos, testes e cobertura com um comando. Use "testar.bat --hw" para incluir o hardware real.
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYEXE=python"
where py >nul 2>&1 && (py -3.12 -c "import sys" >nul 2>&1 && set "PYEXE=py -3.12")
if exist ".venv\Scripts\python.exe" set "PYEXE=.venv\Scripts\python.exe"
%PYEXE% scripts\testar.py %*
exit /b %errorlevel%
