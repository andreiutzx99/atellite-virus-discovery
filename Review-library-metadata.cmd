@echo off
cd /d "%~dp0"
python -m satellite_discovery.library_review --wizard
if errorlevel 1 goto failed
echo Review complete. Open the report path printed above.
pause
exit /b 0
:failed
echo Review failed. Copy the error above. Your source metadata and QC are unchanged.
pause
exit /b 1
