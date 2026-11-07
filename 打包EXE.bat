@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
echo [1/3] Installing PyInstaller ...
%PY% -m pip install -q pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
echo [2/3] Building exe (1-2 min) ...
%PY% tools\build_exe.py
echo [3/3] Done.
echo.
echo Output: %~dp0..\dist\wotingfengchuiyu.exe
echo NOTE: the exe is only a launcher; ComfyUI + models still required.
pause