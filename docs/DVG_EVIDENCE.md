# External DVG/recombination evidence (Milestone 5)

## Integration decision — recorded before implementation

The existing `artifact-workflow-v1` runner and trusted `WorkflowStageRegistry`
remain the only workflow framework. A registered `dvg_virema` external-tool
adapter accepts declared FASTQ reads, a declared FASTA reference, and an
optional checksum-validated catalogue records table. The stage uses the
existing artifact contracts, bounded argv-only execution, stage manifests,
output inventory, state machine, verified reuse, and workflow reporting.
Workflow JSON must never choose a script, shell command, aligner, output path,
or arbitrary ViReMa arguments. A second caller can later implement the same
evidence contract and use the same reporting interface without changing the
meaning of a negative result.

The upstream ViReMa script builds Bowtie indexes beside its reference FASTA
when an index does not exist. The adapter must first copy the checked reference
into its own stage directory. ViReMa may create indexes and raw outputs only
there; upstream inputs and M1–M4 stage artifacts remain untouched. The
adapter retains the native SAM, compiled results and logs. A strict parser
produces a separate normalized JSON document, a summary and an HTML report.
The compiled virus-virus junction output is the currently supported parser
surface; other ViReMa result families remain raw and are not silently
interpreted. The stage is optional: M1–M4-only manifests need no ViReMa
installation. In a combined manifest, a prior M4 report can finish before a
missing ViReMa dependency blocks M5-dependent stages.

### Declared contract

- Inputs: `reads` (`validated_fastq`), `reference` (declared FASTA artifact),
  optionally `catalogue_records` (`sequence_catalogue_records`); `sample_id`
  and bounded numeric caller settings are validated configuration data.
- Outputs: the unmodified `raw/Virus_Recombination_Results.txt`, normalized
  `evidence.json`, `summary.json`, `parameters.json`, and `report.html`. The
  stage manifest additionally inventories every regular raw/index/log file
  with SHA256; it records the argv representation, input/reference hashes,
  executable/source identities, timestamps, exit status and errors.
- Event fields include a stable evidence ID, caller and parser versions,
  sample and read-artifact identity, reference and sequence hashes, event
  type, both breakpoints and orientations, support count when supplied,
  explicitly null fields when unavailable, caller-native metadata, and a raw
  file/line/hash reference. Coordinates follow ViReMa's one-based positions.
- Catalogue linkage is **resolved** only for an exact reference record ID
  **and** sequence SHA256 match to a declared catalogue row. Cross-reference
  or ambiguous links remain **unresolved**; sequence names alone do not
  establish candidate identity.
- Complete evaluations report `DVG_EVIDENCE_DETECTED` or
  `NO_DVG_EVIDENCE_DETECTED`. Skipped/pending, missing dependency, execution
  failure/interruption, and malformed/incomplete output remain distinct:
  `NOT_EVALUATED`, `ANALYSIS_UNAVAILABLE`, `ANALYSIS_FAILED`, and
  `INVALID_RESULT`. A failed stage does not manufacture a successful evidence
  artifact. The root workflow manifest and HTML report expose its status.

The adapter identity and workflow reuse key must include reads, reference,
catalogue mapping, executable/source identity, parser source/version and
configuration. Raw and normalized output hashes are rechecked for reuse.
Changes to downstream report presentation alone should not require rerunning
ViReMa. An invalid, truncated, missing, duplicate or unsupported native
result must not become a zero-event result.

## Verified upstream source and redistribution boundary

- Repository: <https://github.com/Routh-Lab/ViReMaDocker>
- Audited commit: `481defd7c340bb52fa80748a89d478be9c265f64`
  (2022-05-24). The `src/ViReMa_0.25/ViReMa.py` startup banner identifies
  version **0.25**. Its adjacent `README.txt` still says **0.24**; do not
  infer the version from that stale line.
- Entry point: `python ViReMa.py Virus_Index Input_Data Output_SAM` with
  fixed validated options. It accepts single-read FASTQ (and FASTA with
  `-F`, not enabled here), builds/uses a Bowtie reference index, writes SAM,
  and compiles `Virus_Recombination_Results.txt` into its output directory.
  The adapter parses that compiled text, not SAM or optional BED output.
- Python source SHA256 at the pinned commit:
  - `ViReMa.py`: `c4c7cb46db9ac8a0427ef073db918cced451ef8bfb9e81bf906a784396c20486`
  - `ConfigViReMa.py`: `27bc2f61bae94c754ca80bcff22fa030676629eaddadc49cc24638868876da0e`
  - `Compiler_Module.py`: `6cfd3687639775fab6592aab4dec90c611b4752e5efc61b4f1964ed2c879c272`
- Licence: repository root `LICENSE` is MIT (Routh Lab, 2022); embedded
  `src/ViReMa_0.25/LICENSE.txt` grants MIT-style permission with Andrew
  Laurence Routh's 2013–2021 copyright. The bundled Bowtie 0.12.9 has its
  **own Artistic License** in `src/bowtie-0.12.9/COPYING`. The root MIT
  licence does not cover Bowtie or every other external dependency.
- Distribution: this project does **not** vendor ViReMa, Bowtie, the
  upstream Docker image, upstream test data, or other bundled dependencies.
  An operator installs/checks out the pinned ViReMa source separately,
  supplies its source directory via `VIREMA_HOME`, and installs the audited
  Linux x86_64 Bowtie 0.12.9 executables and Python with NumPy separately.
  The adapter verifies pinned source and executable hashes before execution.
  Upstream documents Python 3.7; other Python versions require actual runtime
  validation rather than an assumed compatibility claim.

