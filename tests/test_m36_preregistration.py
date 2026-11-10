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

    def test_family_splits_and_opaque_case_ids_are_complete(self):
        units = self.design["experimental_units"]
        families = units["families"]
        self.assertEqual(units["independent_families"], 12)
        self.assertEqual(len(families), 12)
        self.assertEqual(sum(units["family_split_counts"].values()), 12)
        self.assertEqual(set(units["family_split_counts"]), {"development", "tuning", "held_out"})
        self.assertEqual(
            {split: sum(row["split"] == split for row in families) for split in units["family_split_counts"]},
            units["family_split_counts"],
        )
        self.assertEqual(len({row["sequence_seed"] for row in families}), 12)
        self.assertEqual(len({row["read_seed_root"] for row in families}), 12)
        self.assertTrue(units["held_out_truth_in_analysis_inputs"] is False)
        self.assertTrue(units["technical_repeat_is_independent_unit"] is False)
        family_ids = [row["family_id"] for row in families]
        self.assertEqual(len(family_ids), len(set(family_ids)))
        self.assertTrue(all(re.fullmatch(r"m36x\d{4}", value) for value in family_ids))
        self.assertEqual(units["analysis_case_id_pattern"], "m36x####-c##-r##")
        case_ids = [
            f"m36x{index:04d}-c{condition:02d}-r{repeat:02d}"
            for index in range(1, 13)
            for condition in range(1, self.design["matrix"][0]["condition_count_per_family"] + 1)
            for repeat in range(1, 3)
        ]
        self.assertEqual(len(case_ids), 216)
        self.assertTrue(all(re.fullmatch(r"m36x\d{4}-c\d{2}-r\d{2}", value) for value in case_ids))
        for leaked in ("held_out", "positive", "negative", "coverage", "substitution"):
            self.assertFalse(any(leaked in value for value in case_ids))

    def test_matrix_counts_and_budget_reconcile(self):
        blocks = {row["block_id"]: row for row in self.design["matrix"]}
        self.assertEqual(
            sum(row["planned_family_condition_units"] for row in blocks.values()),
            self.design["planned_totals"]["family_condition_units"],
        )
        self.assertEqual(
            sum(row["planned_assembly_executions"] for row in blocks.values()),
            self.design["planned_totals"]["assembly_executions_max"],
        )
        for row in blocks.values():
            self.assertEqual(
                row["planned_assembly_executions"],
                row["planned_family_condition_units"]
                * row["technical_repeats_per_condition"]
                if "technical_repeats_per_condition" in row
                else row["planned_family_condition_units"]
                * row["technical_repeats_per_assembler_arm"],
            )
        totals = self.design["planned_totals"]
        self.assertEqual(totals["maximum_cpu_hours"], totals["assembly_executions_max"] * totals["attempt_timeout_seconds"] / 3600)
        self.assertEqual(totals["maximum_concurrent_jobs"], 4)

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
