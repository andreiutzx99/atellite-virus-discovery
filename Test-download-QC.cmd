@echo off
cd /d "%~dp0"
echo This test retrieves a public RNA-seq run and performs baseline QC.
echo It downloads about 170 MB and processes about 5.1 million reads. Allow 20-30 minutes.
echo Repeating this test reuses verified files. No satellite analysis is performed.
python -m satellite_discovery --helper influenza-a --limit 2 --query "SRR3157747[Accession]" --stage qc --max-download-mb 200 --output runs/phase3-guided-test
if errorlevel 1 goto failed
start "" "runs\phase3-guided-test\report.html"
echo SUCCESS: Open the report and check that Download and QC says complete.
pause
exit /b 0
:failed
echo The test did not complete. Copy the last 15 lines above and send them to Codex.
echo If present, also send runs\phase3-guided-test\phase3\manifest.json.
pause
exit /b 1
