@echo off
chcp 65001 >nul
title MOPEDETU - Tablero de descentralizacion turistica
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 iniciar.py
) else (
  python iniciar.py
)
if errorlevel 1 (
  echo.
  echo No se pudo iniciar. Verifica que Python 3.10+ este instalado: https://www.python.org/downloads/
  pause
)
