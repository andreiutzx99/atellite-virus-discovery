@echo off
cd /d "%~dp0"
python -m satellite_discovery.sequence_catalogue --wizard
if errorlevel 1 goto failed
echo Inventory complete. Open the report path printed above.
pause
exit /b 0
:failed
echo Inventory failed. Copy the error above. The input FASTA was not changed.
pause
exit /b 1
