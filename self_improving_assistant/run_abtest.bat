@echo off
setlocal
pushd "%~dp0"
if not exist .venv (
	py -3 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install -q --disable-pip-version-check -r requirements.txt
python scripts\ab_test.py >> logs\cron.log 2>&1
popd
endlocal
