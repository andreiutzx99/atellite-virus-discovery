# M31 — Reproducible Synthetic Evidence Screening and Candidate Triage

**Conclusion:** Frozen M8 executed with the verified pinned runtime on synthetic inputs. Triage summarizes only synthetic-panel similarity; M29 measured support is NOT_SUPPLIED and final biological sensitivity/specificity remain NOT_EVALUATED.

## Runtime verification

Profile: `m8-blastn-linux-x86_64-v1`; release `2.17.0+`.

| Executable | Version | SHA-256 | Pinned |
|---|---|---|---|
| blastn | 2.17.0+ | `33b64bc67d3149cee2459b2f7766b363323df632cf12c099546de00aea9698b5` | True |
| makeblastdb | 2.17.0+ | `c1ffdcf6f15d1d8d75377cc9f37afa42bc9fa06678903bad77c2641e60778fce` | True |

Platform: Linux x86_64. M8 aggregate status: **COMPLETE**.

## Frozen screening and triage

Panel digest: `0d4edce726cd77e2a238a37daee24046e63e09d12ba0862cb491e8473ec87f43`. Candidate input digest: `18655e4087812b9d6bef8ac36a834dacc22da2724d3de206e0db0d502ade413e`. Synthetic reference FASTA digest: `5b62f17add445c9b089096ac0f52de061b462b1eeeef8ccb61bf8129743db4b0`.

The short and partial held-out queries derive from the separately seeded SYN006.1 family, not the development target. Retrospective truth is stored in separate sidecars and is not passed to M8 or triage.

The unmodified M8 workflow ran both frozen DUST masking branches and selected its task by query length. M8 alignments remain similarity evidence only. Triage criteria were frozen in code before the held-out cases were evaluated.

| Candidate | Split | M8 outcome | Triage | Reason | M29 linkage |
|---|---|---|---|---|---|
| q001 | development | completed stage; see JSON | REVIEW_PRIORITY | Strong synthetic target-role similarity; identity and M29 support remain unestablished. | NOT_SUPPLIED |
| q002 | development | completed stage; see JSON | REVIEW_PRIORITY | Strong synthetic target-role similarity; identity and M29 support remain unestablished. | NOT_SUPPLIED |
| q003 | development | completed stage; see JSON | BACKGROUND_LIKE | Strong helper-role synthetic similarity; this is panel-relative only. | NOT_SUPPLIED |
| q004 | development | completed stage; see JSON | INSUFFICIENT_EVIDENCE | No qualifying synthetic-panel alignment; this is not evidence of novelty. | NOT_SUPPLIED |
| q005 | tuning | completed stage; see JSON | INSUFFICIENT_EVIDENCE | Alignment is low-complexity-sensitive and requires review. | NOT_SUPPLIED |
| q006 | tuning | completed stage; see JSON | CONFLICTING_EVIDENCE | Strong alignments occur in both synthetic panel roles. | NOT_SUPPLIED |
| q007 | held_out | completed stage; see JSON | REVIEW_PRIORITY | Strong synthetic target-role similarity; identity and M29 support remain unestablished. | NOT_SUPPLIED |
| q008 | held_out | completed stage; see JSON | REVIEW_PRIORITY | Strong synthetic target-role similarity; identity and M29 support remain unestablished. | NOT_SUPPLIED |
| q009 | held_out | completed stage; see JSON | INSUFFICIENT_EVIDENCE | No qualifying synthetic-panel alignment; this is not evidence of novelty. | NOT_SUPPLIED |

Full normalized alignment rows, both masking-branch statuses, commands, truncation indicators, and raw-output hashes are in the JSON report and generated M8 run directory.

## M29 linkage and final metrics

**M29 linkage: NOT_SUPPLIED.** The merged M29 report is present, but no original per-run assembly/read-support artifacts were retained in the repository or supplied with this request.

The M31 candidate handoff is a synthetic M8 contract fixture with M6 support set to NOT_EVALUATED; it is not real M6 or M29 support. The truth files are retrospective-only and are not passed to M8 or triage.

Final biological discovery sensitivity, specificity and false-discovery rate: **NOT_EVALUATED**. Triage is not a biological acceptance classifier.

## Reproduction

Download the archive from the pinned URL in `m8_blastn_profile.py`, verify its SHA-256 and both executable hashes, extract BLAST+ 2.17.0+, then run:

```sh
export LD_LIBRARY_PATH=/path/to/libgomp-directory${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
PYTHONPATH=. python -m satellite_discovery.m31_synthetic_evidence_screening --output /tmp/m31-run --blastn /path/to/blastn --makeblastdb /path/to/makeblastdb
```

Only deterministic synthetic sequences are generated. No external biological reference database is queried.

## Governance

```text
decision=INCOMPLETE
overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION
biological_execution_authorized=false
```
