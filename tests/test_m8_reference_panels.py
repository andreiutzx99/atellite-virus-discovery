import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from satellite_discovery.m8_reference_panels import (
    validate_external_snapshot_files,
    validate_snapshot_manifest,
)


def digest(value):
    return hashlib.sha256(value).hexdigest()


class ReferencePanelTests(unittest.TestCase):
    def make_fixture(self, root):
        root = Path(root)
        fasta = b">ACC001.1 synthetic one\nACGTU\n>ACC002.3\nNNac\n"
        fasta_path = root / "panel.fasta"
        fasta_path.write_bytes(fasta)
        indexes = {}
        suffixes = (".ndb", ".nhr", ".nin", ".not", ".nsq", ".ntf", ".nto")
        for suffix in suffixes:
            content = ("index-" + suffix).encode()
            path = root / ("synthetic" + suffix)
            path.write_bytes(content)
            indexes[path.name] = path
        manifest = {
            "schema": "m8-reference-snapshot-manifest-v1",
            "snapshot_id": "synthetic-v1",
            "retrieved_utc": "2026-01-01T00:00:00Z",
            "status": "EXTERNAL_ONLY",
            "provider": "synthetic-fixture",
            "database": "synthetic",
            "request_endpoint": "fixture://local",
            "retrieval_method": "fixed literal",
            "normalization": "uppercase ASCII; preserve T/U",
            "taxonomy_provenance": "fixture metadata only",
            "rights": {
                "redistribution_class": "C",
                "provider_policy_urls": ["https://example.invalid/terms"],
                "record_scan": "synthetic",
                "analysis_disposition": "external fixture only",
                "redistribution_disposition": "NOT_APPROVED",
                "publication_supplements": "none",
            },
            "payload_storage": "outside repository",
            "panel_fasta": {
                "external_filename": "panel.fasta",
                "sha256": digest(fasta),
                "size_bytes": len(fasta),
                "record_count": 2,
                "total_bases": 9,
            },
            "blast_toolchain": {
                "release": "synthetic",
                "archive_url": "fixture://tool",
                "archive_md5_from_ncbi_sidecar": "fixture",
                "archive_sha256_recomputed_from_fresh_download": "fixture",
                "blastn_sha256": "fixture",
                "makeblastdb_sha256": "fixture",
                "makeblastdb_command": "makeblastdb fixture",
                "index_validation": (
                    "blastdbcmd -info reported 2 sequences; blastdbcmd -entry all "
                    "returned the same 2 accession.version IDs listed below"
                ),
                "database_search_performed": False,
                "index_files_external": [
                    {"filename": name, "sha256": digest(path.read_bytes()),
                     "size_bytes": path.stat().st_size}
                    for name, path in sorted(indexes.items())
                ],
            },
            "records": [
                {
                    "accession_version": "ACC001.1", "role": "satellite_subviral",
                    "subrole": "satellite_rna", "curation_state": "REVIEWED",
                    "source_study_ids": ["fixture-1"], "taxid": 0,
                    "source_organism": None, "length": 5,
                    "sequence_sha256": digest(b"ACGTU"),
                    "source_response_sha256": digest(b"response-1"),
                },
                {
                    "accession_version": "ACC002.3", "role": "virus_helper",
                    "subrole": "other_virus", "curation_state": "REVIEWED",
                    "source_study_ids": ["fixture-2"], "taxid": 0,
                    "source_organism": None, "length": 4,
                    "sequence_sha256": digest(b"NNAC"),
                    "source_response_sha256": digest(b"response-2"),
                },
            ],
            "snapshot_digest_algorithm": "SHA-256 canonical JSON excluding snapshot digest fields",
        }
        material = {
            key: value for key, value in manifest.items()
            if key not in {"snapshot_digest", "snapshot_digest_algorithm"}
        }
        manifest["snapshot_digest"] = digest(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        )
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest_path, fasta_path, indexes, manifest

    def test_valid_metadata_and_external_payloads(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest, fasta, indexes, _ = self.make_fixture(folder)
            metadata = validate_snapshot_manifest(manifest)
            self.assertEqual(metadata["snapshot_id"], "synthetic-v1")
            self.assertEqual(metadata["roles"], ["satellite_subviral", "virus_helper"])
            result = validate_external_snapshot_files(
                manifest, {"panel.fasta": fasta, **indexes}
            )
            self.assertEqual(result["panel_fasta"]["record_count"], 2)
            self.assertEqual(result["references"][0]["accession_version"], "ACC001.1")

    def test_manifest_digest_and_role_or_duplicate_accession_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest, _fasta, _indexes, document = self.make_fixture(folder)
            document["snapshot_id"] = "changed"
            manifest.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "canonical digest"):
                validate_snapshot_manifest(manifest)
        for mutation, message in (
            (lambda d: d["records"][0].update({"subrole": "other_virus"}), "Invalid role"),
            (lambda d: d["records"][1].update({"accession_version": "ACC001.1"}), "Duplicate"),
        ):
            with tempfile.TemporaryDirectory() as folder:
                manifest, _fasta, _indexes, document = self.make_fixture(folder)
                mutation(document)
                material = {k: v for k, v in document.items()
                            if k not in {"snapshot_digest", "snapshot_digest_algorithm"}}
                document["snapshot_digest"] = digest(
                    json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
                )
                manifest.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    validate_snapshot_manifest(manifest)

    def test_corrupt_fasta_and_index_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest, fasta, indexes, _ = self.make_fixture(folder)
            fasta.write_bytes(fasta.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "FASTA hash"):
                validate_external_snapshot_files(manifest, {"panel.fasta": fasta, **indexes})
            manifest, fasta, indexes, _ = self.make_fixture(folder)
            indexes["synthetic.nsq"].write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "index mismatch"):
                validate_external_snapshot_files(manifest, {"panel.fasta": fasta, **indexes})

    def test_missing_extra_and_symlink_payloads_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest, fasta, indexes, _ = self.make_fixture(folder)
            payloads = {"panel.fasta": fasta, **indexes}
            payloads.pop("synthetic.nhr")
            with self.assertRaisesRegex(ValueError, "mapping mismatch"):
                validate_external_snapshot_files(manifest, payloads)
            extra = Path(folder) / "extra"
            extra.write_bytes(b"x")
            payloads = {"panel.fasta": fasta, **indexes, "extra": extra}
            with self.assertRaisesRegex(ValueError, "mapping mismatch"):
                validate_external_snapshot_files(manifest, payloads)
            link = Path(folder) / "link.nsq"
            link.symlink_to(indexes["synthetic.nto"])
            symlink_payloads = {"panel.fasta": fasta, **indexes}
            symlink_payloads["synthetic.nto"] = link
            with self.assertRaises(ValueError):
                validate_external_snapshot_files(manifest, symlink_payloads)

    def test_incomplete_core_blastdb_suffix_set_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest, _fasta, indexes, document = self.make_fixture(folder)
            document["blast_toolchain"]["index_files_external"] = [
                row for row in document["blast_toolchain"]["index_files_external"]
                if not row["filename"].endswith(".nto")
            ]
            material = {k: v for k, v in document.items()
                        if k not in {"snapshot_digest", "snapshot_digest_algorithm"}}
            document["snapshot_digest"] = digest(
                json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
            )
            manifest.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "core suffixes"):
                validate_snapshot_manifest(manifest)

    def test_approved_manifest_metadata_digest_and_roles(self):
        manifest = Path(__file__).parents[1] / "docs" / "M8_REFERENCE_SNAPSHOT_MANIFEST.json"
        result = validate_snapshot_manifest(manifest)
        self.assertEqual(result["snapshot_id"], "m8-class-b-b3ce1c2a410a4ee05ded")
        self.assertEqual(len(result["references"]), 14)
        self.assertEqual(
            result["roles"],
            ["related_non_satellite", "satellite_subviral", "virus_helper"],
        )


if __name__ == "__main__":
    unittest.main()