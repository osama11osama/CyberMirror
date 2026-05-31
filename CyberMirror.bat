@echo off
title CyberMirror Launcher
cd /d "%~dp0"

where python >nul 2>&1
if %errorlevel% neq 0 (
  echo Python not found. Install Python 3.10+ from https://python.org
  pause
  exit /b 1
)

python "%~dp0launcher\cybermirror_launcher.py"
if errorlevel 1 pause
