> Historical version 0.2.0 instructions; not current development commands.
> For current capabilities and supported commands, see the [README](../README.md)
> and [milestone roadmap](ROADMAP.md).

# How to test version 0.2.0

## What this version does

It finds public sequencing metadata, selects complete FASTQ runs within a download budget, retrieves those files, verifies their archive checksums, and performs basic read QC. It does not perform helper mapping, assembly, DVG detection or satellite discovery. This is a software integration test on real archived reads, not a known-satellite rediscovery experiment.

## Get the updated program

If you use the folder already managed by Codex on this computer, it has been updated. The folder is `outputs/satellite-discovery` in this task's workspace.

If you previously downloaded the program from GitHub to a different location:

1. Open https://github.com/andreiutzx99/atellite-virus-discovery .
2. Click **Code**, then **Download ZIP**.
3. Extract the ZIP into a **new folder**. Keep the old folder and its results.
4. Open the extracted folder. You should see both `Start.cmd` and `Test-download-QC.cmd`.

Python 3.11 or newer must already be available as `python`. No additional Python packages, Linux installation, API keys or manually supplied sequencing files are required for this release.

## First test — exact steps

1. Double-click **Test-download-QC.cmd**.
2. Leave the terminal open while it runs. It retrieves metadata linked to accession `SRR3157747`, selects a complete run within a 200 MB compressed-input budget, and prints download and QC progress.
3. Expect about **170 MB** to download on the first run. Keep at least **1 GB free** for originals, QC outputs and temporary files. The file contains about **5.1 million reads**. Allow **20–30 minutes** for the first test with the portable Python QC engine; your machine may be faster or slower. A progress line appears after every 100,000 processed reads. Keep the window open while those numbers increase.
4. When it succeeds, your browser opens the report automatically.
5. The report should show **Download and QC: complete**, one completed run, and nonzero input/retained read counts. The selected accession should be `SRR3157747` while the source metadata remains unchanged. Four metadata rows may appear: the archive experiment contains multiple runs. Only the budgeted run is downloaded.
6. Send Codex: **“The Phase 3 test completed”** and either a screenshot of the top of the report or its input/retained read counts.

The report is saved at `runs/phase3-guided-test/report.html` inside the extracted project folder. You can reopen it at any time. The `.cmd` launcher only opens this local file in your browser; it does not publish your results.

## Test resume

After the first successful test, double-click **Test-download-QC.cmd** again. Expect messages beginning **Reusing verified** for the FASTQ and QC results. The program rechecks file integrity; it should not download the same file again or recompute unchanged QC.

## Run your own metadata/download pilot

Double-click **Start.cmd** and enter these responses:

| Prompt | Enter |
|---|---|
| Helper number | `1` for influenza A |
| Maximum experiments | `10` initially |
| Retrieve possible study controls? | `n` for the first software test |
| Stage | `2` for download and QC |
| Maximum complete runs to download | `1` |
| Total compressed download budget in MB | `1000` |
| Output folder | Press Enter to accept a new timestamped folder |

The default search now targets supported broad libraries and Illumina sequencing, excludes explicitly PCR-selected libraries, and uses records published at least 90 days ago to allow time for FASTQ mirrors. It also tries additional studies rather than spending the entire search budget on one study. The exact query/cutoff is saved and reused on resume. This is purposeful pilot sampling, not an exhaustive search. It may still find no complete run within your budget.

If the report says **no_suitable_downloads**, expand **Why other runs were skipped**. A missing file link, unsupported layout or exceeded budget is not a negative satellite finding. For a predictable software check, use the guided test above. For broader dataset selection, share the skipped reasons with Codex before choosing larger resource limits.

## If something goes wrong

- **Python is not recognized:** send that exact message to Codex; do not repeatedly rerun the launcher.
- **Download interrupted:** rerun the same launcher with the same output folder. Completed files are checksum-verified and reused; a partial transfer resumes where the server supports Range.
- **Checksum mismatch:** send the error and filename. A mismatching partial file is deliberately retained and never reported as a successful download.
- **Parameters changed:** choose a new output folder. Do not delete old results to force the new settings into them.
- **Already running / interrupted lock:** first close the earlier terminal and confirm no copy of this workflow is still running. Then send Codex the path of `phase3/.running.lock`; this file may need removal after an abrupt system shutdown. Do not remove it while another run is active.
- **Other failure:** copy the last 15 terminal lines and attach the `phase3/manifest.json` file from the output folder if it exists. This provides the failed stage and reason. Do not send FASTQ files; they can be large and are unnecessary for initial troubleshooting.

## Exact terminal alternatives

Open PowerShell **inside the project folder** (the folder containing `Start.cmd`). Run:

```powershell
python -m satellite_discovery --helper influenza-a --limit 2 --query 'SRR3157747[Accession]' --stage qc --max-download-mb 200 --output runs/phase3-guided-test
```

To reopen the report:

```powershell
Start-Process .\runs\phase3-guided-test\report.html
```

To replay without using the network, after a successful first run:

```powershell
python -m satellite_discovery --helper influenza-a --limit 2 --query 'SRR3157747[Accession]' --stage qc --max-download-mb 200 --output runs/phase3-guided-test --offline
```
