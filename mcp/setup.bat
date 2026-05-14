@echo off
REM VisionPower MCP Server Setup Script
REM Requires: Python 3.10+, uv (https://docs.astral.sh/uv/)

echo === VisionPower MCP Server Setup ===

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
echo   1. From the repository root, run: python install.py
echo   2. Or add the following to your MCP client config:
echo.
echo   {
echo     "mcpServers": {
echo       "vision-power": {
echo         "type": "stdio",
echo         "command": "%SCRIPT_DIR%/.venv/Scripts/python.exe",
echo         "args": ["%SCRIPT_DIR%/server.py"],
echo         "env": {
echo           "VISION_POWER_API_KEY": "YOUR_KEY_HERE",
echo           "VISION_POWER_MODEL": "mimo-v2.5",
echo           "VISION_POWER_API_BASE_URL": "https://token-plan-cn.xiaomimimo.com/v1",
echo           "VISION_POWER_API_PROTOCOL": "openai",
echo           "VISION_POWER_TIMEOUT": "120"
echo         }
echo       }
echo     }
echo   }
echo.
echo   3. Restart your MCP client
echo.
pause
