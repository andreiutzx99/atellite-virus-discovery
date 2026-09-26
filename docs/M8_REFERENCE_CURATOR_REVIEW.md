# M8 Initial Reference Curator Review

**Curation date:** 2026-09-26
**Scope:** metadata and initial-panel eligibility for the 14 accession.version records in the starter catalogue.
**Boundary:** this is a reference-membership decision, not a classification of future candidates, sequence validation, rights clearance, or M8 implementation.

## Decision

The 14 records are approved for the initial M8 reference metadata definition, each in its existing distinct role. The four plant satellite/subviral records are `APPROVED_INITIAL_REFERENCE`. The five related/context records and five helper records are `APPROVED_CONTEXT_REFERENCE`. All 14 therefore have initial-panel inclusion **yes**, but only the first four belong to `satellite_subviral`; the other ten must remain in their contextual or helper roles.

Approval is limited to exact accession.version metadata membership in a role-separated panel plan. It does not establish that a future candidate has the role of a matching reference, nor does it authorize bundling or redistributing a sequence. The reference data remain externally retrieved under the Class B policy. No sequence payload was retrieved or added.

## Sources and method

- Queried NCBI Nucleotide ESummary for all 14 exact accession.versions and NCBI Taxonomy ESummary for the 12 TaxIDs on 2026-09-26. The summaries confirmed the current record title/organism, accession.version, TaxID, sequence length, molecule, topology, strand when returned, and completeness when returned. These are live summaries, not an archived taxonomy release; no sequence records or sequence bytes were fetched.
- Queried NCBI ELink `nuccore_pubmed` for the Nucleotide records, then checked PubMed summaries for the linked publication titles. `source_study_ids` below is restricted to verified accession-linked primary sequence/provenance papers; it is not a list of every paper that supports a biological relationship. Evidence papers about helper systems are identified separately.
- Checked the applicable ICTV material: the current Tonesaviridae interim report for V01468.1, the Kolmioviridae/Deltavirus report for HDV, the Pospiviroid report for PSTVd, and the ICTV satellite introduction for historical satellite-group context. The older ICTV satellite list is not treated as an accession catalogue or a current taxonomy release.
- Primary study identifiers are normalized as `PMID:<number>`. A DOI or publication that supports general biology is not substituted for an accession-linked source study. No unsupported study ID is inferred.

NCBI ESummary does not provide an archived taxonomy release or a complete legal/rights determination. The current NCBI names are retained separately from accession titles and historical publication names. Completeness, topology, strand, and segment claims below are limited to the fields returned by NCBI and the explicitly cited authoritative/literature sources; they are not independent sequence-integrity checks.

## Record-by-record decisions

### 1. `NC_002602.2` — Cucumber mosaic virus satellite RNA

- **Panel role:** `satellite_subviral` / `plant_satellite_rna`.
- **Curation state:** `APPROVED_INITIAL_REFERENCE`.
- **Initial-panel inclusion:** **yes**.
- **Evidence basis:** NCBI RefSeq ESummary and Taxonomy identify a 336-nt RNA record, linear, single-stranded, complete, TaxID 12436. It is one satellite RNA molecule, not a numbered CMV genome segment. NCBI links the record to the original sequence paper, PMID 18627882. PMID 17342261 supports CMV satellite-RNA system biology.
- **Helper-evidence scope:** CMV helper functions are established for the satellite-RNA system. Neither PMID 17342261 nor the RefSeq metadata establishes that a particular CMV accession/isolate is the paired helper for this satellite accession. The three CMV segment records below are contextual records only; no exact isolate pairing is asserted.
- **Source/terms disposition:** NCBI RefSeq, exact accession.version `NC_002602.2`; future sequence retrieval is external by exact accession through NCBI E-utilities or NCBI Datasets. Cite the NCBI record and PMID 18627882 for provenance; no record-specific sequence license or attribution notice was established by the metadata query. Repository treatment is accession/provenance/retrieval-manifest only; Class B; the sequence remains externally retrieved. Verify record/source terms before any materialized snapshot or redistribution.
- **Remaining caveat:** exact helper isolate pairing is unresolved. This does not prevent metadata membership.
- **Verified source study:** `PMID:18627882`.

