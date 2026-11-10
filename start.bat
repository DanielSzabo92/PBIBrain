@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo               Starting Power BI Brain
echo ========================================================

:: 1. Detect Python 3.11+
set "PYTHON_CMD="
for %%P in (python py python3) do (
    where %%P >nul 2>nul
    if !errorlevel! equ 0 (
        %%P -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
        if !errorlevel! equ 0 (
            set "PYTHON_CMD=%%P"
            goto :found_python
        )
    )
)

:found_python
if "%PYTHON_CMD%"=="" (
    echo [ERROR] Python 3.11 or newer was not found.
    echo Please install Python 3.11+ from https://www.python.org/
    echo and ensure it is added to your PATH.
    pause
    exit /b 1
)

:: 2. Set up virtual environment
if not exist ".venv\Scripts\activate.bat" (
    echo [*] Creating virtual environment in .venv...
    %PYTHON_CMD% -m venv .venv
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat

:: 3. Install backend dependencies if not installed
python -c "import antlr4, jsonschema; from backend.cli.main import _parser" >nul 2>nul
if !errorlevel! neq 0 (
    echo [*] Installing Power BI Brain backend dependencies...
    python -m pip install --disable-pip-version-check -e ".[mcp]"
    if !errorlevel! neq 0 (
        echo [*] Retrying with core dependencies...
        python -m pip install --disable-pip-version-check -e .
        if !errorlevel! neq 0 (
            echo [ERROR] Failed to install backend dependencies.
            pause
            exit /b 1
        )
    )
)

:: 4. Check / build frontend
if not exist "frontend\dist\index.html" (
    echo [*] Web UI build not found. Checking Node.js...
    where npm >nul 2>nul
    if !errorlevel! equ 0 (
        echo [*] Installing frontend packages and building UI...
        pushd frontend
        call npm install
        call npm run build
        popd
    ) else (
        echo [WARNING] Node.js not found. Starting server without built UI.
        echo           To use the UI, install Node.js 20+ and run:
        echo           cd frontend ^&^& npm install ^&^& npm run build
    )
)

:: 5. Open browser and launch server
echo [*] Launching browser and starting server on http://127.0.0.1:8000 ...
start "" http://127.0.0.1:8000
python -m backend.cli.main serve %*

pause
