import json
import os
from pathlib import Path
import tempfile
import unittest

from satellite_discovery.m36_manifest_builder import (
    SOURCE_SCHEMA,
    build_manifest,
    store_manifest,
)
from satellite_discovery.m36_runner import (
    condition_catalog_sha256,
    registered_assignments,
    validate_evaluator_manifest,
    FROZEN_SEED_POLICY,
)


ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = ROOT / "docs/M36_POSITIVE_CONTROL_ASSEMBLY_INVESTIGATION.json"
DESIGN = json.loads(DESIGN_PATH.read_text(encoding="utf-8"))


def source_map_fixture():
    assignments = registered_assignments(DESIGN)
    split_by_family = {
        f"f{index:02d}": (
            "development" if index <= 4 else
            "held_out" if index <= 8 else "tuning"
        )
        for index in range(1, 13)
    }
    families = [
        {
            "family_id": family,
            "family_seed": 20_000 + int(family[1:]),
            "split": split,
        }
        for family, split in split_by_family.items()
    ]
    groups = sorted({
        (row["block_id"], row["family_id"], row["condition_id"], row["repeat_id"])
        for row in assignments
    })
    read_seeds = [
        {
            "block_id": block,
            "family_id": family,
            "condition_id": condition,
            "repeat_id": repeat,
            "read_seed": 100_000 + index,
        }
        for index, (block, family, condition, repeat) in enumerate(groups)
    ]
    return {
        "schema": SOURCE_SCHEMA,
        "provenance": {
            "source_id": "synthetic-unit-test-only",
            "source_version": "fixture",
            "approval_reference": "unit-test fixture",
        },
        "families": families,
        "read_seeds": read_seeds,
    }


class M36ManifestBuilderTests(unittest.TestCase):
    def test_builds_full_manifest_from_complete_synthetic_source_map(self):
        source_map = source_map_fixture()
        design_digest = "a" * 64
        manifest = build_manifest(
            DESIGN, source_map, design_sha256=design_digest,
        )

        result = validate_evaluator_manifest(
            DESIGN, manifest, design_sha256=design_digest,
        )
        self.assertEqual(result["assignment_count"], 520)
        self.assertEqual(manifest["seed_policy"], FROZEN_SEED_POLICY)
        self.assertEqual(
            manifest["condition_catalog_sha256"],
            condition_catalog_sha256(DESIGN),
        )
        self.assertEqual(len(manifest["source_map_sha256"]), 64)
        self.assertNotIn("source_map", manifest)

    def test_missing_or_unregistered_source_rows_fail_closed(self):
        source_map = source_map_fixture()
        source_map["read_seeds"].pop()
        with self.assertRaisesRegex(ValueError, "missing a registered"):
            build_manifest(DESIGN, source_map, design_sha256="a" * 64)

        source_map = source_map_fixture()
        source_map["families"][0]["family_seed"] = "not-a-seed"
        with self.assertRaises(Exception):
            build_manifest(DESIGN, source_map, design_sha256="a" * 64)

    @unittest.skipUnless(
        os.name == "posix",
        "owner-only restricted storage requires verifiable POSIX ownership and modes",
    )
    def test_restricted_storage_is_immutable_and_reports_only_digests(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            checkout = root / "checkout"
            restricted = root / "restricted"
            public = root / "public"
            checkout.mkdir()
            restricted.mkdir(mode=0o700)
            restricted.chmod(0o700)
            public.mkdir()
            source_path = restricted / "approved-source.json"
            source_path.write_text(
                json.dumps(source_map_fixture()), encoding="utf-8",
            )
            source_path.chmod(0o600)

            summary = store_manifest(
                DESIGN,
                source_path,
                design_path=DESIGN_PATH,
                source_root=checkout,
                restricted_root=restricted,
                public_root=public,
            )

            self.assertEqual(summary["status"], "PASS")
            self.assertEqual(summary["assignment_count"], 520)
            self.assertNotIn("family_seed", json.dumps(summary))
            with self.assertRaises(FileExistsError):
                store_manifest(
                    DESIGN,
                    source_path,
                    design_path=DESIGN_PATH,
                    source_root=checkout,
                    restricted_root=restricted,
                    public_root=public,
                )


if __name__ == "__main__":
    unittest.main()
