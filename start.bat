@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")

if not exist config.json (
  if exist config.example.json copy config.example.json config.json >nul
  echo [i] 已生成 config.json，请按需修改 comfy_root / data_dir
)

%PY% start.py %*
if errorlevel 1 pause
