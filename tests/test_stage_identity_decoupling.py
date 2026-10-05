import importlib.util
import os
from dataclasses import replace
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from satellite_discovery import (
    artifact_contracts,
    artifact_workflow,
    m12_artifact_review,
    m13_stage,
    m14_descriptive_observations,
    m15_stage,
    stage_cache_identity,
)


_MILESTONE_KINDS = (
    m12_artifact_review.STAGE_KIND,
    m13_stage.STAGE_KIND,
    m14_descriptive_observations.STAGE_KIND,
    m15_stage.STAGE_KIND,
)
_SNAPSHOT_SCRIPT = r"""
import json
from satellite_discovery import artifact_workflow, m12_artifact_review
from satellite_discovery import m13_stage, m14_descriptive_observations, m15_stage
from satellite_discovery import stage_cache_identity
registry = artifact_workflow.build_default_registry()
kinds = (
    m12_artifact_review.STAGE_KIND, m13_stage.STAGE_KIND,
    m14_descriptive_observations.STAGE_KIND, m15_stage.STAGE_KIND, "inventory",
)
keys = {
    kind: artifact_workflow._stage_cache_key(
        {"id": kind, "kind": kind}, registry.get(kind), {}, {}, {}, None
    )
    for kind in kinds
}
inventory_identity = stage_cache_identity.stage_implementation_identity(
    registry.get("inventory"),
    artifact_workflow._stage_cache_registration_identity(registry.get("inventory")),
)
print("IDENTITY_SNAPSHOT=" + json.dumps({
    "keys": keys,
    "source": {
        "m12": m12_artifact_review._source_identity(),
        "m13": m13_stage._source_identity(),
        "m15": m15_stage._source_identity(),
    },
    "inventory_identity": inventory_identity,
    "inventory_alias": stage_cache_identity.legacy_package_cache_alias(
        "inventory", inventory_identity[0], inventory_identity[1]
    ),
}, sort_keys=True))
"""


