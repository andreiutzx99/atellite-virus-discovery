@echo off
cd /d "%~dp0"
python -u -m satellite_discovery.audit_wizard
set "audit_exit=%errorlevel%"
if not "%audit_exit%"=="0" echo The audit did not pass. Copy the error shown above if you need help.
pause
exit /b %audit_exit%
