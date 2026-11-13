@echo off
setlocal
cd /d "%~dp0"
py -3 -m pip install --no-index --no-deps --find-links="dist" okto-toolkit
if errorlevel 1 (
  echo Install failed. Offline fallback: py -3 dist\okto.pyz --help
  exit /b 1
)
py -3 -m okto doctor
