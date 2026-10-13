"""Synthetic contract tests; they are not biological validation."""
import unittest
from unittest.mock import patch

import satellite_discovery.public_virus_provenance as provenance
from satellite_discovery.public_virus_provenance import (
    SCHEMA,
    ProvenanceValidationError,
    assess_independence,
    create_document,
    serialize_document,
    stable_evidence_id,
    validate_document,
)


def entity(entity_id, entity_type="sra_run", **fields):
    return {"entity_id": entity_id, "entity_type": entity_type, **fields}


def edge(rid, left, right, kind="derived_from", evidence=None):
    return {
        "relationship_id": rid, "relationship_type": kind,
        "subject": left, "object": right,
        "evidence": evidence or [ev()],
    }


def ev(source="curator_decision", review="accepted", dimension=None,
       assessment=None, **fields):
    result = {
        "source": source, "evidence_type": "synthetic_example",
        "review_state": review, "uncertainty": "Synthetic test evidence only.",
        "statement": "Synthetic contract fixture; not a biological observation.",
    }
    if dimension is not None:
        result["dimension"] = dimension
        result["assessment"] = assessment
        if review == "accepted" and source == "curator_decision":
            result["audit_reference"] = {
                "reviewer_id": "curator:test-reviewer",
                "decision_id": "decision:test-001",
                "decision_rationale": "Synthetic test rationale.",
            }
        elif review == "accepted" and source == "publication_assertion":
            result["audit_reference"] = {
                "publication_ref": "doi:10.0000/synthetic",
                "source_locator": "Results, paragraph 1",
            }
    result.update(fields)
    return result


def decision_edge(rid, left, right, dimension, assessment, **kwargs):
    return edge(
        rid, left, right, "independence_assessment",
        [ev(dimension=dimension, assessment=assessment, **kwargs)],
    )


