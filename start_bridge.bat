@echo off
title DeepSeek Web Agent Bridge
cd /d "%~dp0"

rem Use the Python launcher if present, otherwise whatever "python" is on PATH.
where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    set "PY=python"
)

%PY% bridge.py

if errorlevel 1 (
    echo.
    echo Bridge exited with an error. Python 3.10 or newer is required.
    pause
)