## Linux runtime and continuous-integration evidence

The only verified real-runtime platform is Linux x86_64: Python 3.12, NumPy
2.5.3, and the three audited Bowtie 0.12.9 Linux x86_64 executables. The
ViReMa source files and Bowtie binaries were extracted from that exact source
commit for the test; they are temporary runtime dependencies, not checked-in
or redistributed project files. In addition to checking executable version
output, the adapter and CI diagnostic require exact Bowtie executable SHA256
matches: `bowtie` `95d87272268ec455f2bea7e9c03bdde7e03da8af87c1eb33dee000dace10f682`,
`bowtie-build` `b5bbc660d29afd372eb2929c8ee14fe98c01763126f41470a69a786c135e7cf7`,
and `bowtie-inspect` `91aba905857d56b9d3350f107ae616b8371f8e769bfccfab7e6ea8c5505c6504`.
The diagnostic records the expected, extracted, and adapter-inspected hashes
and version output.

These pins intentionally establish support only for those Linux x86_64
binaries. Windows unit tests exercise software behavior and unavailable states;
they do not establish a genuine ViReMa/Bowtie runtime on Windows. An absent
executable, unsupported platform, version mismatch, or executable hash mismatch
is `ANALYSIS_UNAVAILABLE`, never a zero-event/negative result.

The fixed software-only fixture uses a generated 1,500-base reference
(`SYNTHETIC_REF`) and eight identical reads per case, each with a unique FASTQ
name and `I` qualities. The positive reads concatenate `seq[199:259]` and
`seq[749:809]`; ViReMa's native output contains
`259_to_750_#_8` (with its native trailing tab), and the adapter reports
`DVG_EVIDENCE_DETECTED`, one event, breakpoints 259 and 750, and support 8.
The negative reads use `seq[199:319]`; native compiled ViReMa output is empty
and the adapter reports `NO_DVG_EVIDENCE_DETECTED`, zero events. Both outcomes
and their native/normalized SHA256 hashes passed adapter output validation
and verified reuse. The real runtime test produced raw result hashes
`d97979ff5fdc8ec9a8f487adc5c508b4cdff549b82ff91f022d2171d2335c893`
(positive) and
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
(empty negative result). The normalized `evidence.json` hashes were
`cf6d028baf9de5d80693e56453bcde19a54426e97d57d051e90c78f747d2982e`
(positive) and
`fa7a86cdfd316dbc9c0415b630b93aeea1b2c488a76612bbc3b8947f8d1796ce`
(negative). The pinned Bowtie executable SHA256 values were
`95d87272268ec455f2bea7e9c03bdde7e03da8af87c1eb33dee000dace10f682`
(`bowtie`),
`b5bbc660d29afd372eb2929c8ee14fe98c01763126f41470a69a786c135e7cf7`
(`bowtie-build`), and
`91aba905857d56b9d3350f107ae616b8371f8e769bfccfab7e6ea8c5505c6504`
(`bowtie-inspect`).

An empty native result is accepted as zero events only when ViReMa stdout has
one analyzed-read count matching the staged FASTQ record count, one
recombination-count summary, and the final nonempty line is the completion
marker `Time to complete in seconds:  N`. Missing/duplicate markers, a read
count mismatch, or otherwise incomplete native/stdout output is
`INVALID_RESULT`, not a negative evaluation.

CI independently fetches the pinned commit into a temporary Git checkout,
extracts only the three hash-verified Python files and the three Bowtie
executables with `git show`, verifies the exact executable hashes above and
runs the same two generated cases. The optional
Ubuntu tools job pins NumPy 2.2.6 and uploads the bounded report, logs, and
synthetic artifacts under `artificial-virema-evidence` even on failure. The
script limits each caller run to 180 seconds and the stage to 400 MB; Git and
version probes also have timeouts. This is operational evidence for this
particular Linux software fixture, not a general resource sandbox or evidence
of sensitivity, specificity, breakpoint accuracy on biological data, or
clinical/biological validity. It does not validate the sensitivity or
specificity of the ViReMa parser/caller.

The installed NumPy 2.5.3 distribution metadata reports the license
expressions `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`. NumPy remains
an external runtime dependency; this report does not make a blanket licensing
claim for all dependencies or vendor NumPy.

## Interpretation and future aggregation

ViReMa produces **caller-specific junction evidence**, not a final biological
classifier. A detected junction can support a DVG/recombination
interpretation. **No DVG evidence detected by the configured caller** means
only that this run reported no supported junctions under its settings; it
does not establish that the sequence is not a DVG. An unavailable, failed,
interrupted or invalid run draws no biological conclusion. M5 neither
validates satellite-virus discovery nor classifies any sequence as a
satellite virus. See the [current M5 milestone description](M5_DVG_EVIDENCE.md).

A future aggregator consumes caller-neutral evaluation summaries and event
references, preserving each caller's status and raw provenance. It can report
caller A only, caller B only, multiple callers, conflicting outputs, no
evidence from evaluated callers, caller unavailable and caller failed.
Agreement or zero events must not be converted into `NON_DVG` or any
equivalent classification. No second caller is integrated in M5.

The [30-point local acceptance audit](M5_AUDIT.md) records the software,
workflow, provenance, licensing, and CI-configuration checks separately from
remote publication gates.