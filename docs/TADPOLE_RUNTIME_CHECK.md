# Tadpole on Windows: runtime check

Tadpole 40.01 is installed locally under this development project's `.tools` directory. It uses the existing Java runtime. No administrator access, WSL, Docker or additional ChatGPT plugin was needed for the synthetic runtime test.

This addition provides an application-side diagnostic launcher, not a completed assembly/discovery workflow. It does not read existing sequencing runs. It generates random test data and checks that one 1,000-base sequence is reconstructed exactly, allowing reverse-complement orientation. Passing this test does not demonstrate equivalence to SPAdes, sensitivity on real data, or satellite/helper dependence.

## Optional repeat test

1. Open `C:\Users\ad6752\Documents\Codex\2026-09-19\a\outputs\satellite-discovery` in File Explorer. This is the development project, not the older `satellite-discovery-v0.2.0` installation.
2. Double-click `Test-Tadpole.cmd`.
3. Wait for `PASS: the installed assembler exactly reconstructed the synthetic fixture.`
4. The terminal prints the full path to a new `report.html`. Open that file to inspect the result. Its folder also contains `test_result.json` and `assembly.log`.
5. If the test prints `FAIL`, copy the error text and report path. Do not delete or repeat your completed QC run.

Every attempt uses a new output folder. Existing output folders are refused. The test validates the pinned BBTools archive and installed runtime files before invoking Java; it records the Java version, command, input/output checksums and outcome. A subprocess timeout produces a failed report. The launcher requires Python and Java on PATH, and the locally installed pinned BBTools archive/runtime. It does not install missing dependencies automatically.

Source: [BBTools](https://github.com/bbushnell/BBTools), commit `7afa43b1bb3ad07493ac93a67ada4a5ec779f0c0`.

Archive SHA256: `36b1c7be738f16185e967e33cab909e660b0f33a905b1fe06043f24a314a3725`.

The tools directory is ignored by Git. Committing this launcher does not install BBTools on another computer.
