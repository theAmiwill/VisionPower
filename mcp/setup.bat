@echo off
REM MiMo Vision MCP Server ? Setup Script
REM Requires: Python 3.10+, uv (https://docs.astral.sh/uv/)

echo === MiMo Vision MCP Server Setup ===

REM Check uv
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] uv not found. Install it first: https://docs.astral.sh/uv/
    echo   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    exit /b 1
)

REM Create venv and install deps
echo Creating virtual environment...
if exist ".venv\Scripts\python.exe" (
    echo Reusing existing .venv
) else (
    uv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create venv
        exit /b 1
    )
)

echo Installing dependencies...
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies
    exit /b 1
)

echo.
echo === Setup complete ===
echo.
set "SCRIPT_DIR=%CD:\=/%"
echo Next steps:
echo   1. Copy .env.example to .env and fill in your API key
echo   2. Add the following to your ~/.mcp.json:
echo.
echo   {
echo     "mcpServers": {
echo       "mimo-vision": {
echo         "command": "%SCRIPT_DIR%/.venv/Scripts/python.exe",
echo         "args": ["%SCRIPT_DIR%/server.py"],
echo         "env": {
echo           "MIMO_VISION_API_KEY": "YOUR_KEY_HERE",
echo           "MIMO_VISION_MODEL": "mimo-v2.5-pro",
echo           "MIMO_VISION_API_BASE_URL": "https://api.xiaomimimo.com/v1"
echo         }
echo       }
echo     }
echo   }
echo.
echo   3. Restart Claude Code
echo.
pause
