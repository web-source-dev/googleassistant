@echo off
cd /d "%~dp0"
echo Google Assistant: http://127.0.0.1:5173
echo The backend should already be running on http://127.0.0.1:8000
python -m http.server 5173
pause
