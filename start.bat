@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
where py >nul 2>nul
if errorlevel 1 (python launcher.py start) else (py -3 launcher.py start)
if errorlevel 1 pause