### 2. `NC_003847.1` — Panicum mosaic satellite virus

- **Panel role:** `satellite_subviral` / `plant_satellite_virus`.
- **Curation state:** `APPROVED_INITIAL_REFERENCE`.
- **Initial-panel inclusion:** **yes**.
- **Evidence basis:** NCBI RefSeq ESummary and Taxonomy identify an 826-nt single-stranded RNA, linear and complete, TaxID 154834. It is one non-segmented satellite-virus RNA and is separate from its helper virus. The accession-linked primary genome paper is PMID 18644571. Helper-system studies include PMID 16014937 and PMID 31455653.
- **Helper-evidence scope:** Panicum mosaic virus supports replication and spread at the biological-system level. RefSeq `NC_002598.1` is an appropriate separate helper-context record, but it is not claimed to be the isolate used in every experiment.
- **Source/terms disposition:** NCBI RefSeq, exact accession.version `NC_003847.1`; future sequence retrieval is external by exact accession through NCBI E-utilities or NCBI Datasets. Cite the NCBI record and PMID 18644571; no record-specific sequence license or attribution notice was established by the metadata query. Repository treatment is accession/provenance/retrieval-manifest only; Class B; the sequence remains externally retrieved. Verify record/source terms before any materialized snapshot or redistribution.
- **Remaining caveat:** no exact PMV helper accession/isolate pairing is asserted.
- **Verified source study:** `PMID:18644571`.

### 3. `V01468.1` — Satellite tobacco necrosis virus 1

- **Panel role:** `satellite_subviral` / `plant_satellite_virus`.
- **Curation state:** `APPROVED_INITIAL_REFERENCE`.
- **Initial-panel inclusion:** **yes**.
- **Evidence basis:** NCBI/INSDC ESummary reports a 1,239-nt linear RNA record and current Taxonomy name *Albetovirus alphatabaci* (TaxID 3426007). The accession title retains the historical name “Satellite tobacco necrosis virus 1.” NCBI did not return strand or completeness fields. The linked primary papers are PMID 6260960 (near-full-size DNA copy of the RNA) and PMID 427118 (5′-terminal sequence). ICTV’s 2025-established family Tonesaviridae interim report identifies V01468 as an example of species *Albetovirus alphatabaci* and describes a positive-sense RNA satellite virus.
- **Helper-evidence scope:** ICTV describes replication dependence on helper viruses in genera *Alphanecrovirus* or *Betanecrovirus* (family Tombusviridae). This is group-level evidence, not an exact helper accession/isolate pairing for V01468.1.
- **Source/terms disposition:** INSDC/GenBank record, exact accession.version `V01468.1`; future sequence retrieval is external by exact accession through NCBI E-utilities or an INSDC provider API. Cite the accession record, PMID 6260960 and PMID 427118; no record-specific sequence license or attribution notice was established by the metadata query. Repository treatment is accession/provenance/retrieval-manifest only; Class B; the sequence remains externally retrieved. Verify record/source terms before any materialized snapshot or redistribution.
- **Remaining caveat:** ESummary does not assert completeness; do not label the accession a complete genome based only on its title. Preserve historical accession title and current NCBI/ICTV taxonomic name as separate fields. Exact helper isolate remains unknown.
- **Verified source studies:** `PMID:6260960`, `PMID:427118`.

### 4. `AJ298903.1` — Cotton leaf curl Multan betasatellite

