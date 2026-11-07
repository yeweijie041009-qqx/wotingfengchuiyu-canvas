@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   Push canvas updates to GitHub
echo ============================================
echo.

git push origin main
if not errorlevel 1 goto done

echo.
echo [i] First attempt failed. Trying without proxy ...
git -c http.proxy= -c https.proxy= push origin main
if not errorlevel 1 goto done

echo.
echo [i] Still failed. Trying through proxy 127.0.0.1:7890 ...
git -c http.proxy=http://127.0.0.1:7890 -c https.proxy=http://127.0.0.1:7890 push origin main
if not errorlevel 1 goto done

echo.
echo [X] Push failed.
echo     Common reasons:
echo       - GitHub login expired: sign in when the window pops up
echo       - VPN/proxy is off and github.com is blocked
echo     Send me this window's text if you need help.
pause
exit /b 1

:done
echo.
echo [OK] Pushed. Check: https://github.com/yeweijie041009-qqx/wotingfengchuiyu-canvas
pause