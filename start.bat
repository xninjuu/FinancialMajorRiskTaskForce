@echo off
setlocal
set SCRIPT_DIR=%~dp0
cd /d %SCRIPT_DIR%
if exist "%SCRIPT_DIR%dist\FMR_TaskForce_GUI.exe" (
    echo Starting FMR_TaskForce_GUI.exe...
    "%SCRIPT_DIR%dist\FMR_TaskForce_GUI.exe"
) else (
    echo FMR_TaskForce_GUI.exe not found in %SCRIPT_DIR%dist
)
if errorlevel 1 (
    echo.
    echo The application exited with an error. Review the message above.
)
pause
