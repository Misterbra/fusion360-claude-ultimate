@echo off
title Fusion 360 MCP Server
color 0A

echo.
echo  ========================================
echo   FUSION 360 MCP SERVER - Quick Start
echo  ========================================
echo.

:: Check Node.js
where node >nul 2>nul
if %errorlevel% neq 0 (
    color 0C
    echo  [X] Node.js not found. Install it from https://nodejs.org
    echo.
    pause
    exit /b 1
)

:: Check dependencies
if not exist "%~dp0server\node_modules" (
    echo  [!] Installing dependencies...
    cd /d "%~dp0server"
    npm install --silent
    echo  [OK] Dependencies installed.
    echo.
)

echo  [1] START SERVER    - Launch the MCP server
echo  [2] SETUP GUIDE     - First-time setup instructions
echo  [3] QUIT
echo.
set /p choice="  Your choice (1/2/3): "

if "%choice%"=="1" goto :start_server
if "%choice%"=="2" goto :guide
if "%choice%"=="3" exit /b 0
goto :start_server

:guide
cls
echo.
echo  ========================================
echo   SETUP GUIDE
echo  ========================================
echo.
echo  STEP 1 - Fusion 360 Add-in
echo  ---------------------------
echo  Copy the folder:
echo    %~dp0fusion_script\fusion_mcp_server\
echo  To:
echo    %%APPDATA%%\Autodesk\Autodesk Fusion 360\API\AddIns\
echo.
echo  Then in Fusion 360: Tools ^> Add-Ins ^> Enable "Fusion MCP Server"
echo  Click START in the MCP panel.
echo.
echo  ---------------------------
echo  STEP 2 - Claude Desktop
echo  ---------------------------
echo  Edit: %%APPDATA%%\Claude\claude_desktop_config.json
echo  Paste this (replace the path):
echo.
echo  {
echo    "mcpServers": {
echo      "fusion_mcp": {
echo        "command": "node",
echo        "args": ["%~dp0server\server.mjs"],
echo        "protocol": "stdio"
echo      }
echo    }
echo  }
echo.
echo  Then restart Claude Desktop.
echo.
echo  ---------------------------
echo  STEP 3 - Start working
echo  ---------------------------
echo  1. Open Fusion 360 + start the add-in
echo  2. Run this script and press [1] to start the server
echo  3. Open Claude Desktop and start talking!
echo.
echo  Example prompts:
echo    "Create a box 100x60x40mm"
echo    "Shell it with 2mm walls, remove the top face"
echo    "Add 3mm fillets to all edges"
echo    "Export as STL to my Desktop"
echo.
pause
cls
goto :guide_end

:guide_end
echo.
echo  ========================================
echo   FUSION 360 MCP SERVER - Quick Start
echo  ========================================
echo.
echo  [1] START SERVER    - Launch the MCP server
echo  [2] SETUP GUIDE     - First-time setup instructions
echo  [3] QUIT
echo.
set /p choice="  Your choice (1/2/3): "
if "%choice%"=="1" goto :start_server
if "%choice%"=="2" goto :guide
if "%choice%"=="3" exit /b 0
goto :start_server

:start_server
cls
echo.
echo  ========================================
echo   STARTING MCP SERVER...
echo  ========================================
echo.
echo  [i] Server directory: %~dp0server\
echo  [i] Press Ctrl+C to stop the server
echo.
echo  CHECKLIST before you start:
echo    [?] Fusion 360 is open
echo    [?] Add-in is running (click START in MCP panel)
echo    [?] Claude Desktop is open
echo.
echo  Starting in 2 seconds...
timeout /t 2 /nobreak >nul
echo.
echo  ----------------------------------------
cd /d "%~dp0server"
node server.mjs
echo.
echo  ----------------------------------------
echo  Server stopped.
pause
