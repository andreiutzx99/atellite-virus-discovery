@echo off
cd /d "%~dp0"
python -m satellite_discovery.observation_report --wizard
if errorlevel 1 goto failed
echo Report complete. Open the report path printed above.
pause
exit /b 0
:failed
echo The comparison failed. Copy the error message above; input files were not changed.
pause
exit /b 1
