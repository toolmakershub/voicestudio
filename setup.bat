@echo off
cd /d "%~dp0"
REM One-time setup (needs internet). Usage:  setup.bat        (CPU)
REM                                         setup.bat gpu    (NVIDIA GPU)
py -3.11 -m venv .venv || (echo Python 3.11 not found. Install it from python.org first. & exit /b 1)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if /I "%1"=="gpu" (
  echo Installing CUDA build of PyTorch...
  pip install --force-reinstall torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
)
python download_model.py
echo.
echo Setup complete. Run run.bat to start the studio.
pause
