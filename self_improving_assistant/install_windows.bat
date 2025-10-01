@echo off
setlocal
pushd "%~dp0"

REM Lance l'installateur PowerShell avec élévation et ATTEND la fin
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "\
	$p = Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoLogo -NoProfile -ExecutionPolicy Bypass -File ""%~dp0scripts\install_and_setup.ps1""' -Verb RunAs -PassThru -Wait; \
	if ($p -and $p.HasExited) { exit $p.ExitCode } else { exit 1 }"

set ERR=%ERRORLEVEL%
if %ERR% NEQ 0 (
	echo L'installation a rencontre une erreur. Code: %ERR%
) else (
	echo Installation terminee.
)
echo.
pause

popd
endlocal