- **Panel role:** `satellite_subviral` / `plant_satellite_dna`.
- **Curation state:** `APPROVED_INITIAL_REFERENCE`.
- **Initial-panel inclusion:** **yes**.
- **Evidence basis:** NCBI/INSDC ESummary identifies a 1,349-nt DNA record, circular and complete, TaxID 306025. The title says “c1 gene,” but the record summary marks the accession complete and circular; the accession-linked primary paper, PMID 11437658, reports the DNA components required for cotton leaf curl disease. The cited 2003 study PMID 14551819 is supporting system literature, not the direct accession-linked source-study ID. The older ICTV satellite list names the betasatellite group but gives a different representative accession (AJ292769); that older list is not evidence that AJ298903.1 is the same sequence.
- **Helper-evidence scope:** Cotton leaf curl Multan virus trans-replication and compatible begomovirus associations are established for the documented DNA-beta system. No single helper accession or exclusive isolate pairing is assigned.
- **Source/terms disposition:** INSDC/GenBank record, exact accession.version `AJ298903.1`; future sequence retrieval is external by exact accession through NCBI E-utilities or an INSDC provider API. Cite the accession record and PMID 11437658; no record-specific sequence license or attribution notice was established by the metadata query. Repository treatment is accession/provenance/retrieval-manifest only; Class B; the sequence remains externally retrieved. Verify record/source terms before any materialized snapshot or redistribution.
- **Remaining caveat:** do not replace this accession with the ICTV list’s AJ292769 or claim those records are sequence-identical. The exact helper isolate is unresolved.
- **Verified source study:** `PMID:11437658`.

### 5. `NC_001653.2` — Hepatitis delta virus

- **Panel role:** `delta_related_subviral` / `deltavirus_context`.
- **Curation state:** `APPROVED_CONTEXT_REFERENCE`.
- **Initial-panel inclusion:** **yes**, as contextual deltavirus evidence only.
- **Evidence basis:** NCBI RefSeq ESummary and Taxonomy identify a 1,682-nt circular, single-stranded RNA record, TaxID 12475. ICTV places genus *Deltavirus* in family Kolmioviridae. The accession-linked cloning/sequencing papers are PMID 3627276 and PMID 2374010. NCBI does not return RNA polarity in ESummary; ICTV describes HDV as negative-sense.
- **Helper-evidence scope:** HBV surface antigen supports HDV particle envelopment and transmission. That evidence is distinct from HDV RNA replication, which is not represented here as requiring HBV. ICTV also discusses other helper-virus evidence in vitro. `NC_003977.2` is a separately identified HBV context record, not an asserted matched strain.
- **Source/terms disposition:** NCBI RefSeq, exact accession.version `NC_001653.2`; future sequence retrieval is external by exact accession through NCBI E-utilities or NCBI Datasets. Cite the NCBI record and PMID 3627276/2374010; no record-specific sequence license or attribution notice was established by the metadata query. Repository treatment is accession/provenance/retrieval-manifest only; Class B; the sequence remains externally retrieved. Verify record/source terms before any materialized snapshot or redistribution.
- **Remaining caveat:** keep the deltavirus role separate from the plant satellite member role and preserve the envelopment/transmission versus replication distinction.
- **Verified source studies:** `PMID:3627276`, `PMID:2374010`.

### 6. `NC_002030.1` — Potato spindle tuber viroid

- **Panel role:** `related_non_satellite` / `viroid_context`.
- **Curation state:** `APPROVED_CONTEXT_REFERENCE`.
- **Initial-panel inclusion:** **yes**, as a viroid comparator only.
- **Evidence basis:** NCBI RefSeq ESummary and Taxonomy identify a 359-nt, circular, single-stranded RNA record, TaxID 12892. ICTV places PSTVd in genus *Pospiviroid* and describes Pospiviroidae genomes as circular ssRNA. PMID 643081 is the accession-linked primary sequence paper; the linked PMID 472709 is a review, not used as a source-study ID.
- **Helper-evidence scope:** no helper virus is assigned. Viroid replication using host machinery is not helper-virus dependence.
- **Source/terms disposition:** NCBI RefSeq, exact accession.version `NC_002030.1`; future sequence retrieval is external by exact accession through NCBI E-utilities or NCBI Datasets. Cite the NCBI record and PMID 643081; no record-specific sequence license or attribution notice was established by the metadata query. Repository treatment is accession/provenance/retrieval-manifest only; Class B; the sequence remains externally retrieved. Verify record/source terms before any materialized snapshot or redistribution.
- **Remaining caveat:** retain the viroid role; do not classify it as a satellite or helper-virus record.
- **Verified source study:** `PMID:643081`.

### 7. `NC_011132.1` — Sputnik virophage

