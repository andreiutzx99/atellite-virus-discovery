"""Synthetic contract tests; they are not biological validation."""
import unittest

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
            [entity("run-a"), entity("run-b"), entity("sra-sample", "sra_sample")],
            [
                edge("r-a-exp", "run-a", "sra-sample", "experiment_uses_archive_sample"),
                edge("r-b-exp", "run-b", "sra-sample", "experiment_uses_archive_sample"),
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


if __name__ == "__main__":
    unittest.main()
