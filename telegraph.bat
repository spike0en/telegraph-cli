@echo off
py "%~dp0telegraph.py" %*
if "%~1"=="" (
    echo.
    echo Press any key to exit...
    pause >nul
)
