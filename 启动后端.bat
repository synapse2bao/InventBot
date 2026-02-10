@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo Restart InventBot Backend Service
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found, please install Python first
    pause
    exit /b 1
)

REM Stop existing Python processes
echo [1/3] Stopping existing backend service...
taskkill /F /IM python.exe >nul 2>&1
timeout /t 2 /nobreak >nul

REM Check if port 5000 is in use
echo [2/3] Checking port 5000...
netstat -ano | findstr :5000 >nul 2>&1
if %errorlevel% equ 0 (
    echo Warning: Port 5000 may still be in use, trying to release...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
        taskkill /F /PID %%a >nul 2>&1
    )
    timeout /t 2 /nobreak >nul
)

REM Change to project directory
cd /d "%~dp0"

REM Check DeepSeek API KEY
echo [3/5] Checking DeepSeek API KEY...
python -c "from dotenv import load_dotenv; import os; load_dotenv(); key = os.getenv('DEEPSEEK_API_KEY'); exit(0 if key and key.strip() else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo DeepSeek API KEY not configured, starting setup...
    echo.
    
    REM Start update server in background
    echo [4/5] Starting update server...
    start "DeepSeek API KEY Update Server" /min python update_env_server.py
    
    REM Wait for server to start
    timeout /t 3 /nobreak >nul
    
    REM Open setup page in browser (local HTML file)
    start "" "%~dp0setup_deepseek_key.html"
    
    echo Setup page opened in browser.
    echo Please complete the configuration:
    echo 1. Enter your DeepSeek API KEY
    echo 2. Verify and save
    echo 3. Click "Update .env file" button to automatically update
    echo.
    echo Press any key after you have completed the configuration...
    pause >nul
    
    REM Stop update server
    taskkill /F /FI "WINDOWTITLE eq *DeepSeek API KEY Update Server*" >nul 2>&1
    timeout /t 1 /nobreak >nul
) else (
    echo DeepSeek API KEY found.
)

echo [5/5] Starting backend service...
echo.
echo ========================================
echo Backend service is starting...
echo Press Ctrl+C to stop the service
echo ========================================
echo.

REM Start backend service
python app.py

REM If service exits unexpectedly, show error message
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Backend service failed to start
    echo Please check:
    echo 1. Python environment is correct
    echo 2. Dependencies are installed (run: pip install -r requirements.txt)
    echo 3. Port 5000 is not occupied by other programs
    echo.
    pause
)
