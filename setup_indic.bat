@echo off
cd /d "%~dp0"
REM One-time setup of the Indian-language engine (IndicF5). Needs internet.
set HF_HOME=%~dp0models
py -3.10 -m venv .venv-indic || (echo Python 3.10 not found. Install it from python.org first. & pause & exit /b 1)
call .venv-indic\Scripts\activate
python -m pip install --upgrade pip
pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
pip install "https://github.com/AI4Bharat/IndicF5/archive/refs/heads/main.zip" "transformers<4.50" "numpy<=1.26.4" fastapi uvicorn soundfile
python -m indic_worker.download
echo.
echo Indian-language engine setup finished. Restart the studio with run.bat.
pause
