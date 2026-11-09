import copy
import unittest

from satellite_discovery.m35_specificity_assembly import (
    DECOY_SIMILARITY_LEVELS,
    GOVERNANCE,
    SEEDS,
    SIMILARITY_LEVELS,
    preregistered_design,
    validate_evidence_bundle,
    validate_design,
)


class M35PreregisteredDesignTests(unittest.TestCase):
    def setUp(self):
        self.design = preregistered_design(b">synthetic-panel\nACGT\n", "ACGT" * 100)

    def test_design_freezes_similarity_gradient_and_independent_seeds(self):
        validate_design(self.design)
        self.assertEqual(self.design["similarity_levels"], list(SIMILARITY_LEVELS))
        self.assertEqual(self.design["independent_seeds"], list(SEEDS))
        decoys = [row for row in self.design["cases"]
                  if row["condition"] == "target_absent_near_target_decoy"]
        self.assertEqual(len(decoys), len(SEEDS) * len(DECOY_SIMILARITY_LEVELS))
        self.assertEqual(
            sum(row["similarity_level"] == 1.0 for row in self.design["cases"]),
            len(SEEDS),
        )
        for level in DECOY_SIMILARITY_LEVELS:
            self.assertEqual(
                sum(row["similarity_level"] == level for row in decoys),
                len(SEEDS),
            )

    def test_panel_changes_invalidate_the_preregistered_digest(self):
        other = preregistered_design(b">synthetic-panel\nTGCA\n", "ACGT" * 100)
        self.assertNotEqual(self.design["panel_sha256"], other["panel_sha256"])
        self.assertNotEqual(self.design["design_sha256"], other["design_sha256"])

    def test_held_out_truth_is_not_exposed_to_screening_cases(self):
        held_out = [row for row in self.design["cases"] if row["split"] == "held_out"]
        self.assertTrue(held_out)
        self.assertTrue(all("truth_target_present" not in row for row in held_out))
        self.assertEqual(self.design["governance"], GOVERNANCE)

    def test_duplicate_ids_and_mislabeled_target_absent_decoys_fail(self):
        duplicate = copy.deepcopy(self.design)
        duplicate["cases"].append(copy.deepcopy(duplicate["cases"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate M35 case ID"):
            validate_design(duplicate)

        mislabeled = copy.deepcopy(self.design)
        decoy = next(row for row in mislabeled["cases"]
                     if row["condition"] == "target_absent_near_target_decoy")
        decoy["truth_target_present"] = True
        with self.assertRaisesRegex(ValueError, "mislabeled"):
            validate_design(mislabeled)

    def test_missing_similarity_level_replica_fails(self):
        incomplete = copy.deepcopy(self.design)
        decoy_index = next(
            i for i, row in enumerate(incomplete["cases"])
            if row["condition"] == "target_absent_near_target_decoy"
            and row["similarity_level"] == SIMILARITY_LEVELS[-1]
        )
        incomplete["cases"].pop(decoy_index)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            validate_design(incomplete)

    def make_bundle(self):
        cases = []
        truth = {}
        for design_case in self.design["cases"]:
            cid = design_case["case_id"]
            cases.append({
                "case_id": cid,
                "family_id": design_case["family_id"],
                "split": design_case["split"],
                "assembly_status": "ASSEMBLED_COMPLETE",
                "m8_search_complete": True,
                "candidate_records": [],
            })
            truth[cid] = {
                "target_present": (
                    design_case["condition"] == "known_target_positive_control"
                ),
            }
        return {
            "panel_sha256": self.design["panel_sha256"],
            "cases": cases,
            "truth_sidecars": truth,
            "candidate_identity": {},
        }

    def test_evidence_bundle_rejects_panel_truth_and_case_identity_drift(self):
        bundle = self.make_bundle()
        validate_evidence_bundle(self.design, bundle)

        altered = self.make_bundle()
        altered["panel_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "panel digest"):
            validate_evidence_bundle(self.design, altered)

        leaked = self.make_bundle()
        leaked["cases"][0]["truth_sidecar"] = {"target_present": True}
        with self.assertRaisesRegex(ValueError, "leakage"):
            validate_evidence_bundle(self.design, leaked)

        swapped = self.make_bundle()
        held_out_index = next(
            i for i, row in enumerate(swapped["cases"]) if row["split"] == "held_out"
        )
        swapped["cases"][0]["case_id"], swapped["cases"][held_out_index]["case_id"] = (
            swapped["cases"][held_out_index]["case_id"], swapped["cases"][0]["case_id"]
        )
        with self.assertRaisesRegex(ValueError, "wrong family or split"):
            validate_evidence_bundle(self.design, swapped)

        false_positive = self.make_bundle()
        absent_id = next(
            row["case_id"] for row in self.design["cases"]
            if row["condition"] == "target_absent_near_target_decoy"
            and row["split"] != "held_out"
        )
        false_positive["truth_sidecars"][absent_id]["target_present"] = True
        with self.assertRaisesRegex(ValueError, "misclassified"):
            validate_evidence_bundle(self.design, false_positive)

    def test_candidate_hash_id_and_read_support_are_verified(self):
        sequence = "ACGTACGT"
        import hashlib
        digest = hashlib.sha256(sequence.encode()).hexdigest()
        bundle = self.make_bundle()
        case = bundle["cases"][0]
        case["candidate_records"] = [{
            "candidate_id": "candidate-1",
            "sequence": sequence,
            "sha256": digest,
            "read_support_status": "READ_SUPPORTED_ASSEMBLY",
            "support_evidence": {"read_count": 4},
        }]
        bundle["candidate_identity"] = {"candidate-1": digest}
        validate_evidence_bundle(self.design, bundle)

        bad_hash = self.make_bundle()
        bad_hash["cases"][0]["candidate_records"] = [{
            "candidate_id": "candidate-1", "sequence": sequence,
            "sha256": "f" * 64, "read_support_status": "UNSUPPORTED_ASSEMBLY",
        }]
        bad_hash["candidate_identity"] = {"candidate-1": digest}
        with self.assertRaisesRegex(ValueError, "incorrect candidate hash"):
            validate_evidence_bundle(self.design, bad_hash)

        swapped_id = self.make_bundle()
        swapped_id["cases"][0]["candidate_records"] = [{
            "candidate_id": "candidate-b", "sequence": sequence,
            "sha256": digest, "read_support_status": "UNSUPPORTED_ASSEMBLY",
        }]
        swapped_id["candidate_identity"] = {"candidate-a": digest}
        with self.assertRaisesRegex(ValueError, "candidate ID digest mismatch"):
            validate_evidence_bundle(self.design, swapped_id)

        no_support = self.make_bundle()
        no_support["cases"][0]["candidate_records"] = [{
            "candidate_id": "candidate-1", "sequence": sequence,
            "sha256": digest, "read_support_status": "READ_SUPPORTED_ASSEMBLY",
        }]
        no_support["candidate_identity"] = {"candidate-1": digest}
        with self.assertRaisesRegex(ValueError, "lacks support"):
            validate_evidence_bundle(self.design, no_support)

    def test_assembler_failure_requires_stderr_and_correct_stage_classification(self):
        failed = self.make_bundle()
        case = failed["cases"][0]
        case.update({
            "assembly_status": "EXECUTION_FAILED",
            "m8_search_complete": False,
            "assembler_stderr": {"text": "invalid kmer coverage histogram", "exit_code": 21},
        })
        with self.assertRaisesRegex(ValueError, "stderr provenance"):
            validate_evidence_bundle(self.design, failed)

        import hashlib
        stderr_text = "invalid kmer coverage histogram"
        case["assembler_stderr"]["sha256"] = hashlib.sha256(
            stderr_text.encode()
        ).hexdigest()
        validate_evidence_bundle(self.design, failed)

        missing = self.make_bundle()
        missing["cases"][0].update({
            "assembly_status": "EXECUTION_FAILED",
            "m8_search_complete": False,
        })
        with self.assertRaisesRegex(ValueError, "stderr is missing"):
            validate_evidence_bundle(self.design, missing)

        bad_stage = self.make_bundle()
        bad_stage["cases"][0]["assembly_status"] = "SPADES_ERROR"
        with self.assertRaisesRegex(ValueError, "stage-level"):
            validate_evidence_bundle(self.design, bad_stage)


if __name__ == "__main__":
    unittest.main()
