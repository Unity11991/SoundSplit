@echo off
setlocal
chcp 65001 >nul
title SoundSplit - AI Voice & Music Isolator

:: Ensure working directory is always the script directory
cd /d "%~dp0"

echo ==================================================================
echo             SoundSplit - AI Voice ^& Music Isolator
echo ==================================================================
echo.
echo Starting FastAPI Backend and Next.js Frontend...
echo Detecting your local Wi-Fi IP for Mobile access...
echo.

:: Detect Python executable (.venv or system)
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set "PYTHON_EXE=python"
    ) else (
        echo [ERROR] Python was not found in .venv or system PATH!
        echo Please ensure Python is installed.
        pause
        exit /b 1
    )
)

:: Run unified launcher
"%PYTHON_EXE%" "scripts\run_all.py"

if %ERRORLEVEL% neq 0 (
    echo.
    echo [SoundSplit stopped or encountered an error.]
)
pause
