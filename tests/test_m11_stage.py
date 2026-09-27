import hashlib
import json
import platform
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from satellite_discovery import artifact_contracts, m11_algorithms, m11_stage
from satellite_discovery.m11_runtime import WHEEL_LOCK
from tests.test_m8_contracts import M8ContractTests


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _available_runtime():
    system = platform.system()
    python = f"{sys.version_info.major}.{sys.version_info.minor}"
    filename, wheel_hash = WHEEL_LOCK[(system, python)]
    return {
        "status": "available",
        "reason_code": None,
        "engine": "ViennaRNA",
        "version": "2.7.2",
        "wheel_filename": filename,
        "wheel_sha256": wheel_hash,
        "native_library_sha256": "1" * 64,
        "installed_files_sha256": "2" * 64,
        "python_implementation": "CPython",
        "python_version": platform.python_version(),
        "python_abi": sys.implementation.cache_tag,
        "operating_system": system,
        "architecture": platform.machine(),
        "platform": platform.platform(),
        "target_python": python,
    }


def _make_handoff(root, sequences=("GCGAAACGC", "ATGCAAA"), molecules=("RNA", "DNA")):
    manifest, document = M8ContractTests()._candidate_set(root)
    source_ref = document["source_artifact"]
    source_path = Path(root) / source_ref["path"]
    source_bytes = (
        f">source-a description\n{sequences[0]}\n"
        f">source-b\n{sequences[1]}\n"
    ).encode("ascii")
    source_path.write_bytes(source_bytes)
    source_ref["sha256"] = _digest(source_bytes)
    fasta_ref = document["availability"]["fasta_artifact"]
    fasta_path = Path(root) / fasta_ref["path"]
    fasta_bytes = (
        f">source-a description\n{sequences[0]}\n"
        f">source-b\n{sequences[1]}\n"
    ).encode("ascii")
    fasta_path.write_bytes(fasta_bytes)
    fasta_ref["sha256"] = _digest(fasta_bytes)
    for record, sequence, molecule in zip(document["records"], sequences, molecules):
        record["sequence_sha256"] = _digest(sequence.encode("ascii"))
        record["sequence_length"] = len(sequence)
        record["molecule_type"] = molecule
        record["source_artifact_sha256"] = source_ref["sha256"]
    manifest.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
    return manifest


def _fold(sequence, timeout, memory):
    return "COMPLETED", {
        "dot_bracket": "." * len(sequence),
        "energy_hex": (-0.4).hex(),
        "effective_model_details": {
            "temperature": 37.0,
            "dangles": 2,
            "parameter_set": "TURNER_2004_BUILTIN",
        },
    }, None


