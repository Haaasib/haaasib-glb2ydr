@echo off
title Haaasib 3D Converter Server

cd /d "%~dp0"

echo.
echo ================================================
echo   Setting up Python environment and dependencies
echo ================================================
echo.

echo Installing required Python packages...
python -m pip install -r requirements.txt

IF %ERRORLEVEL% NEQ 0 (
  echo.
  echo Failed to install Python dependencies.
  echo Make sure Python is installed and available in PATH.
  pause
  goto :eof
)

echo.
echo ======================================
echo   Starting FastAPI server (server.py)
echo ======================================
echo.

python server.py

echo.
echo Server stopped.
pause