class PublicVirusProvenanceTests(unittest.TestCase):
    def test_two_runs_from_one_sra_sample_do_not_imply_independence(self):
        graph = create_document(
            [entity("run-a"), entity("run-b"),
             entity("exp-a", "sra_experiment"), entity("exp-b", "sra_experiment"),
             entity("sra-sample", "sra_sample")],
            [
                edge("r-a-exp", "run-a", "exp-a", "run_of_experiment"),
                edge("r-b-exp", "run-b", "exp-b", "run_of_experiment"),
                edge("exp-a-sample", "exp-a", "sra-sample", "experiment_uses_archive_sample"),
                edge("exp-b-sample", "exp-b", "sra-sample", "experiment_uses_archive_sample"),
            ],
        )
        for dimension in ("sequencing", "biological_sample", "original_viral_isolate"):
            self.assertEqual(assess_independence(graph, "run-a", "run-b", dimension), "UNKNOWN")

    def test_multiple_experiments_from_one_sample_do_not_imply_independence(self):
        graph = create_document(
            [entity("exp-a", "sra_experiment"), entity("exp-b", "sra_experiment"),
             entity("sample", "sra_sample")],
            [
                edge("a-sample", "exp-a", "sample", "experiment_uses_archive_sample"),
                edge("b-sample", "exp-b", "sample", "experiment_uses_archive_sample"),
            ],
        )
        self.assertEqual(assess_independence(graph, "exp-a", "exp-b", "biological_sample"), "UNKNOWN")

    def test_technical_sequencing_replicates_are_not_sequence_independent_when_assessed(self):
        graph = create_document(
            [entity("a"), entity("b")],
            [
                edge("tech-rep", "a", "b", "technical_replicate_of"),
                decision_edge("seq-assessment", "a", "b", "sequencing", "same"),
            ],
        )
        self.assertEqual(assess_independence(graph, "a", "b", "sequencing"), "NOT_INDEPENDENT")
        self.assertEqual(assess_independence(graph, "a", "b", "biological_sample"), "UNKNOWN")

    def test_distinct_preparations_need_explicit_evidence_per_dimension(self):
        graph = create_document(
            [entity("prep-a", "preparation_event"), entity("prep-b", "preparation_event")],
            [decision_edge("prep-assessment", "prep-a", "prep-b",
                           "library_preparation", "different")],
        )
        self.assertEqual(assess_independence(graph, "prep-a", "prep-b", "library_preparation"),
                         "INDEPENDENT")
        self.assertEqual(assess_independence(graph, "prep-a", "prep-b", "biological_sample"),
                         "UNKNOWN")

    def test_separate_infections_using_one_stock_are_not_independent_origins(self):
        graph = create_document(
            [entity("infection-a", "infection_event"), entity("infection-b", "infection_event"),
             entity("stock", "viral_isolate_or_stock")],
            [
                edge("a-stock", "infection-a", "stock", "prepared_from_stock"),
                edge("b-stock", "infection-b", "stock", "prepared_from_stock"),
                decision_edge("infection-independent", "infection-a", "infection-b",
                              "experimental_or_infection", "different"),
                decision_edge("origin-same", "infection-a", "infection-b",
                              "viral_stock_or_lineage", "same"),
            ],
        )
        self.assertEqual(assess_independence(graph, "infection-a", "infection-b",
                                             "experimental_or_infection"), "INDEPENDENT")
        self.assertEqual(assess_independence(graph, "infection-a", "infection-b",
                                             "viral_stock_or_lineage"), "NOT_INDEPENDENT")
        self.assertEqual(assess_independence(graph, "infection-a", "infection-b",
                                             "original_viral_isolate"), "UNKNOWN")

    def test_different_strains_sharing_stock_lineage_are_not_distinct_origins(self):
        graph = create_document(
            [entity("strain-a", "viral_isolate_or_stock"),
             entity("strain-b", "viral_isolate_or_stock"),
             entity("lineage", "viral_isolate_or_stock")],
            [
                edge("a-lineage", "strain-a", "lineage", "derived_from"),
                edge("b-lineage", "strain-b", "lineage", "derived_from"),
                decision_edge("lineage-same", "strain-a", "strain-b",
                              "viral_stock_or_lineage", "same"),
            ],
        )
        self.assertEqual(assess_independence(graph, "strain-a", "strain-b",
                                             "viral_stock_or_lineage"), "NOT_INDEPENDENT")
        self.assertEqual(assess_independence(graph, "strain-a", "strain-b",
                                             "original_viral_isolate"), "UNKNOWN")

    def test_different_isolates_with_unknown_ancestry_stay_unknown(self):
        graph = create_document([entity("isolate-a", "viral_isolate_or_stock"),
                                 entity("isolate-b", "viral_isolate_or_stock")], [])
        self.assertEqual(assess_independence(graph, "isolate-a", "isolate-b",
                                             "original_viral_isolate"), "UNKNOWN")

    def test_two_studies_sharing_original_material_are_not_independent_origins(self):
        graph = create_document(
            [entity("study-a", "sra_study"), entity("study-b", "sra_study"),
             entity("material", "biological_material", identity_state="confirmed",
                    identifiers={"curator_material_id": "MAT-A"},
                    identity_evidence=[ev()])],
            [
                edge("study-a-material", "study-a", "material", "derived_from"),
                edge("study-b-material", "study-b", "material", "derived_from"),
                decision_edge("same-origin", "study-a", "study-b",
                              "original_viral_isolate", "same"),
            ],
        )
        self.assertEqual(assess_independence(graph, "study-a", "study-b",
                                             "original_viral_isolate"), "NOT_INDEPENDENT")

    def test_conflicting_metadata_is_reported_as_conflicting(self):
        graph = create_document(
            [entity("a"), entity("b")],
            [
                decision_edge("claim-same", "a", "b", "biological_sample", "same"),
                decision_edge("claim-different", "a", "b", "biological_sample", "different"),
            ],
        )
        self.assertEqual(assess_independence(graph, "a", "b", "biological_sample"),
                         "CONFLICTING")

    def test_missing_origin_evidence_is_unknown(self):
        graph = create_document([entity("a"), entity("b")], [])
        self.assertEqual(assess_independence(graph, "a", "b", "original_viral_isolate"),
                         "UNKNOWN")

    def test_repeated_processing_does_not_establish_independence(self):
        graph = create_document(
            [entity("source-material", "biological_material", identity_state="provisional",
                    identifiers={"local_id": "MAT-1"}),
             entity("prep-a", "preparation_event"), entity("prep-b", "preparation_event")],
            [
                edge("prep-a-derived", "prep-a", "source-material", "derived_from"),
                edge("prep-b-derived", "prep-b", "source-material", "derived_from"),
            ],
        )
        self.assertEqual(assess_independence(graph, "prep-a", "prep-b", "biological_sample"),
                         "UNKNOWN")

    def test_proposed_or_unknown_assessments_do_not_become_decisions(self):
        graph = create_document(
            [entity("a"), entity("b")],
            [decision_edge("proposed", "a", "b", "sequencing", "different",
                           review="proposed")],
        )
        self.assertEqual(assess_independence(graph, "a", "b", "sequencing"), "UNKNOWN")

    def test_uncertain_relationships_are_not_transitive(self):
        graph = create_document(
            [entity("a"), entity("b"), entity("c")],
            [
                decision_edge("a-b", "a", "b", "original_viral_isolate", "same"),
                edge("b-c", "b", "c", evidence=[ev(review="proposed")]),
            ],
        )
        self.assertEqual(assess_independence(graph, "a", "c", "original_viral_isolate"),
                         "UNKNOWN")

    def test_archive_accession_never_creates_biological_material_identity(self):
        with self.assertRaisesRegex(ProvenanceValidationError, "archive accessions"):
            create_document(
                [entity("material", "biological_material",
                        identity_state="confirmed", identifiers={"biosample": "SAMN123"})],
                [],
            )
        with self.assertRaisesRegex(ProvenanceValidationError, "archive accessions"):
            create_document([entity("SAMN123", "biological_material")], [])
        with self.assertRaisesRegex(ProvenanceValidationError, "curator identity evidence"):
            create_document(
                [entity("material-1", "biological_material",
                        identity_state="confirmed", identifiers={"local": "MAT-1"})],
                [],
            )

    def test_direct_archive_assertions_cannot_claim_independence(self):
        with self.assertRaisesRegex(ProvenanceValidationError, "requires publication or curator"):
            create_document(
                [entity("a"), entity("b")],
                [decision_edge("archive-claim", "a", "b", "sequencing", "different",
                               source="direct_archive_assertion")],
            )

    def test_sha256_is_labeled_integrity_only(self):
        graph = create_document(
            [entity("a"), entity("b")],
            [edge("digest", "a", "b", evidence=[ev(source_digest="a" * 64)])],
        )
        entry = graph["relationships"][0]["evidence"][0]
        self.assertEqual(entry["digest_semantics"],
                         "local_integrity_only_not_source_authentication")

    def test_deterministic_serialization_and_stable_evidence_ids(self):
        evidence = ev()
        a = create_document([entity("b"), entity("a")],
                            [edge("r", "a", "b", evidence=[evidence])])
        b = create_document([entity("a"), entity("b")],
                            [edge("r", "a", "b", evidence=[dict(reversed(list(evidence.items())))])])
        self.assertEqual(serialize_document(a), serialize_document(b))
        self.assertEqual(stable_evidence_id(evidence),
                         a["relationships"][0]["evidence"][0]["evidence_id"])
        self.assertEqual(validate_document(a)["schema"], SCHEMA)

    def test_validation_rejects_bad_references_duplicate_records_and_unknown_fields(self):
        with self.assertRaisesRegex(ProvenanceValidationError, "missing entity"):
            create_document([entity("a")], [edge("dangling", "a", "missing")])
        with self.assertRaisesRegex(ProvenanceValidationError, "duplicate entity_id"):
            create_document([entity("a"), entity("a")], [])
        with self.assertRaisesRegex(ProvenanceValidationError, "unknown fields"):
            create_document([dict(entity("a"), private_sample_detail="unneeded")], [])
        graph = create_document([entity("a"), entity("b")], [])
        graph["schema_version"] = 99
        with self.assertRaisesRegex(ProvenanceValidationError, "schema_version"):
            validate_document(graph)

    def test_evidence_identity_mismatch_is_rejected(self):
        evidence = ev()
        evidence["evidence_id"] = "ev-" + "0" * 64
        with self.assertRaisesRegex(ProvenanceValidationError, "does not match"):
            create_document([entity("a"), entity("b")], [edge("r", "a", "b", evidence=[evidence])])

    def test_aggregate_evidence_limit_counts_identity_and_relationship_evidence(self):
        def identity_entity(name, count):
            return entity(
                name, "biological_material", identity_state="provisional",
                identity_evidence=[
                    ev(review="proposed", statement=f"identity fixture {name}-{i}")
                    for i in range(count)
                ],
            )

        with patch.object(provenance, "MAX_EVIDENCE", 4):
            with self.assertRaisesRegex(ProvenanceValidationError, "evidence exceeds 4"):
                create_document([identity_entity("a", 3), identity_entity("b", 2)], [])
            rel_evidence = [
                ev(review="proposed", statement=f"relationship fixture {i}")
                for i in range(5)
            ]
            with self.assertRaisesRegex(ProvenanceValidationError, "evidence exceeds 4"):
                create_document([entity("a"), entity("b")],
                                [edge("too-many", "a", "b", evidence=rel_evidence)])
            mixed = [
                ev(review="proposed", statement=f"mixed relationship fixture {i}")
                for i in range(3)
            ]
            with self.assertRaisesRegex(ProvenanceValidationError, "evidence exceeds 4"):
                create_document(
                    [identity_entity("a", 2), entity("b")],
                    [edge("mixed", "a", "b", evidence=mixed)],
                )
            exact = [
                ev(review="proposed", statement=f"exact relationship fixture {i}")
                for i in range(2)
            ]
            graph = create_document(
                [identity_entity("a", 2), entity("b")],
                [edge("exact", "a", "b", evidence=exact)],
            )
            self.assertEqual(
                sum(len(item.get("identity_evidence", [])) for item in graph["entities"])
                + sum(len(item["evidence"]) for item in graph["relationships"]),
                4,
            )

    def test_aggregate_evidence_limit_fails_before_evidence_validation(self):
        with patch.object(provenance, "MAX_EVIDENCE", 1), \
                patch.object(provenance, "_validate_evidence",
                             side_effect=AssertionError("must fail during preflight")) as validator:
            with self.assertRaisesRegex(ProvenanceValidationError, "evidence exceeds 1"):
                create_document(
                    [entity("a", "biological_material", identity_state="provisional",
                            identity_evidence=[ev(), ev(statement="second fixture")])],
                    [],
                )
        validator.assert_not_called()

    def test_accepted_independence_evidence_requires_auditable_reference(self):
        for source in ("publication_assertion", "curator_decision"):
            evidence = ev(source=source, dimension="sequencing", assessment="different")
            evidence.pop("audit_reference")
            with self.subTest(source=source), self.assertRaisesRegex(
                    ProvenanceValidationError, "requires an audit_reference"):
                create_document([entity("a"), entity("b")],
                                [decision_edge("missing-reference", "a", "b",
                                               "sequencing", "different",
                                               source=source,
                                               audit_reference=None)])

    def test_independence_audit_reference_is_canonical_and_content_addressed(self):
        claim = ev(source="publication_assertion", dimension="sequencing",
                   assessment="different")
        graph = create_document([entity("a"), entity("b")],
                                [edge("audited", "a", "b",
                                      "independence_assessment", [claim])])
        normalized = graph["relationships"][0]["evidence"][0]
        self.assertEqual(normalized["audit_reference"]["publication_ref"],
                         "doi:10.0000/synthetic")
        self.assertEqual(normalized["evidence_id"], stable_evidence_id(
            {key: value for key, value in normalized.items() if key != "evidence_id"}))
        self.assertEqual(validate_document(graph), graph)

    def test_unaccepted_independence_claims_need_dimensions_but_not_audit_references(self):
        for review in ("proposed", "rejected", "conflicting"):
            graph = create_document(
                [entity("a"), entity("b")],
                [decision_edge(f"claim-{review}", "a", "b", "sequencing", "different",
                               review=review)],
            )
            self.assertEqual(assess_independence(graph, "a", "b", "sequencing"), "UNKNOWN")
        with self.assertRaisesRegex(ProvenanceValidationError, "requires a valid dimension"):
            create_document([entity("a"), entity("b")],
                            [edge("no-dimension", "a", "b", "independence_assessment")])
        with self.assertRaisesRegex(ProvenanceValidationError, "fields require an independence_assessment"):
            create_document(
                [entity("a"), entity("b")],
                [edge("wrong-edge", "a", "b",
                      evidence=[ev(dimension="sequencing", assessment="different")])],
            )

    def test_relationship_endpoint_type_contracts(self):
        invalid = edge("invalid-endpoints", "publication", "stock",
                       "experiment_uses_archive_sample")
        with self.assertRaisesRegex(ProvenanceValidationError, "incompatible endpoint types"):
            create_document(
                [entity("publication", "publication"),
                 entity("stock", "viral_isolate_or_stock")], [invalid])
        with self.assertRaisesRegex(ProvenanceValidationError, "matching entity types"):
            create_document(
                [entity("run", "sra_run"), entity("event", "sequencing_event")],
                [edge("mixed-replicates", "run", "event", "technical_replicate_of")],
            )
        graph = create_document(
            [entity("run", "sra_run"), entity("experiment", "sra_experiment"),
             entity("sample", "sra_sample"), entity("paper", "publication")],
            [
                edge("run-exp", "run", "experiment", "run_of_experiment"),
                edge("exp-sample", "experiment", "sample", "experiment_uses_archive_sample"),
                edge("run-paper", "run", "paper", "reported_in_publication"),
            ],
        )
        self.assertEqual(len(graph["relationships"]), 3)

    def test_confirmed_identity_rejects_unresolved_conflicting_evidence(self):
        identity = ev()
        confirmed = entity(
            "material", "biological_material", identity_state="confirmed",
            identifiers={"local": "MAT-1"}, identity_evidence=[identity],
        )
        self.assertEqual(create_document([confirmed], [])["entities"][0]["identity_state"],
                         "confirmed")
        for state in ("proposed", "rejected"):
            with self.subTest(state=state), self.assertRaisesRegex(
                    ProvenanceValidationError, "accepted curator identity evidence"):
                create_document([entity(
                    "material", "biological_material", identity_state="confirmed",
                    identifiers={"local": "MAT-1"},
                    identity_evidence=[ev(review=state)],
                )], [])
        with self.assertRaisesRegex(ProvenanceValidationError, "conflicting identity evidence"):
            create_document([entity(
                "material", "biological_material", identity_state="confirmed",
                identifiers={"local": "MAT-1"},
                identity_evidence=[identity, ev(review="conflicting",
                                                statement="unresolved identity conflict")],
            )], [])
        provisional = entity(
            "material", "biological_material", identity_state="provisional",
            identifiers={"local": "MAT-1"},
            identity_evidence=[identity, ev(review="conflicting",
                                            statement="unresolved identity conflict")],
        )
        self.assertEqual(create_document([provisional], [])["entities"][0]["identity_state"],
                         "provisional")

    def test_independence_arguments_reject_non_string_and_missing_ids_consistently(self):
        graph = create_document([entity("a"), entity("b")], [])
        for left, right, dimension in (
                ([], "b", "sequencing"),
                ("a", [], "sequencing"),
                ("a", "b", []),
                ("missing", "b", "sequencing")):
            with self.subTest(left=left, right=right, dimension=dimension):
                with self.assertRaises(ProvenanceValidationError):
                    assess_independence(graph, left, right, dimension)


if __name__ == "__main__":
    unittest.main()
