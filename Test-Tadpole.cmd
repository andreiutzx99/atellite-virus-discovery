@echo off
cd /d "%~dp0"
echo Testing installed Tadpole with generated random data. Existing QC runs are unchanged.
python -u scripts/test_tadpole_runtime.py --output "runs/tadpole-test-%RANDOM%-%RANDOM%"
if errorlevel 1 goto failed
echo PASS: the installed assembler exactly reconstructed the synthetic fixture.
pause
exit /b 0
:failed
echo FAIL: copy the error above. See the report path if one was printed.
pause
exit /b 1
