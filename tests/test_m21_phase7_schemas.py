import json
import unittest
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, FormatChecker, RefResolver
except ImportError:
    Draft202012Validator = None

from satellite_discovery import m21_phase7_evidence as phase7

SCHEMAS = Path(__file__).parents[1] / "satellite_discovery"


@unittest.skipUnless(Draft202012Validator, "install the phase7-schema-validation extra")
class Phase7SchemaTests(unittest.TestCase):
    def load_schema(self, name):
        return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))

    def test_all_phase7_schemas_are_draft_2020_12_and_reject_invalid_instances(self):
        names = [
            "m21_phase7_custody_checkpoint.schema.json",
            "m21_phase7_readiness.schema.json",
            "m21_phase7_reference_limits.schema.json",
        ]
        for name in names:
            with self.subTest(schema=name):
                Draft202012Validator.check_schema(self.load_schema(name))

        limits = self.load_schema(names[2])
        limits_validator = Draft202012Validator(limits)
        limits_validator.validate({
            "max_artifacts": 2, "max_total_bytes": 10000,
            "max_total_bases": 5000, "max_references": 20,
            "max_alignment_cells": 100000,
        })
        with self.assertRaises(Exception):
            limits_validator.validate({"max_artifacts": 0})

        readiness = self.load_schema(names[1])
        report_validator = Draft202012Validator(readiness, format_checker=FormatChecker())
        report_validator.validate(phase7.phase7_readiness_report(None, None, None, None))
        invalid_report = phase7.phase7_readiness_report(None, None, None, None)
        invalid_report["biological_execution_authorized"] = True
        with self.assertRaises(Exception):
            report_validator.validate(invalid_report)

        checkpoint = self.load_schema(names[0])
        manifest_path = SCHEMAS / "m21_benchmark_manifest.schema.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        resolver = RefResolver(
            base_uri=(SCHEMAS / names[0]).resolve().as_uri(),
            referrer=checkpoint,
            store={manifest_path.resolve().as_uri(): manifest},
        )
        checkpoint_validator = Draft202012Validator(
            checkpoint, resolver=resolver, format_checker=FormatChecker(),
        )
        approval = {
            "status": "APPROVED", "approval_id": "APR-ABCDEFGHIJKL",
            "reviewer_id": "REV-ABCDEFGH", "key_id": "KEY-ABCDEFGHIJ",
            "approved_at": "2026-10-21T10:00:00Z",
            "expires_at": "2027-10-21T10:00:00Z",
            "evidence_sha256": "a" * 64, "manifest_sha256": "b" * 64,
            "signature_ed25519": "synthetic-signature",
        }
        valid_checkpoint = {
            "dataset_id": "DS-SYNTH00001", "chain_id": "CHAIN-SYNTH-01",
            "event_count": 1, "event_sha256": "a" * 64, "sequence": 1,
            "created_at": "2026-10-21T11:00:00Z",
            "previous_checkpoint_sha256": None,
            "trust_store_identity": "c" * 64, "approval": approval,
        }
        checkpoint_validator.validate(valid_checkpoint)
        invalid_checkpoint = dict(valid_checkpoint, sequence=0)
        with self.assertRaises(Exception):
            checkpoint_validator.validate(invalid_checkpoint)
