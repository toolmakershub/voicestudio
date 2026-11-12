@echo off
cd /d "%~dp0"
set HF_HUB_OFFLINE=1
set HF_HOME=%~dp0models
title Indic engine
:loop
.venv-indic\Scripts\python -m uvicorn indic_worker.server:app --host 127.0.0.1 --port 7861
if %errorlevel%==3 (echo Applying update - restarting Indic engine... & goto loop)
pause
