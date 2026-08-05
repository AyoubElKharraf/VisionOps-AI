@echo off
REM Wrapper so the demo works from cmd.exe as well as PowerShell.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0demo-multicam.ps1" %*