- **Panel role:** `related_non_satellite` / `virophage_context`.
- **Curation state:** `APPROVED_CONTEXT_REFERENCE`.
- **Initial-panel inclusion:** **yes**, as a virophage context record only.
- **Evidence basis:** NCBI RefSeq ESummary and Taxonomy identify an 18,343-bp circular, double-stranded DNA genome, TaxID 543939, with the host/source note naming *Acanthamoeba polyphaga mimivirus*. NCBI links the RefSeq record to the original study, PMID 18690211. That primary paper reports the Sputnik experimental system and originally cites accession EU606015.1.
- **Helper-evidence scope:** dependence on a giant-virus factory is established at the experimental system level. Exact helper-isolate equivalence to a particular RefSeq genome accession is not asserted.
- **Source/terms disposition:** NCBI RefSeq, exact accession.version `NC_011132.1`; future sequence retrieval is external by exact accession through NCBI E-utilities or NCBI Datasets. Cite the RefSeq record and PMID 18690211; no record-specific sequence license or attribution notice was established by the metadata query. Repository treatment is accession/provenance/retrieval-manifest only; Class B; the sequence remains externally retrieved. Verify record/source terms before any materialized snapshot or redistribution.
- **Remaining caveat:** the RefSeq-to-publication association is confirmed, while sequence equivalence or synonymy with the paper’s EU606015.1 accession was not tested because no sequence was retrieved. Keep both accessions distinct and do not assert identity.
- **Verified source study:** `PMID:18690211`.

### 8. `KU052222.1` — Cafeteriavirus-dependent mavirus

- **Panel role:** `related_non_satellite` / `virophage_and_proviral_context`.
- **Curation state:** `APPROVED_CONTEXT_REFERENCE`.
- **Initial-panel inclusion:** **yes**, specifically as a proviral-context record, not a free-virus genome.
- **Evidence basis:** NCBI/INSDC ESummary identifies a 40,196-nt linear DNA record, TaxID 1932923, strain E4-10M1; the NCBI record summary describes the genome class as proviral. The accession-linked primary paper, PMID 27929021, is titled “Host genome integration and giant virus-induced reactivation of the virophage mavirus.” The earlier Mavirus experimental-system paper (DOI 10.1126/science.1199412) supports virophage biology but is not substituted for the exact accession-linked study.
- **Helper-evidence scope:** CroV-dependent reproduction/reactivation is supported for Mavirus experimental systems. The record remains explicitly proviral; it is not evidence that this accession is a free-virus isolate.
- **Source/terms disposition:** INSDC/GenBank record, exact accession.version `KU052222.1`; future sequence retrieval is external by exact accession through NCBI E-utilities or an INSDC provider API. Cite the accession record and PMID 27929021; no record-specific sequence license or attribution notice was established by the metadata query. Repository treatment is accession/provenance/retrieval-manifest only; Class B; the sequence remains externally retrieved. Verify record/source terms before any materialized snapshot or redistribution.
- **Remaining caveat:** preserve the proviral qualifier and do not treat the sequence as a propagated, non-integrated Mavirus reference.
- **Verified source study:** `PMID:27929021`.

### 9. `KJ683044.1` — Adoxophyes honmai entomopoxvirus “L” virophage 1

- **Panel role:** `related_non_satellite` / `polinton_like_virus_context`.
- **Curation state:** `APPROVED_CONTEXT_REFERENCE`.
- **Initial-panel inclusion:** **yes**, as Polinton-like/entomopoxvirus-associated context only.
- **Evidence basis:** NCBI/INSDC ESummary and Taxonomy identify an 11,449-nt circular DNA record, complete, TaxID 1612310, with the record title “virophage.” The 2024 primary paper “Genomic analysis of hyperparasitic viruses associated with entomopoxviruses” directly lists accession KJ683044 as AHEV_PLV1 and analyzes it as a Polinton-like virus (PMID 39100687). This resolves the record-to-study mapping and supports a Polinton-like contextual subrole without overwriting the source title.
- **Helper-evidence scope:** the primary paper describes association with entomopoxvirus occlusion bodies; this supports an entomopoxvirus-associated context, not an exact helper-accession pairing or a fully resolved replication-dependence claim for this record.
- **Source/terms disposition:** INSDC/GenBank record, exact accession.version `KJ683044.1`; future sequence retrieval is external by exact accession through NCBI E-utilities or an INSDC provider API. Cite the accession record and PMID 39100687; no record-specific sequence license or attribution notice was established by the metadata query. Repository treatment is accession/provenance/retrieval-manifest only; Class B; the sequence remains externally retrieved. Verify record/source terms before any materialized snapshot or redistribution.
- **Remaining caveat:** preserve both the NCBI “virophage” record title and later PLV study interpretation. It is not promoted to `satellite_subviral`; no candidate inherits this record’s role.
- **Verified source study:** `PMID:39100687`.

