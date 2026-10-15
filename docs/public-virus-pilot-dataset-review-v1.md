# Public-virus pilot dataset review v1

**Curation date:** 2026-10-14  
**Review scope:** Metadata and literature only. No sequencing files were downloaded or inspected; no acquisition, QC, assembly, or discovery was run.  
**Decision:** **No eligible dataset; no pilot or backup run selected.** Acquisition remains disabled.

## Decision rules

This review applies the existing `public-virus-v1` policy without changing its identity terms, accepted sample-level attribute keys, or M1–M16 contracts. A study title, GEO treatment label, or paper statement is useful scientific context but does not replace the policy’s archive sample-level identity evidence. Human host taxonomy alone is not virus identity.

A candidate run must also have a complete ENA FASTQ file manifest with byte counts and checksums, and the sum of compressed file sizes for the entire run must be **at most 1,000,000,000 bytes**. The threshold is applied separately to each complete run, not to an individual mate or a subset of files. These are curation findings only: passing technical checks would not authorize retrieval.

## Ranked assessment

Rank reflects scientific fit for an RNA-focused public-virus pilot, not permission to acquire. A held candidate is not treated as eligible.

| Rank | Study | Scientific fit | Archive/run summary | Status and reason |
|---|---|---|---|---|
| 1 | **GSE252692 / PRJNA1062064 / SRP482325** — HCoV-OC43 in MRC-5 cells, time course | Strongest RNA-oriented design: infected and heat-inactivated-virus mock conditions across time. GEO labels the conventional RNA-seq samples as rRNA-depleted. The same series also contains ribosome-profiling libraries, which are not conventional RNA-seq inputs. | 66 GEO samples / runs: 40 conventional RNA-seq and 26 ribosome-profiling/non-conventional libraries. All 40 conventional runs have complete listed FASTQ manifests and MD5s, but are **1,619,285,979–4,176,610,114 bytes** each (aggregate 121,483,410,130 bytes). | **EXCLUDED — size.** No conventional run meets the cap. The other 26 libraries are excluded as the wrong assay type. |
| 1 | **GSE155986 / PRJNA656274 / SRP276927** — HCoV-229E in MRC-5 cells, time course | Reported 6/24/48/72 h infected groups and three GEO replicate labels at each deposited timepoint. The three 0 h “Untreated” samples have unresolved inoculation/control status. The article and sample-level GEO protocol mention 96 h, but the series design and 15 deposited samples omit it. The paper reports TruSeq RNA Library Preparation Kit v2; the archive selection field says cDNA and does not establish poly-A selection or rRNA depletion. | 15 single-end RNA-seq runs; all have complete listed FASTQ manifests and MD5s. **662,991,065–812,687,023 bytes** each; aggregate 10,766,007,476 bytes. | **HELD — identity.** Every run fits the size cap, but the exact SRA/BioSample sample records identify human samples and do not carry an accepted HCoV-229E identity attribute. GEO and paper labels support the study context but do not override the existing identity gate. |
| 2 | **GSE279271 / PRJNA1171767 / SRP537929** — HCoV-229E in A549 and MRC-5 cells, 24 h | Useful infected/mock comparison in two cell types. Six sample/well labels per group are present; those labels alone do not establish independent biological replicates. The reviewed GEO/ENA fields identify cDNA selection but do not establish poly-A enrichment or rRNA depletion. | 24 paired-end RNA-seq runs; all have complete listed FASTQ manifests and MD5s. **4,138,527,400–5,606,970,308 bytes** each; aggregate 116,796,344,406 bytes. | **EXCLUDED — size.** No run meets the cap. |
| 3 | **GSE279463 / PRJNA1172745 / SRP538516** — HCoV-229E in primary human airway epithelial samples, 24 h | Strong primary-cell relevance and mock/infected groups. Four samples per group are represented by suffix labels; donor independence is not established by those labels. Enrichment/depletion is not confirmed in the reviewed archive metadata. | 8 paired-end RNA-seq runs; all have complete listed FASTQ manifests and MD5s. **3,941,984,395–4,990,508,280 bytes** each; aggregate 35,161,559,393 bytes. | **EXCLUDED — size.** No run meets the cap. |

GSE252692 and GSE155986 share the highest scientific-fit rank because each offers a time course and control context; neither can be selected under the current gates. GSE279271 ranks ahead of GSE279463 for having two cell types and explicit infected/mock groups, while the latter has primary-cell relevance. These scientific distinctions do not change the technical outcomes.

## Identity, design, and limitations

