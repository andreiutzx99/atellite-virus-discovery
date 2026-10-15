import gzip
import json
import random
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from satellite_discovery import coverage_review
from satellite_discovery.quality_control import run_qc

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "hcov229e-reference-panel-v1.json"


class ReferencePanelManifestTests(unittest.TestCase):
    def test_manifest_is_scoped_versioned_and_non_authorizing(self):
        panel = json.loads(MANIFEST.read_text(encoding="utf-8"))
        scope = panel["scope"]
        self.assertEqual(scope["sra_run"], "SRR12424250")
        self.assertEqual(scope["scientific_status"], "HELD")
        self.assertEqual(scope["sequence_confirmation"], "NOT_ASSESSED")
        self.assertEqual(panel["panel_status"], "proposed_metadata_only_not_downloaded")
        self.assertEqual(len(panel["categories"][0]["primary_chromosomes"]), 25)
        self.assertTrue(all(len(accession.split(".")) == 2 for accession, _ in panel["categories"][0]["primary_chromosomes"]))
        hcov = panel["categories"][1]["records"]
        self.assertEqual(hcov[0]["accession"], "NC_002645.1")
        self.assertEqual(hcov[0]["length_bp"], 27317)
        self.assertEqual(hcov[1]["accession"], "MF542265.1")
        self.assertEqual(hcov[1]["length_bp"], 27271)
        self.assertTrue(all(record.get("sha256") is None for category in panel["categories"] for record in category["records"]))
        self.assertTrue(any("not evidence of novelty" in rule for rule in panel["interpretation_rules"]))


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
