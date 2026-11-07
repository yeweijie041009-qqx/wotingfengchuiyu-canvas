@echo off
setlocal
cd /d "%~dp0"

REM PyInstaller does not support Python 3.14 yet, so prefer 3.12 / 3.11 / 3.10
set "PY="
for %%V in (3.12 3.11 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY (
  py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
)
if not defined PY (
  python -c "import sys" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [X] Python not found. Install Python 3.12 from https://www.python.org/downloads/
  pause
  exit /b 1
)

echo Using: %PY%
%PY% -c "import sys; v=sys.version_info; print('Python', v.major, v.minor); sys.exit(0 if v.minor<=13 else 3)"
if errorlevel 3 (
  echo [X] Python 3.14+ is not supported by PyInstaller.
  echo     Install Python 3.12 and run this again.
  pause
  exit /b 2
)

echo [1/3] Installing PyInstaller ...
%PY% -m pip install -q pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
%PY% -c "import PyInstaller" 2>nul
if errorlevel 1 (
  echo [X] PyInstaller install failed. See the pip output above.
  pause
  exit /b 3
)

echo [2/3] Building exe ...
%PY% tools\build_exe.py
if errorlevel 1 (
  echo [X] Build failed.
  pause
  exit /b 4
)

echo [3/3] Done.
echo.
echo Output: %~dp0..\dist\wotingfengchuiyu.exe
echo NOTE: the exe is only a launcher; ComfyUI + models still required.
pause