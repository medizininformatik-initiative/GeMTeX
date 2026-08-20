@echo off
setlocal enabledelayedexpansion

REM py-anonymizer-semann-gemtex launcher for Windows

if not exist "%~dp0main.py" (
    echo Error: main.py not found in %~dp0
    exit /b 1
)

REM Try python3 first, then python
python --version >nul 2>&1
if errorlevel 1 (
    python3 --version >nul 2>&1
    if errorlevel 1 (
        echo Error: Python not found. Please install Python 3.7+ and add it to PATH.
        exit /b 1
    )
    set PYTHON=python3
) else (
    set PYTHON=python
)

echo.
%PYTHON% "%~dp0main.py" %*
pause