### 10. `NC_002598.1` — Panicum mosaic virus helper context

- **Panel role:** `virus_helper` / `documented_helper_context`.
- **Curation state:** `APPROVED_CONTEXT_REFERENCE`.
- **Initial-panel inclusion:** **yes**, as a separate helper-virus context record.
- **Evidence basis:** NCBI RefSeq ESummary and Taxonomy identify a 4,326-nt single-stranded RNA, linear and complete, TaxID 40279. The RefSeq record identifies strain Kansas. Its accession-linked full-length cDNA/infectivity paper is PMID 9454725; SPMV helper evidence is supported separately by PMIDs 16014937 and 31455653.
- **Helper-evidence scope:** PMV is a documented helper for SPMV, but neither this accession nor its Kansas strain is asserted to be the exact helper isolate in every SPMV experiment.
- **Source/terms disposition:** NCBI RefSeq, exact accession.version `NC_002598.1`; future sequence retrieval is external by exact accession through NCBI E-utilities or NCBI Datasets. Cite the NCBI record and PMID 9454725; no record-specific sequence license or attribution notice was established by the metadata query. Repository treatment is accession/provenance/retrieval-manifest only; Class B; the sequence remains externally retrieved. Verify record/source terms before any materialized snapshot or redistribution.
- **Remaining caveat:** helper role is context, not an assignment to a future candidate or proof of the exact experimental pairing.
- **Verified source study:** `PMID:9454725`.

### 11. `NC_002034.1` — Cucumber mosaic virus RNA 1

- **Panel role:** `virus_helper` / `segmented_helper_genome`.
- **Curation state:** `APPROVED_CONTEXT_REFERENCE`.
- **Initial-panel inclusion:** **yes**, as CMV helper segment RNA 1.
- **Evidence basis:** NCBI RefSeq ESummary identifies a 3,357-nt single-stranded RNA, linear and complete as a segment; TaxID 12305, strain Fny, segment RNA 1. The accession-linked primary sequence paper is PMID 2732682.
- **Helper-evidence scope:** this is one of three CMV segments in system-level CMV satellite-RNA helper context. Its Fny strain metadata does not establish that it is the exact isolate paired with `NC_002602.2`.
- **Source/terms disposition:** NCBI RefSeq, exact accession.version `NC_002034.1`; future sequence retrieval is external by exact accession through NCBI E-utilities or NCBI Datasets. Cite the NCBI record and PMID 2732682; no record-specific sequence license or attribution notice was established by the metadata query. Repository treatment is accession/provenance/retrieval-manifest only; Class B; the sequence remains externally retrieved. Verify record/source terms before any materialized snapshot or redistribution.
- **Remaining caveat:** keep RNA 1 individually identified; do not merge it with RNA 2 or RNA 3 or infer isolate pairing.
- **Verified source study:** `PMID:2732682`.

### 12. `NC_002035.1` — Cucumber mosaic virus RNA 2

