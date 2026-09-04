@echo off
setlocal EnableExtensions
set "APP=%ProgramFiles%\Google Assistant\GoogleAssistant.exe"
set "PKG=%ProgramData%\GoogleAssistant\pending.exe"
if not exist "%PKG%" set "PKG=%LOCALAPPDATA%\Google Assistant\updates\GoogleAssistant.exe"
if not exist "%PKG%" exit /b 1

taskkill /F /IM GoogleAssistant.exe /T >nul 2>&1

set /a _n=0
:wait_exit
tasklist /FI "IMAGENAME eq GoogleAssistant.exe" | find /I "GoogleAssistant.exe" >nul
if errorlevel 1 goto do_install
set /a _n+=1
if %_n% GEQ 20 goto do_install
timeout /t 1 /nobreak >nul
goto wait_exit

:do_install
timeout /t 1 /nobreak >nul
"%PKG%" /VERYSILENT /NORESTART /SUPPRESSMSGBOXES /SP- /CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS
set "ERR=%ERRORLEVEL%"

timeout /t 2 /nobreak >nul
if exist "%APP%" start "" "%APP%"
exit /b %ERR%
