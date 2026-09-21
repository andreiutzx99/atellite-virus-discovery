@echo off
cd /d "%~dp0"
python -m satellite_discovery.review_ui
if errorlevel 1 echo Review launcher failed. Copy the error above.
pause