- **Panel role:** `virus_helper` / `segmented_helper_genome`.
- **Curation state:** `APPROVED_CONTEXT_REFERENCE`.
- **Initial-panel inclusion:** **yes**, as CMV helper segment RNA 2.
- **Evidence basis:** NCBI RefSeq ESummary identifies a 3,050-nt single-stranded RNA, linear and complete as a segment; TaxID 12305, strain Fny, segment RNA 2. The accession-linked primary sequence paper is PMID 3404113.
- **Helper-evidence scope:** this is one of three CMV segments in system-level CMV satellite-RNA helper context. Its Fny strain metadata does not establish that it is the exact isolate paired with `NC_002602.2`.
- **Source/terms disposition:** NCBI RefSeq, exact accession.version `NC_002035.1`; future sequence retrieval is external by exact accession through NCBI E-utilities or NCBI Datasets. Cite the NCBI record and PMID 3404113; no record-specific sequence license or attribution notice was established by the metadata query. Repository treatment is accession/provenance/retrieval-manifest only; Class B; the sequence remains externally retrieved. Verify record/source terms before any materialized snapshot or redistribution.
- **Remaining caveat:** keep RNA 2 individually identified; do not merge it with RNA 1 or RNA 3 or infer isolate pairing.
- **Verified source study:** `PMID:3404113`.

### 13. `NC_001440.1` — Cucumber mosaic virus RNA 3

- **Panel role:** `virus_helper` / `segmented_helper_genome`.
- **Curation state:** `APPROVED_CONTEXT_REFERENCE`.
- **Initial-panel inclusion:** **yes**, as CMV helper segment RNA 3.
- **Evidence basis:** NCBI RefSeq ESummary identifies a 2,216-nt single-stranded RNA, linear and complete as a segment; TaxID 12305, strain Fny, segment RNA 3. The accession-linked primary sequence paper is PMID 2230731.
- **Helper-evidence scope:** this is one of three CMV segments in system-level CMV satellite-RNA helper context. Its Fny strain metadata does not establish that it is the exact isolate paired with `NC_002602.2`.
- **Source/terms disposition:** NCBI RefSeq, exact accession.version `NC_001440.1`; future sequence retrieval is external by exact accession through NCBI E-utilities or NCBI Datasets. Cite the NCBI record and PMID 2230731; no record-specific sequence license or attribution notice was established by the metadata query. Repository treatment is accession/provenance/retrieval-manifest only; Class B; the sequence remains externally retrieved. Verify record/source terms before any materialized snapshot or redistribution.
- **Remaining caveat:** keep RNA 3 individually identified; do not merge it with RNA 1 or RNA 2 or infer isolate pairing.
- **Verified source study:** `PMID:2230731`.

### 14. `NC_003977.2` — Hepatitis B virus, strain ayw

- **Panel role:** `virus_helper` / `documented_helper_context`.
- **Curation state:** `APPROVED_CONTEXT_REFERENCE`.
- **Initial-panel inclusion:** **yes**, as a separate HBV helper-context record.
- **Evidence basis:** NCBI RefSeq ESummary identifies a 3,182-nt circular DNA genome, strain ayw, TaxID 10407, complete. The accession-linked original genome paper is PMID 399327. ICTV’s Deltavirus report supports the HDV/HBV particle/envelopment context.
- **Helper-evidence scope:** HBV surface antigen supports HDV envelopment and transmission, not HDV RNA replication. Strain ayw is not asserted to be the exact strain paired with `NC_001653.2`.
- **Source/terms disposition:** NCBI RefSeq, exact accession.version `NC_003977.2`; future sequence retrieval is external by exact accession through NCBI E-utilities or NCBI Datasets. Cite the NCBI record and PMID 399327; no record-specific sequence license or attribution notice was established by the metadata query. Repository treatment is accession/provenance/retrieval-manifest only; Class B; the sequence remains externally retrieved. Verify record/source terms before any materialized snapshot or redistribution.
- **Remaining caveat:** retain as an HBV contextual record; do not imply that it supports HDV RNA replication or is the matched isolate.
- **Verified source study:** `PMID:399327`.

## Study provenance normalization

The IDs below are the verified `source_study_ids` for the catalogue entries. The exact accession-to-PubMed associations were checked via NCBI `nuccore_pubmed`; PubMed titles were checked via PubMed ESummary. General helper/system papers remain in `supporting_sources` and are not substituted for sequence-provenance IDs.

