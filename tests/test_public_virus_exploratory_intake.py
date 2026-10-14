import copy
import hashlib
import json
import unittest
from pathlib import Path

from satellite_discovery import metadata_filter, public_virus, sequence_downloader
from satellite_discovery.public_virus_acquisition_preflight import fastq_manifest_sha256
from satellite_discovery.public_virus_exploratory_intake import (
    POLICY_ID, POLICY_SHA256, TARGET, _digest, evaluate_exploratory_intake,
)
from test_public_virus_acquisition_review import _SNAPSHOT_DIR, make_intake


ROOT = Path(__file__).parents[1]
EVIDENCE_PATH = ROOT / "docs" / "hcov-229e-exploratory-intake-evidence-v1.json"
APPROVAL_PATH = ROOT / "docs" / "hcov-229e-exploratory-scientific-approval-v1.json"


def valid_inputs():
    accession = make_intake(
        virus="hcov-229e", organism="Homo sapiens",
        attributes={"host": "Homo sapiens"},
    )
    record = accession["record"]
    record.update({
        "run_accession": TARGET["run"],
        "experiment_accession": TARGET["experiment"],
        "sample_accession": "SRS15776099",
        "biosample": TARGET["biosample"],
        "study_accession": TARGET["study"],
        "bioproject": TARGET["bioproject"],
        "platform": "ILLUMINA",
        "library_strategy": "RNA-Seq",
        "library_source": "TRANSCRIPTOMIC",
        "library_selection": "cDNA",
        "layout": "SINGLE",
        "raw_read_availability": "ena_fastq_listed",
        "fastq_ftp": "ftp.sra.ebi.ac.uk/vol1/fastq/SRR124/050/SRR12424250/SRR12424250.fastq.gz",
        "fastq_md5": "9ac379cab68b8b5e2862ec167e95d3c9",
        "fastq_bytes": "680887913",
    })
    record["public_virus"] = public_virus.assess_identity(record, "hcov-229e")
    assessed = metadata_filter.assess(dict(record), min_spots=0)
    record["technical_suitability"] = {
        "status": "eligible_for_review" if not assessed["exclusion_reasons"] else "excluded",
        "reasons": assessed["exclusion_reasons"],
        "warnings": assessed["warnings"],
        "archive_errors": [],
    }
    record["pilot_readiness"] = {
        "status": "held_for_identity_review", "reasons": ["sample_level_virus_identity_missing"],
    }
    record["fastq_assessment"] = {
        "status": "complete_within_budget", "complete": True,
        "total_bytes": 680887913, "budget_bytes": 1_000_000_000,
        "fits_budget": True, "reasons": [],
    }
    accession["manifest"]["record_sha256"] = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    approval = json.loads(APPROVAL_PATH.read_text(encoding="utf-8"))
    refresh_bindings(accession, evidence, approval)
    return accession, evidence, approval


def refresh_bindings(accession, evidence, approval):
    files = sequence_downloader.files_for_run(accession["record"])
    evidence["fastq_files"] = files
    evidence["fastq_manifest_sha256"] = fastq_manifest_sha256(files)
    approval["policy_identifier"] = POLICY_ID
    approval["policy_sha256"] = POLICY_SHA256
    approval["evidence_document_sha256"] = _digest(evidence)
    approval["fastq_manifest_sha256"] = fastq_manifest_sha256(files)


def evaluate(accession, evidence, approval):
    return evaluate_exploratory_intake(
        accession, _SNAPSHOT_DIR, evidence, approval,
    )


