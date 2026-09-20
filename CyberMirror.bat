@echo off
title CyberMirror
cd /d "%~dp0"

REM One-click launcher: backend + frontend + opens browser
chcp 65001 >nul 2>&1
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

where python >nul 2>&1
if %errorlevel% neq 0 (
  echo.
  echo  Python 3.10+ is required.
  echo  Download: https://python.org
  echo.
  pause
  exit /b 1
)

echo.
echo  ========================================
echo   CyberMirror - starting...
echo   Keep this window OPEN while using the app
echo  ========================================
echo.

python -X utf8 "%~dp0launcher\cybermirror_launcher.py" --prod
if errorlevel 1 (
  echo.
  echo  CyberMirror stopped with an error.
  pause
)
