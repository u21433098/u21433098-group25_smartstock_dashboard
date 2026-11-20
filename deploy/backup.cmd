@echo off
rem ---------------------------------------------------------------------------
rem  Back up the SmartStock database (Windows). Same as running "flask backup".
rem
rem  Task Scheduler runs this file every night (README, Deployment). It saves
rem  backups\smartstock_YYYY-MM-DD_HHMMSS.sql.gz and deletes backups older than 30 days.
rem  The output is added to logs\backup.log, so a failed night can be found later.
rem ---------------------------------------------------------------------------
cd /d "%~dp0.."
if not exist logs mkdir logs
echo ---- %DATE% %TIME% >> logs\backup.log
"venv\Scripts\flask.exe" backup >> logs\backup.log 2>&1
exit /b %ERRORLEVEL%