class ExploratoryIntakeTests(unittest.TestCase):
    def test_exact_run_is_only_a_non_authorizing_review_candidate(self):
        result = evaluate(*valid_inputs())
        self.assertEqual(result["result"], "candidate_for_scientific_review")
        self.assertEqual(result["scope"], TARGET)
        self.assertEqual(result["original_strict_policy"]["identity_status"], "insufficient")
        self.assertEqual(result["original_strict_policy"]["eligibility"], "HELD")
        self.assertEqual(result["exploratory_evidence_result"], "SUPPORTED")
        self.assertEqual(result["scientific_approval_status"], "NOT_APPROVED")
        self.assertEqual(result["sequence_confirmation_status"], "NOT_ASSESSED")
        self.assertFalse(result["authorizing"])
        self.assertFalse(result["acquisition_authorized"])
        self.assertFalse(result["download_enabled"])
        self.assertFalse(result["may_download"])

    def test_all_scope_and_evidence_adversaries_fail_closed(self):
        cases = []

        def case(name, mutate, rebind=False):
            cases.append((name, mutate, rebind))

        case("wrong_srr", lambda a, e, p: e["scope"].update(run="SRR00000000"), True)
        case("wrong_srx", lambda a, e, p: e["exposure_record"]["accessions"].update(experiment="SRX00000000"), True)
        case("wrong_biosample", lambda a, e, p: e["scope"].update(biosample="SAMN00000000"), True)
        case("wrong_geo_sample", lambda a, e, p: e["exposure_record"]["accessions"].update(geo_sample="GSM0000000"), True)
        case("wrong_study", lambda a, e, p: a["record"].update(study_accession="SRP000000"), True)
        case("wrong_bioproject", lambda a, e, p: a["record"].update(bioproject="PRJNA000000"), True)
        case("wrong_virus", lambda a, e, p: e["scope"].update(virus="HCoV-OC43"), True)
        case("different_treatment", lambda a, e, p: e["exposure_record"]["sample_treatment"].update(archive_annotation="Infected with HCoV-OC43 for 24 hours"), True)
        case("zero_hour", lambda a, e, p: e["exposure_record"]["sample_treatment"].update(timepoint_hours=0), True)
        case("mock_infected", lambda a, e, p: e["exposure_record"]["sample_treatment"].update(condition="REPORTED_MOCK", archive_annotation="Mock-infected control"), True)
        case("missing_publication", lambda a, e, p: e["exposure_record"]["sample_treatment"].update(publication_references=[]), True)
        case("missing_relationship", lambda a, e, p: e["exposure_record"]["accession_relationships"].pop("run_experiment"), True)
        case("contradictory_relationship", lambda a, e, p: e["exposure_record"]["accession_relationships"]["run_experiment"].update(object="SRX999999"), True)
        case("changed_archive_link", lambda a, e, p: a["record"].update(biosample="SAMN00000000"), True)
        case("withdrawn_metadata", lambda a, e, p: e.update(metadata_state="WITHDRAWN"), True)
        case("missing_manifest", lambda a, e, p: e.update(fastq_files=[]))
        case("changed_url", lambda a, e, p: a["record"].update(fastq_ftp="ftp.sra.ebi.ac.uk/vol1/fastq/SRR124/050/OTHER/SRR12424250.fastq.gz"), True)
        case("changed_md5", lambda a, e, p: a["record"].update(fastq_md5="0" * 32), True)
        case("changed_bytes", lambda a, e, p: a["record"].update(fastq_bytes="680887912"), True)
        case("changed_manifest_digest", lambda a, e, p: p.update(fastq_manifest_sha256="0" * 64))
        case("over_1gb", lambda a, e, p: a["record"].update(fastq_bytes="1000000001"), True)
        case("rejected_approval", lambda a, e, p: p.update(decision_status="REJECTED"))
        case("forged_approval", lambda a, e, p: p.update(decision_status="APPROVED"))
        case("malformed_approval_state", lambda a, e, p: p.update(decision_status=[]))
        case("approval_for_another_run", lambda a, e, p: p["scope"].update(run="SRR00000000"))
        case("approval_for_another_policy", lambda a, e, p: p.update(policy_identifier="public-virus-v1"))
        case("attempted_acquisition", lambda a, e, p: p.update(acquisition_authorized=True))
        case("attempted_sequence_promotion", lambda a, e, p: e.update(sequence_confirmation_status="SUPPORTED"), True)
        case("nested_sequence_promotion", lambda a, e, p: e["exposure_record"].update(sequence_confirmation_status="SUPPORTED"), True)
        case("strict_gate_bypass", lambda a, e, p: a["record"].update(pilot_readiness={"status": "eligible_for_review", "reasons": []}), True)

        for name, mutate, rebind in cases:
            with self.subTest(case=name):
                accession, evidence, approval = valid_inputs()
                mutate(accession, evidence, approval)
                if rebind:
                    accession["manifest"]["record_sha256"] = hashlib.sha256(
                        json.dumps(accession["record"], sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest()
                    refresh_bindings(accession, evidence, approval)
                result = evaluate(accession, evidence, approval)
                self.assertIn(result["result"], {"blocked", "held_pending_approval"})
                self.assertFalse(result["authorizing"])
                self.assertFalse(result["acquisition_authorized"])
                self.assertFalse(result["download_enabled"])
                self.assertFalse(result["may_download"])

    def test_missing_approval_stays_held_and_never_authorizes(self):
        accession, evidence, _ = valid_inputs()
        result = evaluate(accession, evidence, None)
        self.assertEqual(result["result"], "held_pending_approval")
        self.assertEqual(result["scientific_approval_status"], "NOT_APPROVED")
        self.assertFalse(result["acquisition_authorized"])

    def test_evidence_or_record_digest_tampering_blocks(self):
        accession, evidence, approval = valid_inputs()
        evidence["scope"]["run"] = "SRR00000000"
        result = evaluate(accession, evidence, approval)
        self.assertEqual(result["result"], "blocked")
        accession, evidence, approval = valid_inputs()
        accession["record"]["fastq_bytes"] = "1"
        result = evaluate(accession, evidence, approval)
        self.assertEqual(result["result"], "blocked")

    def test_result_never_promotes_sequence_or_changes_current_policy(self):
        accession, evidence, approval = valid_inputs()
        result = evaluate(accession, evidence, approval)
        self.assertEqual(result["original_strict_policy"]["version"], "public-virus-v1")
        self.assertEqual(result["current_eligibility"], "HELD")
        self.assertEqual(result["eligibility_effect"], "NONE")
        self.assertEqual(result["sequence_confirmation_status"], "NOT_ASSESSED")

    def test_checked_in_pending_approval_binds_to_policy_evidence_and_manifest(self):
        evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        approval = json.loads(APPROVAL_PATH.read_text(encoding="utf-8"))
        policy = json.loads((ROOT / "satellite_discovery" /
                             "public_virus_exploratory_intake_policy.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(approval["policy_sha256"], _digest(policy))
        self.assertEqual(approval["evidence_document_sha256"], _digest(evidence))
        self.assertEqual(approval["fastq_manifest_sha256"], evidence["fastq_manifest_sha256"])
        self.assertEqual(approval["decision_status"], "NOT_APPROVED")
        self.assertIsNone(approval["owner_identifier"])
        self.assertIsNone(approval["independent_reviewer_identifier"])
        self.assertEqual(evaluate(*valid_inputs())["result"], "candidate_for_scientific_review")


if __name__ == "__main__":
    unittest.main()
