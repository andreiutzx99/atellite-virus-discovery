# Supplied-sequence catalogue and composition report

This stage imports an existing nucleotide FASTA into a local SQLite catalogue and exports a normalized FASTA plus descriptive HTML/CSV. It does not assemble reads, identify ORFs, predict function, search a reference database or classify biological identity.

## Run the artificial example

```console
python -m satellite_discovery.sequence_catalogue --fasta examples/inventory/artificial.fasta --output runs/inventory-example
```

Open `runs/inventory-example/report.html`. Repeating the command verifies and reuses the completed outputs. For other supplied FASTA files, double-click `Inventory-sequences.cmd` and enter the full FASTA path and output folder. No new sequencing download is required.

## Data handling

FASTA records require unique identifiers and nonempty nucleotide sequences. Upper/lowercase and whitespace are normalized; IUPAC ambiguity symbols and U are retained. Gaps and non-nucleotide symbols are rejected. The importer has limits of 100 MB input, 20 million nucleotide symbols and 10,000 records to bound memory use. It preserves all supplied records and does not apply biological rejection thresholds.

Measurements include length, GC fraction over unambiguous A/C/G/T/U symbols, ambiguity fraction, and single-symbol Shannon entropy over those unambiguous symbols. All-ambiguous records have unknown GC and entropy. Entropy is a composition statistic, not evidence that a sequence is a technical artefact. Both T and U in a record produce a warning.

Exact uppercase sequence identity defines duplicate groups. Reverse complements and T/U substitutions remain distinct. Group IDs are full SHA256 sequence hashes. This is exact deduplication, not similarity clustering or evidence of shared evolutionary origin. No consensus sequence is constructed.

`catalogue.sqlite` stores one sequence per exact group plus every original record ID/header and its measurements. `sequences.fasta` contains every normalized record in original order, including duplicates, wrapped at 80 characters. The exported records are round-trip tested against the normalized input. The input file is never changed.

## Reproducibility and recovery

The manifest records the source path, input/implementation checksums, timestamps and checksums for every exported artifact. Changed input or code requires a new output folder. Modified completed outputs cause an integrity error without being overwritten.

Ordinary failed attempts can be rerun with the same inputs: the catalogue database is replaced atomically instead of appending duplicate rows. A lock excludes concurrent writers. After a forced termination, confirm no inventory process is running before removing only `.catalogue.lock` from that output folder, then repeat the command. This small stage recomputes an interrupted inventory and does not repeat any earlier pipeline stage.

This is a per-import catalogue snapshot. Cross-import merging, approximate clustering, coverage/ORF measurements and biological interpretation are not implemented here.
