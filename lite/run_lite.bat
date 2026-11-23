@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First-time setup: creating environment and installing Piper...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || (echo Setup failed. & pause & exit /b 1)
)
start "" ".venv\Scripts\pythonw.exe" app.py
