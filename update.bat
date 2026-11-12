@echo off
cd /d "%~dp0"
REM Installs new libraries and downloads new models after an update. Needs internet.
call .venv\Scripts\activate
pip install indic-numtowords
python download_extras.py
echo.
echo Update finished. Restart the studio with run.bat.
pause
