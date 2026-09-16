@echo off
chcp 65001 >nul
cd /d "%~dp0"

set PY=
py -3.12 -c "print()" >nul 2>&1 && set PY=py -3.12
if "%PY%"=="" python -c "import sys;sys.exit(sys.version_info[:2]!=(3,12))" >nul 2>&1 && set PY=python
if "%PY%"=="" (
    echo Python 3.12 가 없다. README.md 1번을 보고 설치한 뒤 다시 실행.
    pause & exit /b 1
)

where ffmpeg >nul 2>&1 || (
    echo ffmpeg 가 없다. README.md 1번을 보고 설치한 뒤 새 창에서 다시 실행.
    pause & exit /b 1
)

if not exist .venv\Scripts\python.exe (
    echo [1/3] 가상환경 만드는 중...
    %PY% -m venv .venv || (pause & exit /b 1)
)
echo [2/3] 패키지 설치 중 (처음 한 번만 오래 걸린다)...
.venv\Scripts\python -m pip install -q -r requirements.txt || (pause & exit /b 1)

echo [3/3] 실행
.venv\Scripts\python run.py %*
echo.
pause
