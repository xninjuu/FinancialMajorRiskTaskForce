@echo off
setlocal
echo Launching FMR TaskForce GUI...
set SCRIPT_DIR=%~dp0
cd /d %SCRIPT_DIR%
if exist "%SCRIPT_DIR%dist\FMR_TaskForce_GUI.exe" (
    "%SCRIPT_DIR%dist\FMR_TaskForce_GUI.exe"
) else (
    echo dist\FMR_TaskForce_GUI.exe not found. Run PyInstaller build first.
)
if errorlevel 1 (
    echo.
    echo Application exited with an error. Review any messages above.
)
pause
