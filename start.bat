@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m o2j %*
) else (
    python -m o2j %*
)
exit /b %errorlevel%
