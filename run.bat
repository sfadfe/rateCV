@echo off
chcp 65001 >nul
cd /d "%~dp0"

set PY=
py -3.12 -c "print()" >nul 2>&1 && set PY=py -3.12
if "%PY%"=="" python -c "import sys;sys.exit(sys.version_info[:2]!=(3,12))" >nul 2>&1 && set PY=python
if "%PY%"=="" (
    echo Python 3.12 not found. See README.md step 1, install it, and run again.
    pause & exit /b 1
)

where ffmpeg >nul 2>&1 || (
    echo ffmpeg not found. See README.md step 1, install it, and run again in a new window.
    pause & exit /b 1
)

if not exist .venv\Scripts\python.exe (
    echo [1/3] creating venv...
    %PY% -m venv .venv || (pause & exit /b 1)
)
echo [2/3] installing packages (slow only the first time)...
.venv\Scripts\python -m pip install -q -r requirements.txt || (pause & exit /b 1)

echo [3/3] running
.venv\Scripts\python run.py %*
echo.
pause
