@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m satellite_discovery.review_ui
) else (
  python -m satellite_discovery.review_ui
)
pause
