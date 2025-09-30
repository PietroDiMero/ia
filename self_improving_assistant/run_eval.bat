@echo off
setlocal
REM Switch to project directory (folder of this .bat)
pushd "%~dp0"

REM Create venv if missing
if not exist .venv (
	py -3 -m venv .venv
)
call .venv\Scripts\activate.bat

REM Install deps if needed (no-op if already installed)
python -m pip install -q --disable-pip-version-check -r requirements.txt

REM Run evaluation
python scripts\evaluate.py >> logs\cron.log 2>&1

popd
endlocal
