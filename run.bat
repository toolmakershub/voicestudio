@echo off
cd /d "%~dp0"
set HF_HUB_OFFLINE=1
REM Start the Indian-language engine (separate Python 3.10 env) if it is installed
if exist .venv-indic\Scripts\python.exe start "Indic engine" /min cmd /c run_indic.bat
call .venv\Scripts\activate
start "" http://127.0.0.1:7860
:loop
python -m uvicorn app:app --host 127.0.0.1 --port 7860
if %errorlevel%==3 (echo Applying update - restarting studio... & goto loop)
pause
