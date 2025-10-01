@echo off
setlocal
pushd "%~dp0"

REM Lance l'installateur PowerShell avec élévation
powershell -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb runAs -ArgumentList '-ExecutionPolicy Bypass -File ""%CD%\scripts\install_and_setup.ps1""'"

popd
endlocal