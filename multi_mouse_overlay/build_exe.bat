@echo off
setlocal
cd /d "%~dp0"
python -m pip install pyinstaller
pyinstaller --noconsole --onefile --name MultiMouseOverlay app.py
