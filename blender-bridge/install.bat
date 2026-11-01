@echo off
REM Blender Bridge (opcional): ambiente do servidor MCP, o .zip do addon e a
REM configuracao pronta para colar no cliente MCP (Claude, LM Studio, VS Code...).
setlocal
cd /d "%~dp0"
title EasyComfee Blender Bridge setup

set PY=
for %%v in (3.13 3.12 3.11) do if not defined PY (py -%%v --version >nul 2>nul && set PY=py -%%v)
if not defined PY (python -c "import sys; sys.exit(not (3,11) <= sys.version_info[:2] <= (3,13))" >nul 2>nul && set PY=python)
if not defined PY (echo Python 3.11, 3.12 or 3.13 is required: https://www.python.org/downloads/ & goto falhou)
where ffmpeg >nul 2>nul || echo Note: ffmpeg is not on PATH. The Bridge needs it to build videos: winget install ffmpeg

if not exist server\.venv (
  echo Creating the Python environment...
  %PY% -m venv server\.venv || goto falhou
)
server\.venv\Scripts\python.exe -m pip install -q --upgrade pip
server\.venv\Scripts\python.exe -m pip install -q -r server\requirements.txt || goto falhou

echo Packing the Blender add-on...
powershell -NoProfile -Command "Compress-Archive -Force -Path addon\blender_bridge -DestinationPath blender_bridge_addon.zip" || goto falhou

server\.venv\Scripts\python.exe server\escrever_config.py || goto falhou
echo.
echo Done. Next:
echo  1. Blender: Edit ^> Preferences ^> Add-ons ^> Install from Disk ^> blender_bridge_addon.zip,
echo     and turn it on. It starts by itself whenever Blender opens (3D Viewport ^> N ^> Bridge).
echo  2. Your MCP client: if you did not add it automatically above, paste the "blender-bridge"
echo     entry from mcp-config.json into it. Restart the client.
echo  3. Keep EasyComfee open, and ask for a shot.
pause
exit /b 0

:falhou
echo.
echo Setup did not finish. Read the message above, fix it, and run install.bat again.
pause
exit /b 1
