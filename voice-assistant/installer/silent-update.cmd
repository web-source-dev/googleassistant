@echo off
setlocal EnableExtensions
set "APP=%ProgramFiles%\Piano\Piano.exe"
set "PKG=%ProgramData%\Piano\pending.exe"
if not exist "%PKG%" set "PKG=%LOCALAPPDATA%\Piano\updates\Piano.exe"
if not exist "%PKG%" exit /b 1

taskkill /F /IM Piano.exe /T >nul 2>&1

set /a _n=0
:wait_exit
tasklist /FI "IMAGENAME eq Piano.exe" | find /I "Piano.exe" >nul
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