- **GSE252692:** GEO and the paper describe OC43-infected MRC-5 samples and heat-inactivated-virus mock controls. The paper reports infection at MOI 7, a time course from −1 h through 30 h, and RNA-seq at each timepoint. Archive rows map each conventional run to its GEO sample, SRA experiment/run, BioSample, ENA FASTQ path(s), compressed byte count(s), and MD5(s). The corresponding ribosome-profiling records are retained in the machine-readable file but marked excluded from this RNA-seq pilot.
- **GSE279271:** GEO provides the infected/mock and A549/MRC-5 sample group labels. The linked DataHub dataset describes HCoV-229E infection. GEO/ENA record cDNA selection; the reviewed sources do not establish poly-A enrichment or rRNA depletion. Exact donor/culture-level replicate independence was not confirmed; a count of distinct wells or accessions is not taken as proof of independent biological replicates.
- **GSE155986:** GEO and the publication describe HCoV-229E infection and the time course. The 0 h samples are labelled “Untreated,” while the paper describes a 0 h post-infection collection; inoculation timing and control role remain unresolved, so they are not designated pre-infection baselines or mock controls. The article and GEO sample protocol list 96 h, but the GEO series design and deposited 15-sample set list only 0/6/24/48/72 h; the reason is unknown. Although the FASTQ sets fit the cap, the existing fixture for SRR12424243 records `sample_level_virus_identity_missing` / insufficient identity on the exact SRA/BioSample record. No GEO, paper, title, or host-taxonomy override was applied. This is a policy-gate hold, not a finding that the study itself is unrelated to HCoV-229E.
- **GSE279463:** GEO and the linked DataHub description support an HCoV-229E primary-airway study with mock and infected conditions at 24 h. The archive sample labels do not by themselves establish independent donors. All complete run manifests exceed the cap.
- **Strain/isolate and batch provenance:** Not used to upgrade any identity or independence determination. Where the reviewed metadata did not establish an exact isolate, preparation batch, or independent biological unit, it remains unknown rather than inferred.
- **No biological validation:** The review does not establish infection, viral load, contamination status, sample integrity, or biological independence from reads. No sequencing reads were obtained.

## Final selection

| Role | Selection |
|---|---|
| Pilot | **None** |
| Control | **None** |
| Backup | **None** |
| Eligible run count | **0** |

GSE155986 is the only candidate with conventional RNA-seq runs under the cap, but remains held by the unchanged virus-identity gate. The other candidates have no conventional RNA-seq run under the cap. Therefore, there is no eligible dataset and no defensible control or backup run to nominate. Do not enable acquisition on the basis of this review.

## Reproducibility and source records

The versioned machine-readable companion, [`public-virus-pilot-dataset-review-v1.json`](public-virus-pilot-dataset-review-v1.json), contains all 113 run-level records (including the 26 excluded ribosome-profiling/non-conventional records), archive accession relationships, GEO sample labels, complete ENA FASTQ file paths, compressed byte counts, MD5 checksums, technical status, and per-run reasons. It is a metadata curation record, not an authorization document or authenticated archive snapshot.

Primary sources:

1. GEO GSE252692, [series record](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE252692); NCBI [BioProject PRJNA1062064](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1062064); paper, [PLOS Pathogens 2024](https://doi.org/10.1371/journal.ppat.1012831).
2. GEO GSE279271, [series record](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE279271); NCBI [BioProject PRJNA1171767](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1171767); linked [PNNL DataHub dataset 34069](https://data.pnnl.gov/group/nodes/dataset/34069).
3. GEO GSE155986, [series record](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE155986); NCBI [BioProject PRJNA656274](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA656274); paper, [PLOS ONE 2021](https://doi.org/10.1371/journal.pone.0247128). The existing exact-run fixture is `tests/fixtures/public_virus_metadata/SRR12424243.json`.
4. GEO GSE279463, [series record](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE279463); NCBI [BioProject PRJNA1172745](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1172745); the PNNL ACS-DP1 description ([DataHub dataset 34069](https://data.pnnl.gov/group/nodes/dataset/34069)) lists GSE279463 as its HAE dataset. PNNL dataset 34086 instead links to GSE280019 and was not treated as the source for GSE279463.
5. Per-run file paths, compressed sizes, and MD5s were curated from the [ENA Portal file-report API](https://www.ebi.ac.uk/ena/portal/api/filereport) and reconciled to GEO/SRA run accessions. The complete per-file records are in the JSON companion.

---

**Final status: no eligible dataset; acquisition remains disabled.**
