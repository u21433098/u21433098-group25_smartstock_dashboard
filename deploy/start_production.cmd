@echo off
rem ---------------------------------------------------------------------------
rem  Start SmartStock in production mode on Windows (Waitress web server).
rem
rem  Double-click this file, or run it from the project folder:  deploy\start_production.cmd
rem  Other computers on the same network can then open http://THIS-PC-IP:8000
rem  (Windows asks once whether to allow Python through the firewall: allow "Private networks").
rem  Task Scheduler uses this file to start SmartStock automatically (README, Deployment).
rem
rem  A plain .cmd file is used on purpose: starting PowerShell with "-ExecutionPolicy Bypass"
rem  is flagged as harmful by antivirus software, and needs no policy changes.
rem ---------------------------------------------------------------------------
cd /d "%~dp0.."
if not exist "venv\Scripts\waitress-serve.exe" goto no_waitress
if not exist ".env" goto no_env
echo Starting SmartStock on http://0.0.0.0:8000 - logs in %CD%\logs - stop with Ctrl+C
"venv\Scripts\waitress-serve.exe" --listen=0.0.0.0:8000 wsgi:app
exit /b %ERRORLEVEL%

:no_waitress
echo Waitress was not found. Inside the project folder run: pip install -r requirements.txt
exit /b 1

:no_env
echo There is no .env file in %CD%. Copy .env.example to .env and fill it in first.
exit /b 1
