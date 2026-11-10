import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import validate_m35_source_artifact as source_artifact
from satellite_discovery.m34_negative_control_indel_robustness import (
    _truth_sequence_for_m35,
    validate_positive_indel_summary,
)
from satellite_discovery.m35_specificity_assembly import (
    DECOY_SIMILARITY_LEVELS,
    GOVERNANCE,
    SEEDS,
    SIMILARITY_LEVELS,
    _oat_settings,
    _feature_diagnostics,
    _m35_handoff,
    _oat_factor_comparisons,
    _spades_failure_summary,
    _support_semantics_sha256,
    _summarize_gradient,
    _gradient_cases,
    preregistered_design,
    reproduce_m34,
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


class M35SourceArtifactTests(unittest.TestCase):
    def test_archived_m34_report_derives_missing_indel_aggregates_from_cases(self):
        fixture = Path(__file__).parent / "fixtures/m35/m34-original-indel-report-excerpt.json"
        archived_report = json.loads(fixture.read_text(encoding="utf-8"))
        summary = {
            "generated_cases": 7,
            "exact_supported": 0,
            "partial_supported": 3,
            "evaluable_cases": 3,
            "assembler_execution_failures": 4,
        }
        aggregate_before = copy.deepcopy(archived_report["positive_indel_recovery"])
        self.assertNotIn("evaluable_cases", aggregate_before)
        self.assertNotIn("assembler_execution_failures", aggregate_before)
        self.assertEqual(
            validate_positive_indel_summary(summary, archived_report), summary
        )
        self.assertEqual(archived_report["positive_indel_recovery"], aggregate_before)

        corrupted = copy.deepcopy(archived_report)
        corrupted["case_level_results"][0]["partial_reconstruction"] = False
        with self.assertRaisesRegex(ValueError, "case evidence"):
            validate_positive_indel_summary(summary, corrupted)

    def test_artifact_metadata_is_bound_to_the_registered_run(self):
        source_artifact.validate_artifact_metadata(
            13670022421, 42609565425, "m34-negative-control-indel-robustness"
        )
        for args in (
            (1, 42609565425, "m34-negative-control-indel-robustness"),
            (13670022421, 2, "m34-negative-control-indel-robustness"),
            (13670022421, 42609565425, "other-artifact"),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                source_artifact.validate_artifact_metadata(*args)

    def test_source_artifact_rejects_missing_and_corrupted_raw_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "evidence.tsv"
            evidence.write_text("verified evidence\n", encoding="utf-8")
            digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
            source_artifact._check_digest(evidence, digest)
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                source_artifact._check_digest(evidence, "0" * 64)
            with self.assertRaisesRegex(ValueError, "missing"):
                source_artifact._check_digest(root / "missing.tsv", digest)

    def test_end_to_end_source_validation_rejects_changed_m8_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "artifact"
            benchmark = artifact / "benchmark"
            benchmark.mkdir(parents=True)
            panel = benchmark / "reference" / "panel.fasta"
            panel.parent.mkdir(parents=True, exist_ok=True)
            panel.write_bytes(b">synthetic-panel\nACGT\n")
            panel_digest = hashlib.sha256(panel.read_bytes()).hexdigest()
            summary_path = root / "summary.json"
            cases = sorted(source_artifact.REQUIRED_CASES)
            source_rows, metrics, triage, read_index, truth_cases = [], [], [], {}, {}
            for index, case_id in enumerate(cases):
                sequence = f"candidate-{index}"
                candidate_sha = hashlib.sha256(sequence.encode()).hexdigest()
                analysis_id = f"m34x{index:04d}"
                candidate_id = f"contig-{index}"
                stage = (
                    benchmark / "reconstruction" / case_id / "stages"
                    / f"m6_{analysis_id}"
                )
                (stage / "assembly").mkdir(parents=True, exist_ok=True)
                (stage / "assembly" / "contigs.fasta").write_text(
                    f">{candidate_id}\n{sequence}\n", encoding="ascii"
                )
                (stage / "read_support.json").write_text(
                    json.dumps({"contigs": [{
                        "contig_id": candidate_id,
                        "status": "READ_SUPPORTED_ASSEMBLY",
                    }]}),
                    encoding="utf-8",
                )
                background_sha = hashlib.sha256(f"background-{index}".encode()).hexdigest()
                read_bytes = (
                    json.dumps({
                        "read_count": 1,
                        "read_provenance": {
                            "read-1": {
                                "source_role": "synthetic_background",
                                "source_record_sha256": background_sha,
                            }
                        },
                    }) + "\n"
                ).encode()
                read_path = benchmark / "read_provenance" / f"{case_id}.json"
                read_path.parent.mkdir(parents=True, exist_ok=True)
                read_path.write_bytes(read_bytes)
                read_digest = hashlib.sha256(read_bytes).hexdigest()
                read_index[case_id] = {
                    "path": f"read_provenance/{case_id}.json",
                    "sha256": read_digest,
                }

                truth_bytes = json.dumps(
                    {"cases": [{"candidate_sequence": None}]}
                ).encode()
                truth_path = benchmark / "reconstruction" / case_id / "heldout_truth.json"
                truth_path.parent.mkdir(parents=True, exist_ok=True)
                truth_path.write_bytes(truth_bytes)
                truth_digest = hashlib.sha256(truth_bytes).hexdigest()
                truth_cases[case_id] = {
                    "candidate_sequence_absent": True,
                    "source_truth_sidecar_sha256": truth_digest,
                }

                raw_path = benchmark / "m8" / f"{case_id}.tsv"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text("alignment\n", encoding="utf-8")
                raw_digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
                source_rows.append({
                    "case_id": case_id,
                    "synthetic_truth_target_present": False,
                    "analysis_id": analysis_id,
                    "background_category": "near_target_divergence",
                    "target_absent_error_condition": "zero_error",
                })
                metrics.append({"case_id": case_id, "m8_search_complete": True})
                triage.append({
                    "case_id": case_id,
                    "candidate_records": [{
                        "candidate_id": candidate_id,
                        "query_sha256": candidate_sha,
                        "read_support_status": "READ_SUPPORTED_ASSEMBLY",
                        "m8_aggregate_status": "COMPLETE",
                        "triage_status": "REVIEW_PRIORITY",
                    }],
                    "raw_outputs": [{
                        "path": f"m8/{case_id}.tsv",
                        "sha256": raw_digest,
                    }],
                })
            summary = {
                "provenance": {
                    "artifact_id": source_artifact.EXPECTED_ARTIFACT_ID,
                    "workflow_run_id": source_artifact.EXPECTED_RUN_ID,
                    "artifact_name": source_artifact.EXPECTED_ARTIFACT_NAME,
                },
                "false_alarm_investigations": [{
                    "case_id": case_id,
                    "candidate": {
                        "sha256": triage[index]["candidate_records"][0]["query_sha256"]
                    },
                    "source_truth": {
                        "sidecar_sha256": truth_cases[case_id]["source_truth_sidecar_sha256"]
                    },
                    "background": {
                        "category": "near_target_divergence",
                        "error_condition": "zero_error",
                        "source_record_sha256": hashlib.sha256(
                            f"background-{index}".encode()
                        ).hexdigest(),
                    },
                } for index, case_id in enumerate(cases)],
                "reference_panel": {"panel_fasta_sha256": panel_digest},
            }
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            (artifact / "M34_NEGATIVE_CONTROL_INDEL_ROBUSTNESS.json").write_text(
                json.dumps({
                    "case_level_results": source_rows,
                    "reference_panel": {"panel_fasta_sha256": panel_digest},
                    "governance": {
                        "decision": "INCOMPLETE",
                        "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
                        "biological_execution_authorized": False,
                    },
                }),
                encoding="utf-8",
            )
            (benchmark / "M32_END_TO_END_SYNTHETIC_EVIDENCE.json").write_text(
                json.dumps({
                    "panel_preregistration": {"panel_fasta_sha256": panel_digest},
                    "benchmark_metrics": {"cases": metrics},
                    "candidate_triage": triage,
                }),
                encoding="utf-8",
            )
            (benchmark / "M34_READ_PROVENANCE_INDEX.json").write_text(
                json.dumps(read_index), encoding="utf-8"
            )
            (benchmark / "M34_TARGET_ABSENCE_VALIDATION.json").write_text(
                json.dumps({"cases": truth_cases}), encoding="utf-8"
            )
            with patch.object(source_artifact, "_validate_summary_totals"):
                validated = source_artifact.validate_source_artifact(artifact, summary_path)
                self.assertEqual(validated["rerun_status"], "NOT_RUN")
                self.assertEqual(len(validated["cases"]), 5)
                (benchmark / "m8" / f"{cases[0]}.tsv").write_text(
                    "tampered\n", encoding="utf-8"
                )
                with self.assertRaisesRegex(ValueError, "digest mismatch"):
                    source_artifact.validate_source_artifact(artifact, summary_path)


class M35ResultAnalysisTests(unittest.TestCase):
    def test_gradient_input_parameters_match_for_full_and_repeat_bundles(self):
        target = "ACGT" * 100
        design = preregistered_design(b">synthetic-panel\nACGT\n", target)
        full_cases, _contracts, _bundle = _gradient_cases(
            design, target, [], {}
        )
        repeat_design = dict(
            design,
            cases=[row for row in design["cases"] if row["split"] == "held_out"],
        )
        repeat_cases, _contracts, _bundle = _gradient_cases(
            repeat_design, target, [], {}
        )
        full_by_id = {row["case_id"]: row for row in full_cases}
        repeat_by_id = {row["case_id"]: row for row in repeat_cases}
        fields = (
            "m25_replicate", "gc_fraction", "background_gc_fraction",
            "target_length", "coverage", "m25_read_length", "error_rate",
            "insertion_rate", "deletion_rate", "divergence",
        )
        self.assertEqual(set(repeat_by_id), {
            row["case_id"] for row in design["cases"] if row["split"] == "held_out"
        })
        for case_id, repeat in repeat_by_id.items():
            with self.subTest(case_id=case_id):
                self.assertEqual(
                    {field: full_by_id[case_id][field] for field in fields},
                    {field: repeat[field] for field in fields},
                )

    def test_similarity_summary_uses_positive_control_at_one_hundred_percent(self):
        rows = []
        for split in ("development", "tuning", "held_out"):
            rows.append({
                "similarity_level": 1.0, "condition": "known_target_positive_control",
                "split": split, "m8_search_complete": True,
                "read_supported_candidate_count": 1, "review_priority": True,
            })
            rows.append({
                "similarity_level": 0.9, "condition": "target_absent_near_target_decoy",
                "split": split, "m8_search_complete": True,
                "read_supported_candidate_count": 1, "review_priority": split != "held_out",
            })
        summary = _summarize_gradient(rows)
        positive = summary[0]
        self.assertEqual(positive["truth_stratum"], "positive_control")
        self.assertEqual(
            (positive["review_priority_cases"], positive["eligible_cases"]), (3, 3)
        )
        decoy = next(row for row in summary if row["similarity_level"] == 0.9)
        self.assertEqual(
            (decoy["review_priority_cases"], decoy["eligible_cases"]), (2, 3)
        )
        self.assertEqual(len(_oat_settings()), 14)

    def test_feature_diagnostics_reuse_frozen_m31_qualifier(self):
        rows = [{
            "similarity_level": 0.9,
            "condition": "target_absent_near_target_decoy",
            "case_id": "held_out-case",
            "candidates": [{
                "triage_status": "REVIEW_PRIORITY",
                "distinct_reference_count": 2,
                "secondary_match_count": 1,
                "all_alignment_matches": [{
                    "panel_role": "satellite_subviral",
                    "alignment": {"percent_identity": 91, "query_coverage": 0.31},
                }],
            }],
        }]
        summary = _feature_diagnostics(rows)
        level = next(row for row in summary if row["similarity_level"] == 0.9)
        self.assertEqual(level["qualifying_cases"], 1)
        self.assertEqual(level["review_priority_with_qualifying_alignment"], 1)
        self.assertEqual(level["multiple_reference_candidates"], 1)
        self.assertEqual(level["secondary_alignment_count"], 1)

    def test_oat_comparisons_are_descriptive_against_the_registered_baseline(self):
        results = [{
            "factor": "baseline", "level": "combined_moderate",
            "execution_failure_count": 2, "execution_denominator": 2,
            "repetitions": [],
        }, {
            "factor": "coverage", "level": 80,
            "execution_failure_count": 1, "execution_denominator": 2,
            "repetitions": [{"assembly_status": "NOT_RUN"}],
        }]
        comparison = _oat_factor_comparisons(results)[0]
        self.assertEqual(comparison["difference_from_baseline"], -0.5)
        self.assertEqual(comparison["not_run_replicates"], 1)
        self.assertIn("not a causal", comparison["interpretation"])

    def test_empty_m6_fasta_is_not_misclassified_as_a_manifest_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assembly = root / "source" / "assembly"
            assembly.mkdir(parents=True)
            contigs = assembly / "contigs.fasta"
            contigs.write_bytes(b"")
            handoff = lambda *_args: self.fail("empty contigs must not be handed off")
            self.assertIsNone(_m35_handoff(handoff, assembly.parent, root / "out", "case"))
            contigs.write_text(">candidate\nACGT\n", encoding="ascii")
            manifest = assembly / "manifest.json"
            manifest.write_text(json.dumps({"status": "failed"}), encoding="utf-8")
            self.assertIsNone(_m35_handoff(handoff, assembly.parent, root / "out", "case"))
            manifest.unlink()
            with self.assertRaisesRegex(ValueError, "manifest"):
                _m35_handoff(
                    lambda *_args: (_ for _ in ()).throw(
                        ValueError("assembly manifest missing")
                    ),
                    assembly.parent, root / "out", "case",
                )

    def test_support_repeatability_ignores_raw_sam_digest_but_keeps_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "support.json"
            body = {
                "status": "READ_SUPPORTED_ASSEMBLY",
                "contigs": [{"contig_id": "c1", "supporting_read_count": 3}],
                "provenance": {"support_sam_sha256": "a"},
            }
            path.write_text(json.dumps(body), encoding="utf-8")
            first = _support_semantics_sha256(path)
            body["provenance"]["support_sam_sha256"] = "b"
            path.write_text(json.dumps(body), encoding="utf-8")
            self.assertEqual(first, _support_semantics_sha256(path))
            body["contigs"][0]["supporting_read_count"] = 4
            path.write_text(json.dumps(body), encoding="utf-8")
            self.assertNotEqual(first, _support_semantics_sha256(path))

    def test_spades_failure_summary_is_stable_across_run_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp) / "stage"
            log = stage / "assembly" / "raw" / "spades.log"
            log.parent.mkdir(parents=True)
            manifest = {"status": "failed", "exit_status": 21}
            log.write_text(
                "== Error == system call for: ['/run/one/config.info'] "
                "finished abnormally, OS return value: 21\n",
                encoding="utf-8",
            )
            first = _spades_failure_summary(stage, manifest, {})
            log.write_text(
                "== Error == system call for: ['/run/two/config.info'] "
                "finished abnormally, OS return value: 21\n",
                encoding="utf-8",
            )
            self.assertEqual(first, _spades_failure_summary(stage, manifest, {}))
            self.assertEqual(first, "SPAdes core exited with OS return value 21.")

    def test_target_absent_cases_keep_independent_m19_reference_sequence(self):
        design = {
            "target_sequence_by_id": {"positive": "A" * 100, "decoy": "A" * 100},
            "seed_by_id": {"decoy": 35100001},
        }
        fallback_calls = []

        def fallback(rng, length, gc_fraction):
            sequence = "".join(rng.choice("ACGT") for _ in range(length))
            fallback_calls.append((length, gc_fraction, sequence))
            return sequence

        positive = _truth_sequence_for_m35(
            {"case_id": "positive", "positive": True}, design, None, 100, 0.5, fallback
        )
        decoy_reference = _truth_sequence_for_m35(
            {"case_id": "decoy", "positive": False}, design, object(), 100, 0.5, fallback
        )
        repeated_reference = _truth_sequence_for_m35(
            {"case_id": "decoy", "positive": False}, design, object(), 100, 0.5, fallback
        )

        self.assertEqual(positive, "A" * 100)
        self.assertEqual(decoy_reference, repeated_reference)
        self.assertNotEqual(decoy_reference, "A" * 100)
        self.assertEqual(len(fallback_calls), 2)
        self.assertEqual(
            [(length, gc) for length, gc, _sequence in fallback_calls],
            [(100, 0.5), (100, 0.5)],
        )

    def test_m34_rerun_is_distinguished_from_archived_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            current, archive = Path(tmp) / "current", Path(tmp) / "archive"
            current.mkdir()
            archive.mkdir()
            cases = {}
            for case_id in source_artifact.REQUIRED_CASES:
                cases[case_id] = {
                    "case_id": case_id,
                    "candidate_records": [{"triage_status": "REVIEW_PRIORITY"}],
                }
            failure_ids = (
                "tuning-m34-i002", "tuning-m34-i005",
                "held_out-m34-i006", "development-m34-i007",
            )
            for case_id in failure_ids:
                cases[case_id] = {
                    "case_id": case_id, "assembly_status": "EXECUTION_FAILED",
                    "candidate_records": [],
                }
            for root in (current, archive):
                (root / "M34_NEGATIVE_CONTROL_INDEL_ROBUSTNESS.json").write_text(
                    json.dumps({"case_level_results": list(cases.values())})
                )
            result = reproduce_m34(current, archive)
            self.assertEqual(result["source_kind"], "fresh M34 pipeline execution in this Actions run")
            self.assertEqual(result["archived_source_kind"], "inspection of frozen M34 Actions artifact")
            self.assertEqual(result["false_alarm_denominator"], {"reproduced": 5, "registered": 5})
            self.assertEqual(result["spades_failure_denominator"], {"reproduced": 4, "registered": 4})


if __name__ == "__main__":
    unittest.main()
