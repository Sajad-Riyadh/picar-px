@echo off
REM PiCar-X Windows setup launcher
REM Runs the PowerShell setup script (self-elevates to Administrator).
echo Launching PiCar-X Windows setup...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows-setup.ps1"
