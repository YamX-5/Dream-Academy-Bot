@echo off
chcp 65001 >nul
title Dream Academy Manager
cd /d "%~dp0"

echo.
echo  ====================================
echo    DA - Dream Academy Manager
echo  ====================================
echo.

rem -- download cloudflared once (for the public URL that works from the gym) --
if not exist cloudflared.exe (
    echo  [i] Downloading cloudflared for the public link, one time only...
    powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared.exe' } catch { Write-Host '  [!] Download failed - app will work on local network only.' }"
)

echo  [i] Starting the server... keep this window open.
echo      Laptop:  http://127.0.0.1:8000
echo      QR page: http://127.0.0.1:8000/qr
echo.

"%~dp0venv\Scripts\python.exe" app.py
pause
