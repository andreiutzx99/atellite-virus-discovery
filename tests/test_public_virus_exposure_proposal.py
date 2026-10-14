import copy
import json
import unittest
from pathlib import Path

from satellite_discovery.public_virus import POLICY, assess_identity
from satellite_discovery.public_virus_exposure_proposal import (
    CONDITIONS, EVIDENCE_STATUSES, evaluate_document, evaluate_exposure_record,
)


ROOT = Path(__file__).parents[1]
CASE = ROOT / "docs" / "public-virus-exposure-policy-proposal-v1.json"


def valid_record():
    refs = {
        "run_info": {"url": "https://example.org/runinfo/SRR1", "retrieved_at": "2026-10-14"},
        "ena": {"url": "https://example.org/ena/SRR1", "retrieved_at": "2026-10-14"},
        "biosample": {"url": "https://example.org/biosample/SAMN1", "retrieved_at": "2026-10-14"},
        "geo": {"url": "https://example.org/geo/GSM1", "retrieved_at": "2026-10-14"},
        "publication": {"url": "https://doi.org/10.0000/example", "retrieved_at": "2026-10-14"},
    }
    return {
        "accessions": {"run": "SRR1", "experiment": "SRX2",
                       "biosample": "SAMN1", "geo_sample": "GSM1"},
        "source_references": refs,
        "accession_relationships": {
            "run_experiment": {"subject": "SRR1", "object": "SRX2",
                               "status": "SUPPORTED", "source_references": ["run_info", "ena"]},
            "experiment_biosample": {"subject": "SRX2", "object": "SAMN1",
                                     "status": "SUPPORTED", "source_references": ["run_info", "biosample"]},
            "biosample_geo_sample": {"subject": "SAMN1", "object": "GSM1",
                                     "status": "SUPPORTED", "source_references": ["biosample", "geo"]},
        },
        "metadata_state": "CURRENT",
        "conflict_assessment": {"status": "NONE"},
        "sample_treatment": {
            "reported_virus": "HCoV-229E", "condition": "REPORTED_INFECTED",
            "archive_annotation": "Infected with HCoV-229E virus for 6 hours",
            "timepoint_hours": 6,
            "source_references": ["geo", "biosample"],
            "publication_references": ["publication"],
        },
        "biological_independence": {"status": "UNKNOWN"},
        "review": {"status": "NOT_REVIEWED", "reviewers": []},
        "current_identity_status": "INSUFFICIENT",
        "sequence_confirmation_status": "NOT_ASSESSED",
        "requested_eligibility": "HELD",
    }


