import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = ROOT / "docs/M36_POSITIVE_CONTROL_ASSEMBLY_INVESTIGATION.json"
REPORT_PATH = ROOT / "docs/M36_POSITIVE_CONTROL_ASSEMBLY_INVESTIGATION.md"


class M36PreregistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = json.loads(DESIGN_PATH.read_text(encoding="utf-8"))
        cls.report = REPORT_PATH.read_text(encoding="utf-8")

    def test_phase_is_design_only_and_governance_remains_closed(self):
        self.assertEqual(self.design["status"], "DESIGN_ONLY")
        self.assertTrue(self.design["design_only"])
        self.assertFalse(self.design["governance"]["m36_experiments_executed"])
        self.assertFalse(self.design["governance"]["biological_execution_authorized"])
        self.assertFalse(self.design["governance"]["production_promotion"])
        self.assertFalse(self.design["future_actions_plan"]["enabled_in_phase1"])
        self.assertIn("Do not execute", self.report)

    def test_family_registry_keeps_split_mapping_restricted(self):
        units = self.design["experimental_units"]
        families = units["families"]
        tokens = [row["family_id"] for row in families]
        self.assertEqual(units["independent_families"], 12)
        self.assertEqual(len(families), 12)
        self.assertEqual(sum(units["family_split_counts"].values()), 12)
        self.assertEqual(set(units["family_split_counts"]), {"development", "tuning", "held_out"})
        self.assertEqual(len(set(tokens)), 12)
        self.assertTrue(all(set(row) == {"family_id"} for row in families))
        self.assertTrue(all(re.fullmatch(r"f\d{2}", token) for token in tokens))
        self.assertTrue(units["held_out_truth_in_analysis_inputs"] is False)
        self.assertTrue(units["technical_repeat_is_independent_unit"] is False)
        self.assertEqual(set(self.design["registered_case_manifest"]["families"]), set(tokens))
        sidecar = self.design["registered_case_manifest"]["restricted_evaluation_sidecar"]
        self.assertIn("family-to-split mapping", sidecar["contains"])
        self.assertIn("truth sequences", sidecar["contains"])
        self.assertIn("split_seed_and_truth_mapping", units)

    def test_analysis_visible_identifier_contract_is_opaque(self):
        manifest = self.design["registered_case_manifest"]
        self.assertEqual(manifest["analysis_visible_case_id_pattern"], r"case-[a-f0-9]{24}")
        self.assertEqual(manifest["analysis_visible_stage_id_pattern"], r"stage-[a-f0-9]{24}-s[0-9]{2}")
        for key in ("analysis_visible_case_ids", "analysis_visible_header_rule", "analysis_visible_log_rule"):
            self.assertTrue(manifest[key])
        sidecar = manifest["restricted_evaluation_sidecar"]
        self.assertIn("opaque-case-to-registered-case mapping", sidecar["contains"])
        self.assertIn("independent reviewer authorizes locked unblinding", sidecar["unblinding_point"])
        for block in manifest["blocks"]:
            for value in block["family_ids"] + block["condition_ids"]:
                self.assertFalse(re.search(r"held.?out|positive|negative|coverage|substitution", value, re.I))

    def test_matrix_counts_and_budget_reconcile(self):
        blocks = {row["block_id"]: row for row in self.design["matrix"]}
        registry = self.design["registered_case_manifest"]
        repeats = len(registry["repeat_ids"])
        derived = {}
        for block in registry["blocks"]:
            units = len(block["family_ids"]) * len(block["condition_ids"]) * len(block["assembler_ids"])
            executions = units * repeats
            derived[block["block_id"]] = (units, executions)
            row = blocks[block["block_id"]]
            self.assertEqual(row["planned_family_condition_units"], units)
            self.assertEqual(row["planned_assembly_executions"], executions)
            self.assertEqual(row["family_count"], len(block["family_ids"]))
            self.assertEqual(row["condition_count_per_family"], len(block["condition_ids"]))
            self.assertEqual(row.get("assembler_count", len(block["assembler_ids"])), len(block["assembler_ids"]))
            if "conditions" in row:
                self.assertEqual(len(row["conditions"]), len(block["condition_ids"]))
        self.assertEqual(
            sum(units for units, _ in derived.values()),
            self.design["planned_totals"]["family_condition_units"],
        )
        self.assertEqual(
            sum(executions for _, executions in derived.values()),
            self.design["planned_totals"]["assembly_executions_max"],
        )
        totals = self.design["planned_totals"]
        self.assertEqual(totals["aggregate_attempt_slot_hours"], totals["assembly_executions_max"] * totals["attempt_timeout_seconds"] / 3600)
        self.assertEqual(totals["estimated_cpu_hours_at_one_vcpu_per_attempt"], totals["aggregate_attempt_slot_hours"])
        self.assertEqual(totals["maximum_concurrent_jobs"], 4)
        self.assertEqual(sum(totals["wall_budget_allocation_hours"].values()), totals["wall_time_budget_hours"])
        diagnostic = blocks["spades_error_diagnostic"]
        self.assertFalse(any("low_complexity" in condition for condition in diagnostic["conditions"]))
        self.assertIn("low_complexity_stress_sequence", blocks["positive_recovery"]["conditions"])

    def test_target_absent_controls_are_fully_counted(self):
        control = next(row for row in self.design["matrix"] if row["block_id"] == "target_absent_controls")
        registry = next(row for row in self.design["registered_case_manifest"]["blocks"] if row["block_id"] == "target_absent_controls")
        self.assertEqual(set(registry["family_ids"]), set(self.design["registered_case_manifest"]["families"]))
        self.assertEqual(len(registry["condition_ids"]), 1)
        self.assertEqual(len(self.design["registered_case_manifest"]["repeat_ids"]), 2)
        self.assertEqual(control["planned_family_condition_units"], 12)
        self.assertEqual(control["planned_assembly_executions"], 24)
        self.assertFalse(control["included_in_original_464_execution_estimate"])

    def test_paired_assembler_design_preserves_family_independence(self):
        block = next(row for row in self.design["matrix"] if row["block_id"] == "alternative_assemblers")
        self.assertEqual(block["family_count"], 8)
        self.assertIn("byte-identical FASTQ", block["paired_input_rule"])
        self.assertIn("independently simulated reads", block["paired_input_rule"])
        self.assertIn("development", block["exploratory_role"].lower())
        self.assertIn("locked final paired comparison", block["held_out_role"].lower())
        self.assertIn("four family-level differences", self.design["analysis"]["paired_comparison"])
        self.assertIn("median and range", self.design["analysis"]["paired_comparison"])

    def test_frozen_settings_and_m35_findings_are_not_rewritten(self):
        baseline = self.design["frozen_baseline"]
        self.assertEqual(baseline["target_length_nt"], 900)
        self.assertEqual(baseline["nominal_coverage"], 48)
        self.assertEqual(baseline["read_length_nt"], 100)
        self.assertEqual(baseline["substitution_rate"], 0.02)
        self.assertEqual(baseline["insertion_rate"], 0.01)
        self.assertEqual(baseline["deletion_rate"], 0.01)
        evidence = self.design["source_evidence"]
        self.assertEqual(evidence["positive_controls"]["unevaluable"], 3)
        self.assertEqual(evidence["spades"]["failed"], 26)
        self.assertEqual(evidence["spades"]["executions"], 28)
        self.assertFalse(evidence["spades"]["mechanism_resolved"])
        governance = self.design["governance"]
        self.assertFalse(governance["m6_settings_changed"])
        self.assertFalse(governance["m8_settings_changed"])
        self.assertFalse(governance["m31_thresholds_changed"])
        self.assertFalse(governance["m34_m35_results_modified"])

    def test_failures_unevaluable_and_not_run_are_distinct(self):
        statuses = set(self.design["failure_classifications"])
        self.assertTrue({
            "ASSEMBLY_EXECUTION_FAILED",
            "ASSEMBLY_INTERRUPTED",
            "UNEVALUABLE_NO_SUPPORTED_ASSEMBLY",
            "NOT_RUN_WITH_BLOCKER",
            "COMPLETE",
        } <= statuses)
        self.assertFalse(self.design["analysis"]["missing_data"].lower().startswith("impute"))
        self.assertFalse(self.design["analysis"]["threshold_tuning"])
        self.assertFalse(self.design["analysis"]["biological_sensitivity_specificity_claims"])

    def test_alternative_assemblers_are_namespaced_and_version_bound(self):
        block = next(row for row in self.design["matrix"] if row["block_id"] == "alternative_assemblers")
        self.assertTrue(block["namespace_required"])
        self.assertTrue(block["not_run_if_tool_identity_or_input_compatibility_unresolved"])
        self.assertEqual({tool["id"] for tool in block["assemblers"]}, {"spades", "tadpole"})
        self.assertIn("SHA-256", block["assemblers"][0]["version_requirement"])
        self.assertIn("40.01", block["assemblers"][1]["version_requirement"])
        self.assertIn("does not replace M6's configured assembler", self.report)

    def test_actions_plan_is_future_only_and_evidence_bound(self):
        plan = self.design["future_actions_plan"]
        self.assertFalse(plan["enabled_in_phase1"])
        self.assertEqual(plan["maximum_parallelism"], 4)
        self.assertEqual(plan["timeout_seconds_per_attempt"], 180)
        self.assertTrue({"design", "source_commit", "generator", "inputs", "tool executables", "raw outputs", "artifact inventory", "archive"} <= set(plan["required_hashes"]))
        self.assertIn("m36_experiments_executed=false", self.report)
        self.assertIn("phase1_design_only=true", self.report)

    def test_phase2_requires_independent_review_and_explicit_authorization(self):
        gates = " ".join(self.design["acceptance_gates_for_phase2"]).lower()
        self.assertIn("independent scientific review", gates)
        self.assertIn("user explicitly authorizes", gates)
        self.assertIn("held-out truth", gates)
        self.assertIn("exact executable versions and hashes", gates)
        self.assertIn("biological execution and production promotion", self.report.lower())


if __name__ == "__main__":
    unittest.main()
