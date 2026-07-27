@echo off
REM Start Cognitive Offload on Windows.
cd /d "%~dp0"
python main.py
if errorlevel 1 pause
