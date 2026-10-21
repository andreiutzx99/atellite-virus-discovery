import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from satellite_discovery import m21_reference_exclusion as exclusion
from satellite_discovery import m21_scientific_scoring as scoring


def sha(data):
    return hashlib.sha256(data).hexdigest()


class M21Phase5ReferenceExclusionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.target = "ACGTTGCAAGTCGATC"
        self.policy = {
            "schema_version": exclusion.POLICY_VERSION,
            "policy_id": "EXCL-SYNTH00001",
            "min_query_coverage": 0.5,
            "min_identity": 0.8,
            "max_sequence_length": 1000,
            "max_total_bases": 10000,
            "max_panel_bytes": 20000,
            "max_references": 100,
            "max_alignment_cells": 100000,
            "excluded_sequences": [{
                "sequence_id": "SYNTH-00000001", "sequence": self.target,
                "sha256": sha(self.target.encode("ascii")),
            }],
        }
        self.policy_sha = exclusion.exclusion_policy_digest(self.policy)

    def tearDown(self):
        self.temp.cleanup()

    def check(self, records, policy=None, expected_policy=None, cells=None):
        policy = policy or self.policy
        if cells is not None:
            policy = {**policy, "max_alignment_cells": cells}
        content = "".join(f">{identifier}\n{sequence}\n" for identifier, sequence in records).encode("ascii")
        path = self.root / "synthetic.fa"
        path.write_bytes(content)
        policy_sha = expected_policy if expected_policy is not None else exclusion.exclusion_policy_digest(policy)
        return exclusion.validate_reference_exclusions(
            path, policy, expected_policy_sha256=policy_sha, expected_reference_sha256=sha(content)
        )

    @staticmethod
    def legacy_best_local_score(query, reference):
        rows, cols = len(query) + 1, len(reference) + 1
        scores = [[0] * cols for _ in range(rows)]
        best = (0, 0, 0)
        for i in range(1, rows):
            for j in range(1, cols):
                scores[i][j] = max(
                    0,
                    scores[i - 1][j - 1] + (2 if query[i - 1] == reference[j - 1] else -1),
                    scores[i - 1][j] - 2,
                    scores[i][j - 1] - 2,
                )
                if scores[i][j] > best[0]:
                    best = (scores[i][j], i, j)
        i, j = best[1:]
        matches = columns = aligned_query = 0
        while i and j and scores[i][j] > 0:
            diagonal = scores[i - 1][j - 1] + (2 if query[i - 1] == reference[j - 1] else -1)
            if scores[i][j] == diagonal:
                matches += query[i - 1] == reference[j - 1]
                columns += 1
                aligned_query += 1
                i -= 1
                j -= 1
            elif scores[i][j] == scores[i - 1][j] - 2:
                columns += 1
                aligned_query += 1
                i -= 1
            else:
                columns += 1
                j -= 1
        return best[0], matches / max(columns, 1), aligned_query / len(query)

    def test_exact_reverse_complement_mismatch_indels_partial_embedding_and_nonmatch(self):
        rc = self.target.translate(str.maketrans("ACGT", "TGCA"))[::-1]
        substituted = "T" + self.target[1:]
        inserted = self.target[:8] + "AAA" + self.target[8:]
        deleted = self.target[:5] + self.target[7:]
        partial = self.target[3:12]
        results = self.check([
            ("SYNTHREF-00000001", self.target),
            ("SYNTHREF-00000002", rc),
            ("SYNTHREF-00000003", substituted),
            ("SYNTHREF-00000004", inserted),
            ("SYNTHREF-00000005", deleted),
            ("SYNTHREF-00000006", "GGGG" + self.target + "TTTT"),
            ("SYNTHREF-00000007", partial),
            ("SYNTHREF-00000008", "TTTTTTTTTTTTTTTT"),
        ])
        self.assertEqual(results["status"], "FAIL")
        decisions = {item["reference_id"]: item["decision"] for item in results["results"]}
        self.assertTrue(all(decisions[f"SYNTHREF-{index:08d}"] == "REJECT" for index in range(1, 8)))
        self.assertEqual(decisions["SYNTHREF-00000008"], "ACCEPT")
        strict_reverse = self.check([("SYNTHREF-00000002", rc)], {
            **self.policy, "min_query_coverage": 1.0, "min_identity": 1.0,
        })
        self.assertEqual(strict_reverse["results"][0]["matches"][0]["orientation"], "REVERSE_COMPLEMENT")
        self.assertEqual(results["evidence_sha256"], sha(json.dumps({
            "policy_sha256": self.policy_sha,
            "reference_sha256": results["reference_sha256"],
            "excluded_sequence_sha256": [self.policy["excluded_sequences"][0]["sha256"]],
        }, sort_keys=True, separators=(",", ":")).encode()))

    def test_complete_search_finds_lower_scoring_qualifying_forward_and_reverse_hits(self):
        query = "ACGTTGCAAGTCGATCGGATTAAC"

        def mutate_spread(sequence):
            chars = list(sequence)
            for position in (1, 5, 9, 13, 17, 21):
                chars[position] = "A" if chars[position] != "A" else "C"
            return "".join(chars)

        rc_query = query.translate(str.maketrans("ACGT", "TGCA"))[::-1]
        forward_reference = mutate_spread(query) + "NNNNN" + query[:12]
        reverse_reference = mutate_spread(rc_query) + "NNNNN" + rc_query[-12:]
        forward_best = self.legacy_best_local_score(query, forward_reference)
        reverse_best = self.legacy_best_local_score(rc_query, reverse_reference)
        self.assertGreater(forward_best[0], 2 * 12)
        self.assertLess(forward_best[1], 0.9)
        self.assertGreater(reverse_best[0], 2 * 12)
        self.assertLess(reverse_best[1], 0.9)
        policy = {**self.policy, "min_query_coverage": 0.5, "min_identity": 0.9}
        result = self.check([
            ("SYNTHREF-00000021", forward_reference),
            ("SYNTHREF-00000022", reverse_reference),
        ], policy)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual([item["decision"] for item in result["results"]], ["REJECT", "REJECT"])
        self.assertEqual(result["results"][0]["matches"][0]["query_coverage"], 0.5)
        self.assertEqual(result["results"][1]["matches"][0]["orientation"], "REVERSE_COMPLEMENT")
        self.assertGreaterEqual(result["results"][1]["matches"][0]["query_coverage"], 0.5)

    def test_exact_threshold_boundary_is_inclusive(self):
        policy = {**self.policy, "min_query_coverage": 1.0, "min_identity": 1.0}
        result = self.check([("SYNTHREF-00000001", self.target)], policy)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["results"][0]["matches"][0]["query_coverage"], 1.0)
        self.assertEqual(result["results"][0]["matches"][0]["identity"], 1.0)

    def test_policy_binding_reference_mutation_missing_evidence_and_incomplete(self):
        changed = {**self.policy, "min_identity": 0.95}
        result = self.check([("SYNTHREF-00000001", "TTTTTTTT")], changed, self.policy_sha)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("altered" in item for item in result["issues"]))

        content = b">SYNTHREF-00000001\nTTTTTTTT\n"
        path = self.root / "mutated.fa"
        path.write_bytes(content)
        result = exclusion.validate_reference_exclusions(
            path, self.policy, expected_policy_sha256=self.policy_sha,
            expected_reference_sha256="0" * 64,
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("changed" in item for item in result["issues"]))
        result = exclusion.validate_reference_exclusions(
            path, self.policy, expected_policy_sha256=None,
            expected_reference_sha256=sha(content),
        )
        self.assertEqual(result["status"], "FAIL")
        result = self.check([("SYNTHREF-00000001", self.target)], cells=1)
        self.assertEqual(result["status"], "INCOMPLETE")


