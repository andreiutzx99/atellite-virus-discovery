import gzip
import json
import random
import re
import shutil
import subprocess
import tempfile
import unittest
from urllib.parse import urlparse
from pathlib import Path

from satellite_discovery import coverage_review
from satellite_discovery.quality_control import run_qc

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "hcov229e-reference-panel-v1.json"


class ReferencePanelManifestTests(unittest.TestCase):
    @staticmethod
    def _validate(panel):
        def require(condition, message):
            if not condition:
                raise ValueError(message)

        require(panel.get("schema") == "hcov229e-reference-panel-v1", "unexpected manifest schema")
        scope = panel["scope"]
        require(scope == {
            "geo": "GSE155986",
            "bioproject": "PRJNA656274",
            "sra_study": "SRP276927",
            "sra_run": "SRR12424250",
            "biosample": "SAMN15776099",
            "sequence_confirmation": "NOT_ASSESSED",
            "scientific_status": "HELD",
        }, "scope or protected scientific statuses changed")
        require(panel.get("panel_status") == "proposed_metadata_only_not_downloaded",
                "panel is not metadata-only")
        require(panel.get("reference_activation_status") == "NOT_ACTIVATED",
                "references must remain inactive")
        categories = panel.get("categories")
        require(isinstance(categories, list) and categories, "categories are required")
        record_ids = []
        for category in categories:
            require(isinstance(category.get("records"), list), "category records must be a list")
            for record in category["records"]:
                record_id = record.get("id")
                require(isinstance(record_id, str) and record_id.strip(), "record ID is required")
                record_ids.append(record_id)
                require("sha256" in record and record["sha256"] is None,
                        f"{record_id}: sequence checksum must be explicitly null")
                require(not any(k in record for k in ("sequence", "sequence_data", "fasta")),
                        f"{record_id}: sequence payload is not allowed")
                if "documented_adapter_sequence" in record:
                    require(record_id == "illumina-adapter-core" and
                            isinstance(record["documented_adapter_sequence"], str) and
                            re.fullmatch(r"[ACGTN]+", record["documented_adapter_sequence"]) is not None and
                            len(record["documented_adapter_sequence"]) == record.get("length_bp"),
                            "only the documented adapter metadata sequence may be embedded")
                length = record.get("length_bp")
                require(length is None or (type(length) is int and length > 0),
                        f"{record_id}: length must be a positive integer or null")
                source_url = record.get("source_url")
                parsed_url = urlparse(source_url) if isinstance(source_url, str) else None
                require(parsed_url is not None and parsed_url.scheme == "https" and parsed_url.netloc,
                        f"{record_id}: valid HTTPS source_url is required")
                for key, value in record.items():
                    if key.endswith("_url"):
                        parsed = urlparse(value) if isinstance(value, str) else None
                        require(parsed is not None and parsed.scheme == "https" and parsed.netloc,
                                f"{record_id}: {key} must be a valid HTTPS URL")
                if "active" in record:
                    require(record["active"] is False, f"{record_id}: active reference contradicts metadata-only state")
                if "activation_status" in record:
                    require(record["activation_status"] == "NOT_ACTIVATED",
                            f"{record_id}: reference is prematurely activated")
                accession = record.get("accession")
                if accession is not None and accession != "UniVec_Core":
                    require(isinstance(accession, str) and
                            re.fullmatch(r"[A-Z]{1,6}_?\d+\.\d+", accession) is not None,
                            f"{record_id}: accession must be accession.version where applicable")
                    if accession.startswith(("NC_", "MF")):
                        require(record.get("version") == accession.rsplit(".", 1)[1],
                                f"{record_id}: version disagrees with accession.version")
                elif accession == "UniVec_Core":
                    require(record.get("status") == "candidate_not_selected_pending_build_snapshot",
                            "unversioned UniVec must remain an unselected candidate")
        require(len(record_ids) == len(set(record_ids)), "record IDs must be unique")
        chromosome_records = categories[0].get("primary_chromosomes")
        require(isinstance(chromosome_records, list) and len(chromosome_records) == 25,
                "expected 25 host primary chromosome records")
        for accession, length in chromosome_records:
            require(isinstance(accession, str) and
                    re.fullmatch(r"[A-Z]{1,6}_?\d+\.\d+", accession) is not None,
                    "chromosome accession must be accession.version")
            require(type(length) is int and length > 0, "chromosome lengths must be positive integers")
        unresolved = next((r for c in categories for r in c["records"] if r["id"] == "human-rrna"), None)
        require(unresolved is not None and unresolved.get("resolution_status") == "unresolved",
                "unresolved nuclear rRNA reference must remain explicitly unresolved")
        require("not pinned" in unresolved.get("limitation", ""),
                "unresolved rRNA limitation must be documented")
        require(all(r.get("sha256") is None for c in categories for r in c["records"]),
                "sequence checksums must remain null before retrieval")
        require(any("not evidence of novelty" in rule for rule in panel.get("interpretation_rules", [])),
                "interpretation boundary is missing")

    def test_manifest_is_scoped_versioned_and_non_authorizing(self):
        panel = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self._validate(panel)
        hcov = panel["categories"][1]["records"]
        self.assertEqual(hcov[0]["accession"], "NC_002645.1")
        self.assertEqual(hcov[0]["length_bp"], 27317)
        self.assertEqual(hcov[1]["accession"], "MF542265.1")
        self.assertEqual(hcov[1]["length_bp"], 27271)

    def test_manifest_validator_rejects_contradictions_and_premature_activation(self):
        panel = json.loads(MANIFEST.read_text(encoding="utf-8"))
        mutations = (
            lambda value: value["categories"][1]["records"][1].update(id=value["categories"][1]["records"][0]["id"]),
            lambda value: value["categories"][1]["records"][0].update(accession="NC_002645"),
            lambda value: value["categories"][1]["records"][0].update(version="2"),
            lambda value: value["categories"][1]["records"][0].update(source_url="ftp://example.invalid/record"),
            lambda value: value["categories"][1]["records"][0].update(length_bp=0),
            lambda value: value["categories"][1]["records"][0].pop("sha256"),
            lambda value: value["categories"][1]["records"][0].update(sequence_data="ACGT"),
            lambda value: value.update(panel_status="downloaded"),
            lambda value: value.update(reference_activation_status="ACTIVE"),
            lambda value: value["categories"][1]["records"][0].update(active=True),
            lambda value: value["categories"][1]["records"][0].update(activation_status="ACTIVE"),
            lambda value: value["categories"][1]["records"][0].update(sha256="a" * 64),
            lambda value: value["categories"][0]["records"][3].update(resolution_status="resolved"),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                candidate = json.loads(json.dumps(panel))
                mutate(candidate)
                with self.assertRaises(ValueError):
                    self._validate(candidate)


@unittest.skipUnless(shutil.which("minimap2"), "minimap2 is required for synthetic mapping validation")
class SyntheticReferenceValidationTests(unittest.TestCase):
    @staticmethod
    def _seq(seed, size):
        rng = random.Random(seed)
        return "".join(rng.choice("ACGT") for _ in range(size))

    def test_ambiguous_unmapped_mismatch_contaminant_and_junction_fixtures(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            viral = self._seq(7101, 900)
            contaminant = self._seq(7102, 600)
            sgrna_like = viral[30:65] + viral[610:650]
            dvg_like = viral[180:218] + viral[740:777]
            refs = {
                "synthetic_virus": viral,
                "synthetic_virus_duplicate": viral,
                "synthetic_contaminant_like": contaminant,
                "synthetic_sgrna_like_transcript": sgrna_like,
                "synthetic_dvg_like_transcript": dvg_like,
            }
            fasta = root / "refs.fa"
            fasta.write_text("".join(f">{name}\n{seq}\n" for name, seq in refs.items()), encoding="ascii")
            mismatch = list(viral[300:380])
            mismatch[35] = "A" if mismatch[35] != "A" else "C"
            reads = [
                ("exact", viral[100:180]),
                ("ambiguous", viral[500:580]),
                ("mismatch", "".join(mismatch)),
                ("unmapped", self._seq(7199, 80)),
                ("contaminant_like", contaminant[100:180]),
                ("sgrna_like", sgrna_like),
                ("dvg_like", dvg_like),
            ]
            fastq = root / "reads.fq"
            fastq.write_text("".join(f"@{n}\n{s}\n+\n{'I' * len(s)}\n" for n, s in reads), encoding="ascii")
            run = subprocess.run(
                [shutil.which("minimap2"), "-a", "-x", "sr", "-N", "10", str(fasta), str(fastq)],
                capture_output=True, text=True, timeout=60, check=True,
            )
            sam = root / "synthetic.sam"
            sam.write_text(run.stdout, encoding="utf-8")
            records = {}
            for line in run.stdout.splitlines():
                if line and not line.startswith("@"):
                    f = line.split("\t")
                    records.setdefault(f[0], []).append(f)
            self.assertTrue(any(int(f[1]) & 4 for f in records["unmapped"]))
            self.assertTrue(any(int(f[1]) & 256 or int(f[4]) == 0 for f in records["ambiguous"]))
            self.assertTrue(any(any(tag.startswith("NM:i:") and int(tag[5:]) >= 1 for tag in f[11:]) for f in records["mismatch"]))
            for name, target in (("contaminant_like", "synthetic_contaminant_like"),
                                 ("sgrna_like", "synthetic_sgrna_like_transcript"),
                                 ("dvg_like", "synthetic_dvg_like_transcript")):
                self.assertTrue(any(f[2] == target and not int(f[1]) & (4 | 256 | 2048) for f in records[name]))
            refs_out, blocks, _ = coverage_review.read_sam(sam)
            coverage = coverage_review.calculate(
                refs_out, [{"sample_id": "synthetic"}],
                [dict(block, sample_id="synthetic") for block in blocks],
            )
            self.assertTrue(any(row["reference_id"] == "synthetic_virus" and row["covered_bases"] > 0 for row in coverage))
            self.assertTrue(all(name.startswith("synthetic") for name in refs))

    def test_quality_filtering_accounts_for_original_and_rejected_reads(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fastq = root / "reads.fastq.gz"
            good, bad = self._seq(7201, 75), self._seq(7202, 75)
            with gzip.open(fastq, "wt", encoding="ascii") as out:
                out.write(f"@good\n{good}\n+\n{'I' * len(good)}\n")
                out.write(f"@low_quality\n{bad}\n+\n{'!' * len(bad)}\n")
            report = run_qc({"single": fastq}, root / "qc", progress=lambda _msg: None)
            self.assertEqual(report["before"]["reads"], 2)
            self.assertEqual(report["after"]["reads"], 1)
            self.assertEqual(report["counts"]["rejected_reads"], 1)
            self.assertEqual(report["rejection_reasons"], {"too_short_after_trimming": 1})
            self.assertEqual(report["counts"]["retained_single_reads"], 1)


if __name__ == "__main__":
    unittest.main()
