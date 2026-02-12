@echo off
title Yuki Bot Launcher - Windows (English)
color 0B

cls
echo.
echo ============================================================
echo                   Yuki Bot - Interactive AI
echo ============================================================
echo.
echo                      [!] IMPORTANT NOTICE [!]
echo.
echo ------------------------------------------------------------
echo  This project is completely FREE and open source
echo  For learning and communication purposes ONLY
echo ------------------------------------------------------------
echo.
echo  [X] Commercial use is STRICTLY PROHIBITED
echo  [X] Reselling or paid services are FRAUD
echo  [X] Any illegal activities are FORBIDDEN
echo.
echo  [!] FRAUD WARNING:
echo     - Anyone claiming this project requires payment is a SCAMMER
echo     - Any paid services using this project name are FRAUD
echo     - Report immediately if you encounter fraud
echo.
echo  [i] Copyright Notice:
echo     - Character rights belong to original creators
echo     - This is a fan-made project, not official
echo.
echo  [i] Disclaimer:
echo     - Users bear all consequences of using this project
echo     - Authors are not liable for any damages
echo     - Please comply with laws and platform terms
echo.
echo ------------------------------------------------------------
echo.
set /p agree="  Type 'yes' to agree and continue: "

if /i not "%agree%"=="yes" (
    echo.
    echo  [X] You did not agree. Exiting...
    echo.
    pause
    exit /b 1
)

cls
echo.
echo ============================================================
echo                   Starting Yuki Bot...
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [X] ERROR: Python not found
    echo.
    echo Please install Python 3.9 or higher
    echo Download: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo [OK] Python environment check passed
echo.

if not exist ".env" (
    echo [!] WARNING: .env file not found
    echo.
    if exist ".env.example" (
        echo Creating .env from .env.example...
        copy ".env.example" ".env" >nul
        echo [OK] .env file created
        echo.
        echo [!] Please edit .env file before starting
        echo.
        pause
        exit /b 1
    ) else (
        echo [X] ERROR: .env.example not found
        echo.
        pause
        exit /b 1
    )
)

echo [OK] Configuration file check passed
echo.

echo Checking dependencies...
python -c "import nonebot" >nul 2>&1
if errorlevel 1 (
    echo [!] WARNING: Dependencies not installed
    echo.
    set /p install="Install dependencies now? (yes/no): "
    if /i "!install!"=="yes" (
        echo.
        echo Installing dependencies, please wait...
        pip install -r requirements.txt
        if errorlevel 1 (
            echo.
            echo [X] Dependency installation failed
            echo.
            pause
            exit /b 1
        )
        echo.
        echo [OK] Dependencies installed
    ) else (
        echo.
        echo [X] Dependencies not installed, cannot start
        echo.
        echo Please run: pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)

echo [OK] Dependency check passed
echo.
echo ------------------------------------------------------------
echo.
echo [*] Starting...
echo.
echo Tips:
echo   - Press Ctrl+C to stop the bot
echo   - Logs are saved in logs/ directory
echo   - Web admin: http://localhost:8080/admin
echo.
echo ------------------------------------------------------------
echo.

python bot.py

if errorlevel 1 (
    echo.
    echo ============================================================
    echo                      [X] Program exited abnormally
    echo ============================================================
    echo.
    echo Possible causes:
    echo   1. Configuration file error
    echo   2. Port already in use
    echo   3. Invalid API key
    echo   4. Dependency version conflict
    echo.
    echo Check logs above or in logs/ directory for details
    echo.
)

pause