class M21Phase5ScoringTests(unittest.TestCase):
    def setUp(self):
        self.ids = [f"BLD-{index:024X}" for index in range(1, 7)]
        self.samples = [
            {"sample_id": self.ids[0], "candidates": [{"candidate_id": "cand-A"}, {"candidate_id": "cand-A"}], "read_count": 100, "read_unit": "READS"},
            {"sample_id": self.ids[1], "candidates": [], "read_count": 100, "read_unit": "READS"},
            {"sample_id": self.ids[2], "candidates": [], "read_count": 200, "read_unit": "READS"},
            {"sample_id": self.ids[3], "candidates": [{"candidate_id": "false-X"}, {"candidate_id": "false-Y"}], "read_count": 200, "read_unit": "READS"},
            {"sample_id": self.ids[4], "candidates": [{"candidate_id": "pending"}], "read_count": 0, "read_unit": "READS"},
        ]
        self.analysis = {"samples": self.samples}
        self.analysis["analysis_sha256"] = scoring.canonical_sha256(self.samples)
        self.truth = {
            "analysis_sha256": self.analysis["analysis_sha256"],
            "truth_records": [
                {"sample_id": self.ids[0], "label": "POSITIVE", "truth_candidate_ids": ["cand-A"]},
                {"sample_id": self.ids[1], "label": "POSITIVE", "truth_candidate_ids": ["cand-B"]},
                {"sample_id": self.ids[2], "label": "NEGATIVE", "truth_candidate_ids": []},
                {"sample_id": self.ids[3], "label": "NEGATIVE", "truth_candidate_ids": []},
            ],
        }
        self.qualifications = [
            self.qualification(1, self.ids[0], "POSITIVE", "EVALUABLE", True, "bio-1"),
            self.qualification(2, self.ids[1], "POSITIVE", "EVALUABLE", True, "bio-2"),
            self.qualification(3, self.ids[2], "NEGATIVE", "EVALUABLE", True, "bio-3"),
            self.qualification(4, self.ids[3], "NEGATIVE", "EVALUABLE", True, "bio-4"),
            self.qualification(5, self.ids[4], "POSITIVE", "PENDING", False, "bio-5"),
        ]
        self.auth = {"approved": True, "reviewer_ids": ["REV-00000001", "REV-00000002"],
                     "truth_bundle_sha256": scoring.canonical_sha256(self.truth["truth_records"])}
        self.reference_exclusion = {
            "status": "PASS", "evidence_sha256": sha(b"synthetic-exclusion-audit"),
            "results": [{"reference_id": "SYNTHREF-00000001", "decision": "ACCEPT"}],
            "issues": [],
        }

    def qualification(self, number, sample, kind, status, eligible, group):
        record = {
            "control_id": f"CTL-SYNTH{number:05d}",
            "sample_ids": [sample], "control_class": kind, "evaluation_status": status,
            "independently_reviewed": status == "EVALUABLE",
            "scoring_eligibility": eligible,
            "exclusion_reason": None if eligible else "Independent evidence pending.",
            "study_id": "STUDY-SYNTH-01", "replicate_group": group,
            "evidence_strength": "HIGH" if kind == "POSITIVE" else "MODERATE",
            "sensitivity_status": "ADEQUATE" if kind == "NEGATIVE" else "NOT_APPLICABLE",
            "review_evidence_sha256": sha(f"review-{number}".encode()) if eligible else None,
            "reviewer_ids": ["REV-00000001", "REV-00000002"] if eligible else [],
        }
        record["qualification_sha256"] = scoring.qualification_digest(record)
        return record

    def score(self):
        return scoring.score_synthetic_bundle(
            self.analysis, self.truth, self.qualifications,
            unblinding_authorization=self.auth,
            expected_policy_sha256=scoring.scoring_policy_digest(),
            reference_exclusion_result=self.reference_exclusion,
            expected_reference_evidence_sha256=self.reference_exclusion["evidence_sha256"],
        )

    def test_confusion_candidate_metrics_and_excluded_pending_positive(self):
        result = self.score()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["overall_state"], "BLOCKED_FOR_BENCHMARK_EXECUTION")
        self.assertEqual(result["statement"], "SYNTHETIC SOFTWARE VALIDATION — NOT BIOLOGICAL PERFORMANCE EVIDENCE")
        self.assertEqual(result["sample_level"]["confusion_matrix"], {"TP": 1, "FP": 1, "TN": 1, "FN": 1})
        self.assertEqual(result["sample_level"]["sensitivity"]["value"], 0.5)
        self.assertEqual(result["sample_level"]["specificity"]["value"], 0.5)
        self.assertEqual(result["candidate_level"]["true_positives"], 1)
        self.assertEqual(result["candidate_level"]["false_positives"], 2)
        self.assertEqual(result["candidate_level"]["false_negatives"], 1)
        self.assertEqual(result["candidate_level"]["false_candidate_burden_per_evaluable_negative_sample"]["value"], 1.0)
        self.assertEqual(result["candidate_level"]["false_candidate_burden_per_million_reads_or_pairs"]["value"], 2_000_000 / 400)
        self.assertEqual(result["candidate_level"]["false_candidate_burden_per_million_reads_or_pairs"]["read_unit"], "READS")
        self.assertEqual(result["reference_exclusion_verification"]["references_checked"], 1)
        self.assertEqual(len(result["qualification_sha256s"]), 4)
        self.assertEqual(len(result["excluded_controls"]), 1)
        self.assertIn("NOT BIOLOGICAL PERFORMANCE EVIDENCE", scoring.human_scoring_report(result))

    def test_technical_replicates_count_as_one_biological_group(self):
        rep = self.ids[5]
        self.samples.append({"sample_id": rep, "candidates": [], "read_count": 300, "read_unit": "READS"})
        self.analysis["analysis_sha256"] = scoring.canonical_sha256(self.samples)
        self.truth["analysis_sha256"] = self.analysis["analysis_sha256"]
        self.truth["truth_records"].append({"sample_id": rep, "label": "POSITIVE", "truth_candidate_ids": ["cand-A"]})
        self.qualifications[0]["sample_ids"].append(rep)
        self.qualifications[0]["qualification_sha256"] = scoring.qualification_digest(self.qualifications[0])
        self.auth["truth_bundle_sha256"] = scoring.canonical_sha256(self.truth["truth_records"])
        result = self.score()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["sample_level"]["confusion_matrix"]["TP"], 1)
        self.assertEqual(result["sample_level"]["eligible_positive_groups"], 2)
        self.assertEqual(result["candidate_level"]["true_positives"], 1)

    def test_control_truth_and_group_ownership_conflicts_fail_before_scoring(self):
        self.truth["truth_records"][0]["label"] = "NEGATIVE"
        self.auth["truth_bundle_sha256"] = scoring.canonical_sha256(self.truth["truth_records"])
        result = self.score()
        self.assertEqual(result["status"], "FAIL")
        self.assertNotIn("sample_level", result)
        self.assertTrue(any("class conflicts" in issue for issue in result["issues"]))

        self.truth["truth_records"][0]["label"] = "POSITIVE"
        self.auth["truth_bundle_sha256"] = scoring.canonical_sha256(self.truth["truth_records"])
        for index, helper_class, helper_label in (
            (0, "HELPER_POSITIVE", "POSITIVE"),
            (1, "HELPER_NEGATIVE", "NEGATIVE"),
        ):
            self.truth["truth_records"][index]["label"] = helper_label
            self.auth["truth_bundle_sha256"] = scoring.canonical_sha256(self.truth["truth_records"])
            self.qualifications[index] = self.qualification(
                7 + index, self.ids[index], helper_class, "EVALUABLE", True, f"helper-{index}"
            )
            result = self.score()
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("helper comparators" in issue.lower() for issue in result["issues"]))

        self.truth["truth_records"][1]["label"] = "POSITIVE"
        self.auth["truth_bundle_sha256"] = scoring.canonical_sha256(self.truth["truth_records"])
        self.qualifications[0] = self.qualification(1, self.ids[0], "POSITIVE", "EVALUABLE", True, "bio-1")
        self.qualifications[1] = self.qualification(2, self.ids[1], "POSITIVE", "EVALUABLE", True, "bio-2")
        self.qualifications[2]["replicate_group"] = "bio-1"
        self.qualifications[2]["qualification_sha256"] = scoring.qualification_digest(self.qualifications[2])
        result = self.score()
        self.assertEqual(result["status"], "FAIL")
        self.assertNotIn("sample_level", result)
        self.assertTrue(any("spans multiple controls or studies" in issue for issue in result["issues"]))

        self.qualifications[2]["replicate_group"] = "bio-1"
        self.qualifications[2]["study_id"] = "STUDY-SYNTH-OTHER"
        self.qualifications[2]["qualification_sha256"] = scoring.qualification_digest(self.qualifications[2])
        result = self.score()
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("spans multiple controls or studies" in issue for issue in result["issues"]))

    def test_undefined_metrics_zero_reads_and_missing_authorization_fail_closed(self):
        result = self.score()
        self.assertEqual(result["overall_state"], "BLOCKED_FOR_BENCHMARK_EXECUTION")
        no_truth = {"analysis_sha256": self.analysis["analysis_sha256"], "truth_records": []}
        auth = {"approved": True, "reviewer_ids": [], "truth_bundle_sha256": scoring.canonical_sha256([])}
        result = scoring.score_synthetic_bundle(self.analysis, no_truth, self.qualifications,
                                                unblinding_authorization=auth,
                                                expected_policy_sha256="0" * 64,
                                                reference_exclusion_result=self.reference_exclusion,
                                                expected_reference_evidence_sha256=self.reference_exclusion["evidence_sha256"])
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("authorization" in item.lower() for item in result["issues"]))

    def test_sensitivity_specificity_are_not_estimable_without_both_classes(self):
        self.samples[:] = self.samples[:1]
        self.analysis["analysis_sha256"] = scoring.canonical_sha256(self.samples)
        self.truth["analysis_sha256"] = self.analysis["analysis_sha256"]
        self.truth["truth_records"] = [{"sample_id": self.ids[0], "label": "POSITIVE",
                                        "truth_candidate_ids": ["cand-A"]}]
        self.qualifications[:] = self.qualifications[:1]
        self.auth["truth_bundle_sha256"] = scoring.canonical_sha256(self.truth["truth_records"])
        result = self.score()
        self.assertEqual(result["sample_level"]["sensitivity"]["value"], 1.0)
        self.assertEqual(result["sample_level"]["specificity"]["status"], "NOT_ESTIMABLE")
        self.assertIsNone(result["sample_level"]["specificity"]["value"])

        self.truth["truth_records"][0]["label"] = "NEGATIVE"
        self.truth["truth_records"][0]["truth_candidate_ids"] = []
        self.samples[0]["candidates"] = []
        self.analysis["analysis_sha256"] = scoring.canonical_sha256(self.samples)
        self.truth["analysis_sha256"] = self.analysis["analysis_sha256"]
        self.qualifications[0] = self.qualification(3, self.ids[0], "NEGATIVE", "EVALUABLE", True, "bio-3")
        self.auth["truth_bundle_sha256"] = scoring.canonical_sha256(self.truth["truth_records"])
        result = self.score()
        self.assertEqual(result["sample_level"]["sensitivity"]["status"], "NOT_ESTIMABLE")
        self.assertEqual(result["sample_level"]["specificity"]["value"], 1.0)

    def test_reference_exclusion_bypass_is_rejected(self):
        self.reference_exclusion["status"] = "INCOMPLETE"
        result = self.score()
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("reference-exclusion" in item for item in result["issues"]))

    def test_tampered_analysis_truth_identity_and_qualification_are_rejected(self):
        self.analysis["samples"][0]["read_count"] = 999
        result = self.score()
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("analysis output digest" in item.lower() for item in result["issues"]))
        self.analysis["samples"][0]["read_count"] = 100
        self.qualifications[0]["scoring_eligibility"] = False
        result = self.score()
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("qualification digest" in item.lower() for item in result["issues"]))

    def test_pending_or_unevaluable_truth_cannot_enter_denominators(self):
        self.truth["truth_records"].append({"sample_id": self.ids[4], "label": "POSITIVE", "truth_candidate_ids": ["pending"]})
        self.auth["truth_bundle_sha256"] = scoring.canonical_sha256(self.truth["truth_records"])
        result = self.score()
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("exactly the eligible" in item for item in result["issues"]))

    def test_competing_truth_items_and_zero_read_denominator(self):
        self.samples[0]["candidates"] = [{"candidate_id": "cand-A"}]
        self.analysis["analysis_sha256"] = scoring.canonical_sha256(self.samples)
        self.truth["analysis_sha256"] = self.analysis["analysis_sha256"]
        self.truth["truth_records"][0]["truth_candidate_ids"] = ["cand-A", "cand-B"]
        self.auth["truth_bundle_sha256"] = scoring.canonical_sha256(self.truth["truth_records"])
        for row in self.samples[:4]:
            row["read_count"] = 0
        self.analysis["analysis_sha256"] = scoring.canonical_sha256(self.samples)
        self.truth["analysis_sha256"] = self.analysis["analysis_sha256"]
        self.auth["truth_bundle_sha256"] = scoring.canonical_sha256(self.truth["truth_records"])
        result = self.score()
        self.assertEqual(result["candidate_level"]["true_positives"], 1)
        self.assertEqual(result["candidate_level"]["false_negatives"], 2)
        self.assertEqual(result["candidate_level"]["false_candidate_burden_per_million_reads_or_pairs"]["status"], "NOT_ESTIMABLE")


if __name__ == "__main__":
    unittest.main()
