@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "BUNDLED_NODE=C:\Users\tulli\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"

where node >nul 2>nul
if %errorlevel%==0 (
  set "NODE_EXE=node"
) else (
  set "NODE_EXE=%BUNDLED_NODE%"
)

if not exist "%NODE_EXE%" (
  echo Could not find Node.js.
  echo Install Node or update BUNDLED_NODE in run-chat.bat.
  exit /b 1
)

"%NODE_EXE%" "%SCRIPT_DIR%cloud-chat.js"
