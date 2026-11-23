@echo off
REM Updates Voice Studio to the latest RELEASE (not unfinished work on main),
REM then installs any new libraries and models. Needs internet.

REM git may replace this file while it runs, which confuses cmd.exe,
REM so the update runs from a temporary copy.
if not "%~1"=="--from-temp" (
  copy /y "%~f0" "%TEMP%\voicestudio_update.bat" >nul
  "%TEMP%\voicestudio_update.bat" --from-temp "%~dp0"
  exit /b
)
cd /d "%~2"

if not exist .git (
  echo This folder is not a git clone, so it cannot switch versions by itself.
  echo Download the latest release zip from GitHub instead.
  goto :deps
)
git fetch --tags --quiet origin || (echo Could not reach GitHub. & pause & exit /b 1)
set LATEST=
for /f %%t in ('git tag --list "v*" --sort=-v:refname') do if not defined LATEST set LATEST=%%t
echo Updating to %LATEST% ...
git checkout --quiet %LATEST% || (echo You have local changes. Commit or stash them, then run update.bat again. & pause & exit /b 1)

:deps
call .venv\Scripts\activate
REM Installs only what is missing; never replaces the GPU build of PyTorch.
pip install -r requirements.txt
python download_extras.py
echo.
if exist VERSION (for /f %%v in (VERSION) do echo Voice Studio is now on v%%v.)
echo Restart the studio with run.bat.
pause
