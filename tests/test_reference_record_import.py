import csv
import hashlib
import json
import unittest
from pathlib import Path

from test_metadata import scratch_directory
from satellite_discovery import artifact_workflow, reference_snapshot
from satellite_discovery.reference_record_import import (
    compare_record_snapshots, import_from_snapshot, lookup_records,
    verified_record_snapshot,
)


def make_parent(root, label, members, *, reference_ids=None):
    source_dir = Path(root) / ("source-" + label)
    source_dir.mkdir()
    entries = []
    for index, (name, content) in enumerate(members.items()):
        source = source_dir / name
        source.write_text(content, encoding="utf-8")
        entries.append({
            "name": name,
            "path": f"{source_dir.name}/{name}",
            "bytes": source.stat().st_size,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "source": "NCBI RefSeq",
            "version": "release-2025-01",
            "role": "viral-reference",
            "accession": "NC_000001.1",
            "database_version": "archive-2025",
            "reference_id": (reference_ids or {}).get(name, "ref-" + str(index)),
            "display_name": "Supplied " + name,
            "category": "virus",
            "provenance": "provided with the reference specification",
        })
    specification = Path(root) / ("spec-" + label + ".json")
    specification.write_text(json.dumps({"files": entries}), encoding="utf-8")
    output = Path(root) / ("parent-" + label)
    reference_snapshot.snapshot(specification, output)
    return output