def _jsonl(path):
    if not path.read_bytes():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class M11PolicyTests(unittest.TestCase):
    def test_source_and_molecule_precedence(self):
        self.assertEqual(m11_algorithms.validate_source("acgt"), ("INPUT_VALID", "ACGT"))
        self.assertEqual(m11_algorithms.validate_source("AC-G"), ("INPUT_INVALID", None))
        self.assertEqual(m11_algorithms.validate_source(""), ("INPUT_INVALID", None))

        status, applicability, view = m11_algorithms.resolve_applicability(
            "ATGC", "DNA", 0, 4)
        self.assertEqual((status, applicability), ("INPUT_VALID", "APPLICABLE"))
        self.assertEqual(view["view_sequence"], "AUGC")
        self.assertEqual(view["view_sha256"], _digest(b"M11-RNA-VIEW-v1\0AUGC"))

        self.assertEqual(
            m11_algorithms.resolve_applicability("NNN", None, 0, 3)[:2],
            ("INSUFFICIENT_INFORMATION", "INSUFFICIENT_INFORMATION"),
        )
        self.assertEqual(
            m11_algorithms.resolve_applicability("ATGC", "RNA", 0, 4)[:2],
            ("INSUFFICIENT_INFORMATION", "INSUFFICIENT_INFORMATION"),
        )
        self.assertEqual(
            m11_algorithms.resolve_applicability("AN", "RNA", 0, 2)[:2],
            ("INPUT_VALID", "NOT_APPLICABLE"),
        )
        self.assertEqual(
            m11_algorithms.resolve_applicability("ACGU", "RNA", 0, 0)[:2],
            ("INPUT_INVALID", "NOT_EVALUATED"),
        )

    def test_runtime_unavailable_is_a_typed_branch_not_a_silent_skip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            handoff = _make_handoff(root)
            output = root / "out"
            unavailable = {
                "status": "unavailable",
                "reason_code": "PINNED_WHEEL_RECEIPT_MISSING_OR_INVALID",
                "engine": "ViennaRNA",
                "version": None,
                "wheel_filename": None,
                "wheel_sha256": None,
                "native_library_sha256": None,
                "installed_files_sha256": None,
                "python_implementation": "CPython",
                "python_version": platform.python_version(),
                "python_abi": sys.implementation.cache_tag,
                "operating_system": platform.system(),
                "architecture": platform.machine(),
                "platform": platform.platform(),
                "target_python": f"{sys.version_info.major}.{sys.version_info.minor}",
            }
            with patch.object(m11_stage, "runtime_identity", return_value=unavailable):
                with patch.object(m11_stage, "fold_single") as fold:
                    m11_stage.run_stage(
                        {"candidate_sequence_set": str(handoff)}, output, {})
            fold.assert_not_called()
            branches = _jsonl(output / "fold_accounting.jsonl")
            self.assertEqual(
                [row["branch_status"] for row in branches],
                ["DEPENDENCY_UNAVAILABLE", "DEPENDENCY_UNAVAILABLE"],
            )
            self.assertEqual(
                artifact_contracts.validate_artifact(
                    output / "m11_bundle.json", "m11_result_bundle"
                )["aggregate_status"],
                "PARTIAL",
            )

    def test_bundle_is_complete_deterministic_and_preserves_dna_view(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            handoff = _make_handoff(root)
            runtime = _available_runtime()
            outputs = [root / "first", root / "second"]
            for output in outputs:
                with patch.object(m11_stage, "runtime_identity", return_value=runtime):
                    with patch.object(m11_stage, "fold_single", side_effect=_fold):
                        m11_stage.run_stage(
                            {"candidate_sequence_set": str(handoff)},
                            output,
                            {"region_requests": [{
                                "candidate_id": "candidate-1",
                                "sequence_id": "sequence-1",
                                "start": 1,
                                "end": 8,
                            }]},
                        )

            for name in m11_stage._OUTPUT_TYPES:
                self.assertEqual(
                    (outputs[0] / name).read_bytes(),
                    (outputs[1] / name).read_bytes(),
                    name,
                )
                artifact_contracts.validate_artifact(
                    outputs[0] / name, m11_stage._OUTPUT_TYPES[name]
                )

            candidates = _jsonl(outputs[0] / "candidate_accounting.jsonl")[1:]
            self.assertEqual(
                [(row["candidate_id"], row["sequence_id"]) for row in candidates],
                [("candidate-1", "sequence-1"), ("candidate-2", "sequence-2")],
            )
            evidence = _jsonl(outputs[0] / "rna_structure_evidence.jsonl")
            self.assertEqual(len(evidence), 2)
            self.assertEqual(evidence[0]["source_region"], {"start": 1, "end": 8})
            self.assertEqual(evidence[0]["source_sequence"], "GCGAAACGC")
            self.assertEqual(evidence[1]["source_sequence"], "ATGCAAA")
            self.assertEqual(evidence[1]["view_sequence"], "AUGCAAA")
            self.assertEqual(evidence[1]["transformation"],
                             "ASCII_UPPERCASE_AND_DNA_T_TO_RNA_U")
            serialized = b"".join((outputs[0] / name).read_bytes()
                                  for name in m11_stage._OUTPUT_TYPES)
            self.assertNotIn(str(root).encode(), serialized)

    def test_fold_cap_accounts_for_unstarted_requests(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            handoff = _make_handoff(root)
            with patch.object(m11_stage, "runtime_identity",
                              return_value=_available_runtime()):
                with patch.object(m11_stage, "fold_single", side_effect=_fold) as fold:
                    m11_stage.run_stage(
                        {"candidate_sequence_set": str(handoff)},
                        root / "out",
                        {"max_folds_per_run": 1},
                    )
            self.assertEqual(fold.call_count, 1)
            branches = _jsonl(root / "out" / "fold_accounting.jsonl")
            self.assertEqual(
                [row["branch_status"] for row in branches],
                ["PREDICTION_REPORTED", "TRUNCATED"],
            )
            self.assertEqual(branches[1]["reason_code"], "MAX_FOLDS_PER_RUN")

    def test_ambiguity_and_unknown_molecule_keep_separate_axes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            handoff = _make_handoff(
                root, sequences=("ACGNR", "NNN"), molecules=("RNA", None))
            with patch.object(m11_stage, "runtime_identity",
                              return_value=_available_runtime()):
                with patch.object(m11_stage, "fold_single") as fold:
                    m11_stage.run_stage(
                        {"candidate_sequence_set": str(handoff)}, root / "out", {})
            fold.assert_not_called()
            branches = _jsonl(root / "out" / "fold_accounting.jsonl")
            self.assertEqual(
                [row["branch_status"] for row in branches],
                ["NOT_APPLICABLE", "INSUFFICIENT_INFORMATION"],
            )
            self.assertEqual(
                [(row["input_status"], row["applicability_status"]) for row in branches],
                [
                    ("INPUT_VALID", "NOT_APPLICABLE"),
                    ("INPUT_VALID", "INSUFFICIENT_INFORMATION"),
                ],
            )

    def test_length_boundary_invalid_region_and_single_symbol_region(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            handoff = _make_handoff(root)
            with patch.object(m11_stage, "runtime_identity",
                              return_value=_available_runtime()):
                with patch.object(m11_stage, "fold_single", side_effect=_fold) as fold:
                    m11_stage.run_stage(
                        {"candidate_sequence_set": str(handoff)},
                        root / "length",
                        {"max_fold_symbols": 7},
                    )
            self.assertEqual(fold.call_count, 1)
            length_rows = _jsonl(root / "length" / "fold_accounting.jsonl")
            self.assertEqual(
                [row["branch_status"] for row in length_rows],
                ["TRUNCATED", "PREDICTION_REPORTED"],
            )
            self.assertEqual(length_rows[0]["reason_code"], "MAX_FOLD_SYMBOLS")
            self.assertEqual(length_rows[1]["view"]["view_length"], 7)

            with patch.object(m11_stage, "runtime_identity",
                              return_value=_available_runtime()):
                with patch.object(m11_stage, "fold_single", side_effect=_fold) as fold:
                    m11_stage.run_stage(
                        {"candidate_sequence_set": str(handoff)},
                        root / "bad-region",
                        {"region_requests": [{
                            "candidate_id": "candidate-1",
                            "sequence_id": "sequence-1",
                            "start": 1,
                            "end": 1,
                        }]},
                    )
            invalid_rows = _jsonl(root / "bad-region" / "fold_accounting.jsonl")
            self.assertEqual(invalid_rows[0]["branch_status"], "INPUT_INVALID")
            self.assertEqual(invalid_rows[0]["reason_code"], "INVALID_REGION")
            self.assertEqual(invalid_rows[1]["branch_status"], "PREDICTION_REPORTED")
            self.assertEqual(fold.call_count, 1)

            with patch.object(m11_stage, "runtime_identity",
                              return_value=_available_runtime()):
                with patch.object(m11_stage, "fold_single", side_effect=_fold) as fold:
                    m11_stage.run_stage(
                        {"candidate_sequence_set": str(handoff)},
                        root / "single-symbol",
                        {
                            "max_folds_per_run": 1,
                            "region_requests": [{
                                "candidate_id": "candidate-1",
                                "sequence_id": "sequence-1",
                                "start": 0,
                                "end": 1,
                            }],
                        },
                    )
            self.assertEqual(fold.call_count, 1)
            one = _jsonl(root / "single-symbol" / "rna_structure_evidence.jsonl")
            self.assertEqual(len(one), 1)
            self.assertEqual(one[0]["view_sequence"], "G")
            self.assertEqual(one[0]["mfe_structure_dot_bracket"], ".")

    def test_identical_source_bytes_keep_distinct_candidate_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            handoff = _make_handoff(
                root, sequences=("GCGAAACGC", "GCGAAACGC"),
                molecules=("RNA", "RNA"))
            with patch.object(m11_stage, "runtime_identity",
                              return_value=_available_runtime()):
                with patch.object(m11_stage, "fold_single", side_effect=_fold) as fold:
                    m11_stage.run_stage(
                        {"candidate_sequence_set": str(handoff)}, root / "out", {})
            self.assertEqual(fold.call_count, 2)
            evidence = _jsonl(root / "out" / "rna_structure_evidence.jsonl")
            self.assertEqual(len(evidence), 2)
            self.assertEqual(evidence[0]["source_sha256"], evidence[1]["source_sha256"])
            self.assertNotEqual(evidence[0]["candidate_id"], evidence[1]["candidate_id"])
            self.assertNotEqual(evidence[0]["request_id"], evidence[1]["request_id"])

    def test_failed_interrupted_and_malformed_folds_are_not_evidence(self):
        cases = (
            (
                "failed",
                lambda sequence, timeout, memory: (
                    "EXECUTION_FAILED", None, "SYNTHETIC_ENGINE_FAILURE"),
                "EXECUTION_FAILED",
            ),
            (
                "interrupted",
                lambda sequence, timeout, memory: (
                    "INTERRUPTED", None, "PER_FOLD_TIMEOUT"),
                "INTERRUPTED",
            ),
            (
                "malformed",
                lambda sequence, timeout, memory: (
                    "COMPLETED", {
                        "dot_bracket": "(",
                        "energy_hex": (-0.4).hex(),
                        "effective_model_details": {
                            "temperature": 37.0,
                            "dangles": 2,
                            "parameter_set": "TURNER_2004_BUILTIN",
                        },
                    }, None),
                "OUTPUT_INVALID",
            ),
        )
        for name, result, expected in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                handoff = _make_handoff(root)
                with patch.object(m11_stage, "runtime_identity",
                                  return_value=_available_runtime()):
                    with patch.object(m11_stage, "fold_single", side_effect=result):
                        m11_stage.run_stage(
                            {"candidate_sequence_set": str(handoff)},
                            root / "out",
                            {"max_folds_per_run": 1},
                        )
                branch = _jsonl(root / "out" / "fold_accounting.jsonl")[0]
                self.assertEqual(branch["branch_status"], expected)
                self.assertIsNone(branch["evidence_id"])
                bundle = artifact_contracts.validate_artifact(
                    root / "out" / "m11_bundle.json", "m11_result_bundle")
                self.assertEqual(bundle["aggregate_status"], "PARTIAL")
                self.assertEqual(bundle["evidence_count"], 0)

    def test_handoff_is_revalidated_after_folding(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            handoff = _make_handoff(root)
            fasta_path = root / "candidate_sequences.fasta"

            def mutate_after_fold(sequence, timeout, memory):
                fasta_path.write_bytes(fasta_path.read_bytes() + b"\n")
                return _fold(sequence, timeout, memory)

            with patch.object(m11_stage, "runtime_identity",
                              return_value=_available_runtime()):
                with patch.object(
                    m11_stage, "fold_single", side_effect=mutate_after_fold
                ):
                    with self.assertRaisesRegex(
                        ValueError, "checksum|changed during analysis"
                    ):
                        m11_stage.run_stage(
                            {"candidate_sequence_set": str(handoff)},
                            root / "out",
                            {"max_folds_per_run": 1},
                        )
            self.assertEqual(list((root / "out").iterdir()), [])

    def test_empty_handoff_is_complete_without_candidate_branches(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            handoff, document = M8ContractTests()._candidate_set(
                root, state="COMPLETE_EMPTY", with_records=False)
            document["availability"]["reason"] = None
            handoff.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
            with patch.object(m11_stage, "runtime_identity",
                              return_value=_available_runtime()):
                m11_stage.run_stage(
                    {"candidate_sequence_set": str(handoff)}, root / "out", {})
            bundle = artifact_contracts.validate_artifact(
                root / "out" / "m11_bundle.json", "m11_result_bundle")
            self.assertEqual(bundle["aggregate_status"], "COMPLETE")
            self.assertEqual(bundle["input_status"], "COMPLETE_EMPTY_INPUT_SET")
            self.assertEqual(bundle["fold_count"], 0)
            self.assertEqual(_jsonl(root / "out" / "fold_accounting.jsonl"), [])

    def test_partially_available_handoff_accounts_missing_source_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            handoff = _make_handoff(root)
            document = json.loads(handoff.read_text(encoding="utf-8"))
            document["availability"]["state"] = "PARTIALLY_AVAILABLE"
            unavailable = document["records"][1]
            unavailable.update({
                "fasta_record_id": None,
                "sequence_sha256": None,
                "sequence_length": None,
                "sequence_bytes_available": False,
                "sequence_unavailable_reason": "SOURCE_BYTES_MISSING",
            })
            fasta_ref = document["availability"]["fasta_artifact"]
            fasta_path = root / fasta_ref["path"]
            fasta_bytes = b">source-a description\nGCGAAACGC\n"
            fasta_path.write_bytes(fasta_bytes)
            fasta_ref["sha256"] = _digest(fasta_bytes)
            handoff.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")

            with patch.object(m11_stage, "runtime_identity",
                              return_value=_available_runtime()):
                with patch.object(m11_stage, "fold_single", side_effect=_fold) as fold:
                    m11_stage.run_stage(
                        {"candidate_sequence_set": str(handoff)}, root / "out", {})
            self.assertEqual(fold.call_count, 1)
            branches = _jsonl(root / "out" / "fold_accounting.jsonl")
            self.assertEqual(
                [row["branch_status"] for row in branches],
                ["PREDICTION_REPORTED", "SEQUENCE_UNAVAILABLE"],
            )
            self.assertIsNone(branches[1]["source_sha256"])
            self.assertIsNone(branches[1]["source_length"])
            bundle = artifact_contracts.validate_artifact(
                root / "out" / "m11_bundle.json", "m11_result_bundle")
            self.assertEqual(bundle["aggregate_status"], "PARTIAL")
            self.assertEqual(bundle["candidate_count"], 2)
            self.assertEqual(bundle["fold_count"], 2)
            self.assertEqual(bundle["evidence_count"], 1)

    def test_child_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            handoff = _make_handoff(root)
            with patch.object(m11_stage, "runtime_identity",
                              return_value=_available_runtime()):
                with patch.object(m11_stage, "fold_single", side_effect=_fold):
                    m11_stage.run_stage(
                        {"candidate_sequence_set": str(handoff)},
                        root / "out",
                        {},
                    )
            with (root / "out" / "fold_accounting.jsonl").open("ab") as stream:
                stream.write(b"{}")
            with self.assertRaisesRegex(ValueError, "integrity"):
                artifact_contracts.validate_artifact(
                    root / "out" / "m11_bundle.json", "m11_result_bundle")


if __name__ == "__main__":
    unittest.main()