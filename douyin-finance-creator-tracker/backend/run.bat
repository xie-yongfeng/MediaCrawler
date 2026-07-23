@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

rem Start Fund Insight Desk backend (FastAPI + Uvicorn) - Windows script

rem Switch to the script directory so paths resolve correctly regardless of caller cwd
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "VENV_DIR=%SCRIPT_DIR%.venv"
for %%I in ("%SCRIPT_DIR%..\..") do set "MEDIA_CRAWLER_ROOT=%%~fI"
if not defined CDP_USER_DATA_DIR set "CDP_USER_DATA_DIR=%MEDIA_CRAWLER_ROOT%\browser_data\cdp_dy_user_data_dir"

if not defined HOST set "HOST=0.0.0.0"
if not defined PORT set "PORT=8000"
if not defined RELOAD set "RELOAD=true"

rem Create the virtual environment if it does not exist yet
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [run.bat] Virtual environment not found, creating %VENV_DIR% ...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [run.bat] Failed to create virtual environment. Make sure Python is installed and on PATH.
        exit /b 1
    )
)

rem Activate the virtual environment
call "%VENV_DIR%\Scripts\activate.bat"

rem Install/update dependencies
echo [run.bat] Installing dependencies...
python -m pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

call :ensure_cdp_chrome
if errorlevel 1 exit /b 1

rem Start the service (auto-reload is enabled by default; set RELOAD=false to disable)
set "RELOAD_FLAG=--reload"
if /i "%RELOAD%"=="false" set "RELOAD_FLAG="

echo [run.bat] Starting backend service at http://%HOST%:%PORT%
uvicorn app:app --host %HOST% --port %PORT% %RELOAD_FLAG%

endlocal
exit /b

:ensure_cdp_chrome
rem Keep a dedicated Chrome instance available for all crawler subprocesses.
netstat -ano | findstr /r /c:":9222 .*LISTENING" >nul
if not errorlevel 1 exit /b 0

if defined CHROME_PATH goto chrome_path_ready
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME_PATH=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if defined CHROME_PATH goto chrome_path_ready
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME_PATH=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if defined CHROME_PATH goto chrome_path_ready
echo [run.bat] Chrome was not found. Set CHROME_PATH to chrome.exe before starting the service.
exit /b 1

:chrome_path_ready
echo [run.bat] Starting persistent CDP Chrome on port 9222...
start "Fund Insight CDP Chrome" /b "%CHROME_PATH%" --remote-debugging-port=9222 --user-data-dir="%CDP_USER_DATA_DIR%"
set /a CDP_WAIT_SECONDS=0

:wait_for_cdp_chrome
netstat -ano | findstr /r /c:":9222 .*LISTENING" >nul
if not errorlevel 1 exit /b 0
set /a CDP_WAIT_SECONDS+=1
if %CDP_WAIT_SECONDS% GEQ 30 goto cdp_chrome_timeout
echo [run.bat] Waiting for CDP Chrome on port 9222 (%CDP_WAIT_SECONDS%/30)...
timeout /t 1 /nobreak >nul
goto wait_for_cdp_chrome

:cdp_chrome_timeout
echo [run.bat] CDP Chrome did not become ready on port 9222. Check that no other Chrome process is using "%CDP_USER_DATA_DIR%".
exit /b 1