| Accession.version | `source_study_ids` |
| --- | --- |
| NC_002602.2 | `PMID:18627882` |
| NC_003847.1 | `PMID:18644571` |
| V01468.1 | `PMID:6260960`, `PMID:427118` |
| AJ298903.1 | `PMID:11437658` |
| NC_001653.2 | `PMID:3627276`, `PMID:2374010` |
| NC_002030.1 | `PMID:643081` |
| NC_011132.1 | `PMID:18690211` |
| KU052222.1 | `PMID:27929021` |
| KJ683044.1 | `PMID:39100687` |
| NC_002598.1 | `PMID:9454725` |
| NC_002034.1 | `PMID:2732682` |
| NC_002035.1 | `PMID:3404113` |
| NC_001440.1 | `PMID:2230731` |
| NC_003977.2 | `PMID:399327` |

The linked PMID 472709 for PSTVd is a review and is not used as a source-study ID. PMIDs 16014937 and 31455653 support the SPMV/PMV helper system; PMID 17342261 supports the CMV satellite-RNA system; PMID 14551819 supports the betasatellite system; PMID 2430299 and ICTV material support HDV interpretation. These are evidence citations, not accession provenance substitutes.

## Source terms and retrieval disposition

All 14 approved records are from NCBI RefSeq or INSDC/GenBank and have redistribution class **B** under the project's reference-panel policy. “Public record” is not treated as redistribution permission.

- **Authoritative provider and version:** the provider is recorded individually above as NCBI RefSeq or INSDC/GenBank; the accession.version is the exact lookup key.
- **Retrieval model:** future sequence acquisition is external and accession.version-pinned, through NCBI E-utilities/NCBI Datasets for NCBI records or an INSDC provider API (including NCBI/ENA) for GenBank records. This review fetched metadata summaries only; no sequence was fetched.
- **Attribution:** retain the accession record, provider, retrieval provenance, and the verified source-study citation(s) listed above. The metadata and policy pages checked here do not establish an additional record-specific sequence attribution/license condition for any entry.
- **Repository treatment:** store accession.version, provider/source URL, retrieval recipe, retrieval timestamp, file/manifest hashes, and provenance only. Do not commit sequence payloads as part of this review.
- **Sequence location:** sequences remain externally retrieved when a future approved snapshot is built; these approvals do not authorize rehosting.
- **Unresolved rights/terms:** record-level submitter/publication terms and any source-specific exception were not individually adjudicated. Recheck the precise record and source terms before materialized sequence snapshots or redistribution. The project's Class B manifest-only default remains in force.

## Catalogue alignment and limits

- The catalogue retains four `satellite_subviral` roles, five distinct related/context roles, and five helper records. The three CMV RNAs remain separate complete segments; they are not merged.
- Helper relationships are labelled at the system or group level unless an exact accession/isolate pairing is supported. No such exact pairing is inferred for CMV satellite RNA, SPMV, STNV, the betasatellite, Sputnik, HDV/HBV, or Mavirus.
- `NC_011132.1` is retained as the RefSeq Sputnik context record while EU606015.1 remains the accession cited by the original paper; their sequence equivalence was not checked.
- `KU052222.1` remains explicitly proviral. `KJ683044.1` retains the NCBI “virophage” record title and the later PLV interpretation as separately attributed labels.
- `NC_001653.2` remains deltavirus context; HBV evidence concerns envelopment/transmission, not HDV RNA replication. `NC_002030.1` remains viroid context, not a satellite.
- No sequence hashes, sequence comparisons, taxonomy release snapshot, benchmark holdouts, BLASTN results, or M8 implementation were created. The approvals are not future-candidate classifications and do not claim panel completeness.

## Validation performed

- Confirmed 14 unique accession.version records, one curation state per record, 4 `APPROVED_INITIAL_REFERENCE`, 10 `APPROVED_CONTEXT_REFERENCE`, and explicit inclusion `yes` for all 14.
- Confirmed all 14 roles remain separate and `source_study_ids` are normalized to verified PMID identifiers. No record has an invented study ID.
- Confirmed JSON parses; record counts, states, roles, inclusion values, and study identifiers agree between the JSON, catalogue Markdown, and this review.
- Confirmed the JSON contains no sequence payloads and no sequence hashes were computed.
- No M8 implementation, BLASTN installation/run, sequence/database retrieval, M9 work, M1–M7 change, M16 holdout assignment, or automatic merge was performed.

M8 initial reference curator review: READY FOR REVIEW