class StageIdentityDecouplingTests(unittest.TestCase):
    @staticmethod
    def _key(definition):
        return artifact_workflow._stage_cache_key(
            {"id": definition.kind, "kind": definition.kind},
            definition,
            {},
            {},
            {},
            None,
        )

    @classmethod
    def _all_keys(cls, registry):
        return {
            kind: cls._key(definition)
            for kind, definition in sorted(registry._stages.items())
        }

    @staticmethod
    def _source_identity(module_name, identity_function, source_path):
        with tempfile.TemporaryDirectory() as directory:
            replacement = Path(directory) / source_path.name
            replacement.write_bytes(
                source_path.read_bytes() + b"\n# source identity regression probe\n"
            )
            resolve_source = stage_cache_identity._source_file_for_module

            def resolver(name):
                if name == module_name:
                    return replacement
                return resolve_source(name)

            with patch.object(
                stage_cache_identity, "_source_file_for_module", side_effect=resolver
            ):
                return identity_function()

    def test_downstream_contract_registration_and_module_leave_all_existing_keys_stable(self):
        before_registry = artifact_workflow.build_default_registry()
        before_keys = self._all_keys(before_registry)
        before_sources = {
            "m12": m12_artifact_review._source_identity(),
            "m13": m13_stage._source_identity(),
            "m15": m15_stage._source_identity(),
        }
        probe_type = "downstream_identity_probe_artifact"
        with tempfile.TemporaryDirectory() as directory:
            module_name = "downstream_identity_probe"
            module_path = Path(directory) / f"{module_name}.py"
            module_path.write_text(
                "def run(inputs, output, config):\n    return []\n",
                encoding="utf-8",
            )
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            with patch.dict(sys.modules, {module_name: module}):
                spec.loader.exec_module(module)
                with (
                    patch.dict(
                        artifact_contracts._CONTRACTS,
                        {probe_type: "A downstream-only test artifact."},
                    ),
                    patch.dict(
                        artifact_contracts._CONTRACT_SEMANTIC_VERSIONS,
                        {probe_type: "1"},
                    ),
                ):
                    after_registry = artifact_workflow.build_default_registry()
                    after_registry.register(
                        "downstream_identity_probe",
                        (),
                        module.run,
                        output_contracts={"probe.json": probe_type},
                    )
                    after_keys = self._all_keys(after_registry)
                    after_sources = {
                        "m12": m12_artifact_review._source_identity(),
                        "m13": m13_stage._source_identity(),
                        "m15": m15_stage._source_identity(),
                    }

        self.assertEqual(
            before_keys,
            {kind: after_keys[kind] for kind in before_keys},
        )
        self.assertEqual(before_sources, after_sources)
        self.assertEqual(len(before_keys), 36)
        self.assertEqual(len(after_keys), 37)

    def test_m12_m13_and_m15_implementation_sources_invalidate_their_own_identity(self):
        cases = (
            (
                "satellite_discovery.m12_artifact_review",
                m12_artifact_review._source_identity,
                Path(m12_artifact_review.__file__),
            ),
            (
                "satellite_discovery.m13_stage",
                m13_stage._source_identity,
                Path(m13_stage.__file__),
            ),
            (
                "satellite_discovery.m15_stage",
                m15_stage._source_identity,
                Path(m15_stage.__file__),
            ),
        )
        for module_name, identity_function, source_path in cases:
            with self.subTest(module=module_name):
                before = identity_function()["source_sha256"]
                after = self._source_identity(
                    module_name, identity_function, source_path
                )["source_sha256"]
                self.assertNotEqual(before, after)

    def test_m15_producer_verifier_is_a_real_identity_dependency(self):
        verifier_path = Path(m15_stage.__file__).with_name("producer_provenance.py")
        before = m15_stage._source_identity()["source_sha256"]
        after = self._source_identity(
            "satellite_discovery.producer_provenance",
            m15_stage._source_identity,
            verifier_path,
        )["source_sha256"]
        self.assertNotEqual(before, after)

    def test_stage_registration_and_contract_changes_invalidate_only_relevant_stages(self):
        registry = artifact_workflow.build_default_registry()
        for kind in _MILESTONE_KINDS:
            with self.subTest(stage=kind):
                definition = registry.get(kind)
                changed = replace(definition, version=definition.version + "-probe")
                self.assertNotEqual(self._key(definition), self._key(changed))

        m14_before = self._key(registry.get(m14_descriptive_observations.STAGE_KIND))
        with patch.dict(
            artifact_contracts._CONTRACT_SEMANTIC_VERSIONS,
            {"m14_result_bundle": "identity-probe"},
        ):
            m14_after = self._key(registry.get(m14_descriptive_observations.STAGE_KIND))
        self.assertNotEqual(m14_before, m14_after)

        m15_before = m15_stage._source_identity()["source_sha256"]
        with patch.dict(
            artifact_contracts._CONTRACT_SEMANTIC_VERSIONS,
            {"m15_result_bundle": "identity-probe"},
        ):
            m15_contract_change = m15_stage._source_identity()["source_sha256"]
        self.assertNotEqual(m15_before, m15_contract_change)

        with patch.object(artifact_contracts, "VALIDATOR_SEMANTIC_VERSION", "probe"):
            m15_validator_change = m15_stage._source_identity()["source_sha256"]
        self.assertNotEqual(m15_before, m15_validator_change)

    def test_shared_workflow_semantics_invalidate_scoped_and_unscoped_keys(self):
        registry = artifact_workflow.build_default_registry()
        kinds = (
            m12_artifact_review.STAGE_KIND,
            m13_stage.STAGE_KIND,
            m15_stage.STAGE_KIND,
            "inventory",
        )
        before = {kind: self._key(registry.get(kind)) for kind in kinds}
        with patch.object(artifact_workflow, "WORKFLOW_CACHE_SEMANTICS_VERSION", "probe"):
            after = {kind: self._key(registry.get(kind)) for kind in kinds}
        for kind in kinds:
            with self.subTest(stage=kind):
                self.assertNotEqual(before[kind], after[kind])

    def test_identity_algorithm_and_validator_versions_are_cache_inputs(self):
        registry = artifact_workflow.build_default_registry()
        algorithm_kinds = (
            m12_artifact_review.STAGE_KIND,
            m13_stage.STAGE_KIND,
            m15_stage.STAGE_KIND,
            "inventory",
        )
        validator_kinds = (*_MILESTONE_KINDS, "inventory")
        before_algorithm = {
            kind: self._key(registry.get(kind)) for kind in algorithm_kinds
        }
        before_validator = {
            kind: self._key(registry.get(kind)) for kind in validator_kinds
        }
        with patch.object(stage_cache_identity, "IDENTITY_ALGORITHM_VERSION", "probe"):
            algorithm_changed = {
                kind: self._key(registry.get(kind)) for kind in algorithm_kinds
            }
        with patch.object(artifact_contracts, "VALIDATOR_SEMANTIC_VERSION", "probe"):
            validator_changed = {
                kind: self._key(registry.get(kind)) for kind in validator_kinds
            }
        for kind in algorithm_kinds:
            with self.subTest(stage=kind, change="identity algorithm"):
                self.assertNotEqual(before_algorithm[kind], algorithm_changed[kind])
        for kind in validator_kinds:
            with self.subTest(stage=kind, change="validator"):
                self.assertNotEqual(before_validator[kind], validator_changed[kind])

    def test_compatibility_aliases_are_exact_and_unknown_digests_are_rejected(self):
        compatibility_path = Path(stage_cache_identity.__file__).with_name(
            "stage_cache_identity_compatibility.txt"
        )
        compatibility = dict(
            line.split("=", 1)
            for line in compatibility_path.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        legacy_path = Path(artifact_workflow.__file__).with_name(
            "m12_legacy_cache_compatibility.txt"
        )
        legacy_compatibility = dict(
            line.split("=", 1)
            for line in legacy_path.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        self.assertEqual(compatibility["schema"], "stage-cache-identity-compat-v1")
        registry = artifact_workflow.build_default_registry()
        for kind, definition in registry._stages.items():
            if callable(getattr(definition.handler, "cache_implementation_identity", None)):
                continue
            identity, profile = stage_cache_identity.stage_implementation_identity(
                definition,
                artifact_workflow._stage_cache_registration_identity(definition),
            )
            with self.subTest(stage=kind):
                self.assertEqual(compatibility[f"stage.{kind}"], identity)
                self.assertEqual(
                    stage_cache_identity.legacy_package_cache_alias(kind, identity, profile),
                    legacy_compatibility[
                        "legacy_source_sha256" + ("_crlf" if profile == "crlf" else "")
                    ],
                )
                self.assertIsNone(
                    stage_cache_identity.legacy_package_cache_alias(kind, "f" * 64, profile)
                )
        self.assertNotIn("stage.m15_evidence_dossier", compatibility)
        self.assertNotIn("source.m15_evidence_dossier.identity_sha256", compatibility)

    def test_checkout_relocation_and_crlf_preserve_the_declared_identity_rules(self):
        package = Path(artifact_workflow.__file__).resolve().parent
        identity_compatibility = dict(
            line.split("=", 1)
            for line in (package / "stage_cache_identity_compatibility.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if "=" in line
        )
        legacy_compatibility = dict(
            line.split("=", 1)
            for line in (package / "m12_legacy_cache_compatibility.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if "=" in line
        )

        def snapshot(root, *, crlf=False):
            root.mkdir(parents=True)
            destination = root / "satellite_discovery"
            shutil.copytree(
                package, destination, ignore=shutil.ignore_patterns("__pycache__")
            )
            if crlf:
                for path in destination.rglob("*"):
                    if path.is_file() and path.suffix in {".py", ".json", ".txt"}:
                        content = path.read_bytes().replace(b"\r\n", b"\n")
                        path.write_bytes(content.replace(b"\n", b"\r\n"))
            environment = dict(os.environ)
            environment["PYTHONPATH"] = os.pathsep.join(
                filter(None, (str(root), environment.get("PYTHONPATH", "")))
            )
            result = subprocess.run(
                [sys.executable, "-c", _SNAPSHOT_SCRIPT],
                cwd=root,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
                timeout=45,
            )
            marker = next(
                line for line in result.stdout.splitlines()
                if line.startswith("IDENTITY_SNAPSHOT=")
            )
            import json
            return json.loads(marker.split("=", 1)[1])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            relocated = snapshot(root / "relocated")
            crlf = snapshot(root / "crlf", crlf=True)

        local = {
            "keys": {
                kind: self._key(artifact_workflow.build_default_registry().get(kind))
                for kind in (*_MILESTONE_KINDS, "inventory")
            },
            "source": {
                "m12": m12_artifact_review._source_identity(),
                "m13": m13_stage._source_identity(),
                "m15": m15_stage._source_identity(),
            },
        }
        self.assertEqual(local["keys"], relocated["keys"])
        self.assertEqual(local["source"], relocated["source"])
        self.assertEqual(
            relocated["inventory_identity"][0],
            crlf["inventory_identity"][0],
        )
        self.assertEqual(
            relocated["inventory_alias"],
            legacy_compatibility["legacy_source_sha256"],
        )
        self.assertEqual(
            crlf["inventory_alias"],
            legacy_compatibility["legacy_source_sha256_crlf"],
        )
        self.assertEqual(
            relocated["source"]["m13"]["source_sha256"],
            crlf["source"]["m13"]["source_sha256"],
        )
        self.assertEqual(
            relocated["source"]["m15"]["source_sha256"],
            crlf["source"]["m15"]["source_sha256"],
        )
        self.assertEqual(
            relocated["source"]["m12"]["source_sha256"],
            identity_compatibility[
                "source.m12_artifact_review.legacy_sha256_lf"
            ],
        )
        self.assertEqual(
            crlf["source"]["m12"]["source_sha256"],
            identity_compatibility[
                "source.m12_artifact_review.legacy_sha256_crlf"
            ],
        )


if __name__ == "__main__":
    unittest.main()