class ExposureProposalTests(unittest.TestCase):
    def test_positive_sample_level_accession_linked_exposure(self):
        result = evaluate_exposure_record(valid_record())
        self.assertEqual(result["study_reported_experimental_exposure"], "SUPPORTED")
        self.assertEqual(result["experimental_condition"], "REPORTED_INFECTED")

    def test_missing_treatment_is_insufficient(self):
        record = valid_record()
        record.pop("sample_treatment")
        self.assertEqual(evaluate_exposure_record(record)["study_reported_experimental_exposure"],
                         "INSUFFICIENT")

    def test_sra_mapping_conflict_fails_closed(self):
        record = valid_record()
        record["accession_relationships"]["run_experiment"]["object"] = "SRX999"
        self.assertEqual(evaluate_exposure_record(record)["study_reported_experimental_exposure"],
                         "INSUFFICIENT")

    def test_different_virus_is_conflicted(self):
        record = valid_record()
        record["sample_treatment"]["reported_virus"] = "HCoV-OC43"
        record["sample_treatment"]["archive_annotation"] = "Infected with HCoV-OC43"
        self.assertEqual(evaluate_exposure_record(record)["study_reported_experimental_exposure"],
                         "CONFLICTED")

    def test_study_level_claim_without_sample_treatment_is_insufficient(self):
        record = valid_record()
        record["sample_treatment"]["source_references"] = []
        self.assertEqual(evaluate_exposure_record(record)["study_reported_experimental_exposure"],
                         "INSUFFICIENT")

    def test_human_host_or_archive_identity_does_not_replace_exposure_evidence(self):
        record = valid_record()
        record["current_identity_status"] = "INSUFFICIENT"
        result = evaluate_exposure_record(record)
        self.assertEqual(result["archive_declared_identity"], "INSUFFICIENT")
        self.assertEqual(result["study_reported_experimental_exposure"], "SUPPORTED")

    def test_explicit_mock_is_not_infected_exposure(self):
        record = valid_record()
        record["sample_treatment"].update(
            condition="REPORTED_MOCK", archive_annotation="Mock-infected control",
        )
        result = evaluate_exposure_record(record)
        self.assertEqual(result["experimental_condition"], "REPORTED_MOCK")
        self.assertEqual(result["study_reported_experimental_exposure"], "INSUFFICIENT")

    def test_reported_untreated_stays_untreated_not_mock(self):
        record = valid_record()
        record["sample_treatment"].update(
            condition="REPORTED_UNTREATED", archive_annotation="Untreated", timepoint_hours=0,
        )
        result = evaluate_exposure_record(record)
        self.assertEqual(result["experimental_condition"], "REPORTED_UNTREATED")
        self.assertEqual(result["study_reported_experimental_exposure"], "INSUFFICIENT")

    def test_zero_hour_untreated_is_unresolved_baseline(self):
        record = valid_record()
        record["sample_treatment"].update(
            condition="UNRESOLVED_BASELINE", archive_annotation="Untreated", timepoint_hours=0,
        )
        result = evaluate_exposure_record(record)
        self.assertEqual(result["experimental_condition"], "UNRESOLVED_BASELINE")
        self.assertEqual(result["study_reported_experimental_exposure"], "INSUFFICIENT")

    def test_replicate_labels_do_not_establish_biological_independence(self):
        record = valid_record()
        record["biological_independence"] = {"status": "UNKNOWN", "label": "R1"}
        self.assertEqual(evaluate_exposure_record(record)["biological_independence"], "UNKNOWN")

    def test_two_runs_linked_to_one_biosample_do_not_imply_independence(self):
        first = valid_record()
        second = valid_record()
        second["accessions"].update(run="SRR3", experiment="SRX4")
        second["accession_relationships"]["run_experiment"].update(
            subject="SRR3", object="SRX4",
        )
        second["accession_relationships"]["experiment_biosample"].update(
            subject="SRX4",
        )
        results = [evaluate_exposure_record(first), evaluate_exposure_record(second)]
        self.assertEqual({r["biological_independence"] for r in results}, {"UNKNOWN"})

    def test_publication_archive_conflict_is_preserved(self):
        record = valid_record()
        record["conflict_assessment"] = {"status": "CONFLICTED"}
        self.assertEqual(evaluate_exposure_record(record)["study_reported_experimental_exposure"],
                         "CONFLICTED")

    def test_changed_or_withdrawn_sources_require_reassessment(self):
        for state in ("CHANGED", "WITHDRAWN"):
            record = valid_record()
            record["metadata_state"] = state
            with self.subTest(state=state):
                self.assertEqual(
                    evaluate_exposure_record(record)["study_reported_experimental_exposure"],
                    "CONFLICTED",
                )

    def test_missing_source_references_is_insufficient(self):
        record = valid_record()
        record["source_references"].pop("publication")
        self.assertEqual(evaluate_exposure_record(record)["study_reported_experimental_exposure"],
                         "INSUFFICIENT")

    def test_missing_reviewers_cannot_claim_independent_agreement(self):
        record = valid_record()
        record["review"] = {"status": "AGREEMENT", "reviewers": ["one"]}
        result = evaluate_exposure_record(record)
        self.assertEqual(result["review_status"], "NOT_REVIEWED")
        self.assertIn("two_distinct_reviewer_records_missing", result["reasons"])

    def test_claimed_sequence_confirmation_is_never_inferred_from_metadata(self):
        record = valid_record()
        record["sequence_confirmation_status"] = "SUPPORTED"
        result = evaluate_exposure_record(record)
        self.assertEqual(result["sequence_confirmed_viral_presence"], "NOT_ASSESSED")

    def test_held_run_cannot_be_promoted_by_proposal(self):
        record = valid_record()
        record["requested_eligibility"] = "ELIGIBLE"
        result = evaluate_exposure_record(record)
        self.assertEqual(result["current_eligibility"], "HELD")
        self.assertEqual(result["eligibility_effect"], "NONE")
        self.assertFalse(result["authorizing"])
        self.assertFalse(result["acquisition_enabled"])
        self.assertIn("proposal_cannot_change_current_eligibility", result["reasons"])

    def test_case_study_counts_and_contract_boundaries(self):
        document = json.loads(CASE.read_text(encoding="utf-8"))
        results = evaluate_document(document)
        previous = json.loads(
            (ROOT / "docs" / "hcov-229e-identity-evidence-review-v1.json")
            .read_text(encoding="utf-8")
        )
        original = {run["run"]: run for run in previous["runs"]}
        self.assertEqual(len(results), 15)
        evaluation_rows = document["evaluations"]
        self.assertEqual(len(evaluation_rows), 15)
        for result, case in zip(results, document["records"]):
            prior = original[result["run_accession"]]
            self.assertEqual(case["accessions"], {
                "run": prior["run"], "experiment": prior["experiment"],
                "biosample": prior["biosample"], "geo_sample": prior["geo_sample"],
            })
            self.assertEqual(case["fastq_bytes"], prior["fastq_bytes"])
            self.assertEqual(case["fastq_md5"], prior["fastq_md5"])
            self.assertEqual(case["sample_treatment"]["archive_annotation"], prior["treatment"])
            self.assertEqual(case["current_identity_status"], prior["archive_identity"])
            self.assertEqual(case["sequence_confirmation_status"], prior["sequence_presence"])
            self.assertEqual(case["requested_eligibility"], prior["current_policy"])
        for result, expected in zip(results, evaluation_rows):
            self.assertEqual(expected, {
                "run": result["run_accession"],
                "current_identity": result["archive_declared_identity"],
                "reported_exposure": result["study_reported_experimental_exposure"],
                "condition": result["experimental_condition"],
                "sequence_presence": result["sequence_confirmed_viral_presence"],
                "eligibility": result["current_eligibility"],
                "independence": result["biological_independence"],
            })
        self.assertEqual(sum(r["study_reported_experimental_exposure"] == "SUPPORTED"
                             for r in results), 12)
        self.assertEqual(sum(r["experimental_condition"] == "UNRESOLVED_BASELINE"
                             for r in results), 3)
        self.assertTrue(all(r["current_eligibility"] == "HELD" for r in results))
        self.assertTrue(all(r["eligibility_effect"] == "NONE" for r in results))
        self.assertTrue(all(r["sequence_confirmed_viral_presence"] == "NOT_ASSESSED"
                            for r in results))
        self.assertEqual(POLICY["policy_version"], "public-virus-v1")
        self.assertEqual(POLICY["viruses"]["hcov-229e"]["identity_attribute_keys"], [
            "virus", "virus species", "infecting virus", "viral species", "pathogen",
        ])
        identity = assess_identity(
            {"organism": "Homo sapiens", "attributes": {"host": "Homo sapiens"}},
            "hcov-229e",
        )
        self.assertEqual(identity["status"], "insufficient")

    def test_evaluation_is_deterministic_and_status_vocabularies_are_explicit(self):
        document = json.loads(CASE.read_text(encoding="utf-8"))
        self.assertEqual(evaluate_document(document), evaluate_document(copy.deepcopy(document)))
        self.assertEqual(EVIDENCE_STATUSES,
                         {"SUPPORTED", "INSUFFICIENT", "CONFLICTED", "NOT_ASSESSED"})
        self.assertEqual(CONDITIONS, {
            "REPORTED_INFECTED", "REPORTED_MOCK", "REPORTED_UNTREATED",
            "UNRESOLVED_BASELINE", "OTHER", "UNKNOWN",
        })

    def test_document_rejects_activation_and_invalid_accession_namespaces(self):
        document = json.loads(CASE.read_text(encoding="utf-8"))
        activated = copy.deepcopy(document)
        activated["acquisition_enabled"] = True
        with self.assertRaises(ValueError):
            evaluate_document(activated)
        record = valid_record()
        record["accessions"]["run"] = "not-a-run"
        self.assertEqual(
            evaluate_exposure_record(record)["study_reported_experimental_exposure"],
            "INSUFFICIENT",
        )


if __name__ == "__main__":
    unittest.main()