class ReferenceRecordImportTests(unittest.TestCase):
    def test_import_preserves_records_provenance_and_supports_all_lookups(self):
        with scratch_directory() as root:
            parent = make_parent(root, "first", {
                "alpha.fa": (
                    ">NC_123456.2 alpha isolate\nACGTACGT\n"
                    ">common same identifier\nTTTTCCCC\n"
                    ">same_a exact duplicate sequence\nGGAAGGAA\n"
                ),
                "beta.fa": (
                    ">NC_123456.3 beta isolate\nACGTACGT\n"
                    ">common conflicting sequence\nTTTTGGGG\n"
                    ">same_b exact duplicate sequence\nGGAAGGAA\n"
                    ">NC_123456.2 conflicting version sequence\nAACCGGTT\n"
                ),
            }, reference_ids={"alpha.fa": "alpha", "beta.fa": "beta"})
            output = Path(root) / "records"
            result = import_from_snapshot(parent / "references.csv", output)
            self.assertEqual(result["status"], "complete")
            snapshot, _ = verified_record_snapshot(output)
            self.assertEqual(snapshot["record_count"], 7)
            self.assertEqual(snapshot["validation_status"], "review_required")

            common = lookup_records(output, fasta_id="common")
            self.assertEqual(len(common), 2)
            self.assertNotEqual(common[0]["record_id"], common[1]["record_id"])
            self.assertNotEqual(common[0]["sequence"], common[1]["sequence"])
            self.assertEqual(common[0]["source"], "NCBI RefSeq")
            self.assertEqual(common[0]["category"], "virus")
            self.assertEqual(common[0]["provenance"]["supplied_provenance"],
                             "provided with the reference specification")

            accession = lookup_records(
                output, accession="NC_123456", accession_version="3"
            )
            self.assertEqual(len(accession), 1)
            self.assertEqual(accession[0]["accession_version"], "3")
            by_internal_id = lookup_records(output, record_id=accession[0]["record_id"])
            self.assertEqual(by_internal_id[0]["fasta_id"], "NC_123456.3")
            by_hash = lookup_records(output, sequence_sha256=accession[0]["sequence_sha256"])
            self.assertEqual(len(by_hash), 2)
            self.assertEqual(
                {row["exact_sequence_group_size"] for row in by_hash}, {2}
            )

            conflict_types = {item["type"] for item in json.loads(
                (output / "conflicts.json").read_text(encoding="utf-8")
            )["conflicts"]}
            self.assertIn("fasta_identifier_reused", conflict_types)
            self.assertIn("accession_version_conflict", conflict_types)
            self.assertIn("accession_version_sequence_conflict", conflict_types)

            again = Path(root) / "records-again"
            second = import_from_snapshot(parent / "references.csv", again)
            self.assertEqual(verified_record_snapshot(output)[0]["snapshot_id"],
                             verified_record_snapshot(again)[0]["snapshot_id"])
            self.assertEqual(second["status"], "complete")

    def test_invalid_fasta_is_reported_and_never_marked_complete(self):
        with scratch_directory() as root:
            parent = make_parent(root, "bad", {"bad.fa": ">bad\nACGTZ\n"})
            output = Path(root) / "bad-records"
            with self.assertRaisesRegex(ValueError, "validation failed"):
                import_from_snapshot(parent / "references.csv", output)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            validation = json.loads((output / "validation.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(validation["status"], "invalid")
            self.assertIn("invalid_nucleotide_symbol",
                          {issue["code"] for issue in validation["errors"]})
            self.assertFalse((output / "records.csv").exists())
            with self.assertRaisesRegex(ValueError, "completed reference record snapshot"):
                verified_record_snapshot(output)

    def test_duplicate_identifier_within_one_fasta_is_invalid(self):
        with scratch_directory() as root:
            parent = make_parent(
                root, "duplicate", {"duplicate.fa": ">same\nACGT\n>same\nTTTT\n"}
            )
            output = Path(root) / "duplicate-records"
            with self.assertRaisesRegex(ValueError, "validation failed"):
                import_from_snapshot(parent / "references.csv", output)
            validation = json.loads((output / "validation.json").read_text(encoding="utf-8"))
            self.assertIn("duplicate_identifier",
                          {issue["code"] for issue in validation["errors"]})

    def test_unversioned_accession_sequence_conflict_is_reported(self):
        with scratch_directory() as root:
            parent = make_parent(
                root, "unversioned", {
                    "one.fa": ">NC_123456 unversioned reference\nACGT\n",
                    "two.fa": ">NC_123456 another unversioned record\nTGCA\n",
                },
            )
            output = Path(root) / "unversioned-records"
            import_from_snapshot(parent / "references.csv", output)
            conflicts = json.loads((output / "conflicts.json").read_text(encoding="utf-8"))
            self.assertIn("accession_sequence_conflict",
                          {item["type"] for item in conflicts["conflicts"]})

    def test_snapshot_integrity_and_per_record_comparison(self):
        with scratch_directory() as root:
            old_parent = make_parent(
                root, "old", {"ref.fa": ">NC_123456.1 old\nAAAACCCC\n"},
                reference_ids={"ref.fa": "stable-reference"},
            )
            new_parent = make_parent(
                root, "new", {"ref.fa": ">NC_123456.1 updated\nAAAACCCA\n>new_record\nGGGGTTTT\n"},
                reference_ids={"ref.fa": "stable-reference"},
            )
            old_records, new_records = Path(root) / "old-records", Path(root) / "new-records"
            import_from_snapshot(old_parent / "references.csv", old_records)
            import_from_snapshot(new_parent / "references.csv", new_records)
            comparison = Path(root) / "comparison"
            compare_record_snapshots(old_records, new_records, comparison)
            summary = json.loads((comparison / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["added"], 1)
            self.assertEqual(summary["changed"], 1)

            with (old_records / "records.csv").open("a", encoding="utf-8") as handle:
                handle.write("\n")
            with self.assertRaisesRegex(ValueError, "integrity failure"):
                lookup_records(old_records, fasta_id="NC_123456.1")

    def test_record_import_is_registered_as_a_trusted_workflow_stage(self):
        registry = artifact_workflow.build_default_registry()
        self.assertIsNotNone(registry.get("reference_record_import"))
        with scratch_directory() as root:
            parent = make_parent(root, "stage", {"records.fa": ">record\nACGT\n"})
            output = Path(root) / "workflow-stage"
            result = artifact_workflow.dispatch(
                "reference_record_import",
                {"references_table": parent / "references.csv"},
                output,
                registry=registry,
            )
            self.assertEqual(result["status"], "complete")
            self.assertTrue((output / "records.csv").is_file())


if __name__ == "__main__":
    unittest.main()