@echo off
title CyberMirror (Production Mode)
cd /d "%~dp0"
python "%~dp0launcher\cybermirror_launcher.py" --prod
if errorlevel 1 pause
