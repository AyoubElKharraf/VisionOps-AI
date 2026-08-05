@echo off
REM Wrapper so capture works from cmd.exe as well as PowerShell.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0capture-live-grid.ps1" %*
