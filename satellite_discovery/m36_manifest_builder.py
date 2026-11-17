"""Build a restricted M36 evaluator manifest from approved private inputs.

This module never invents seeds, splits, or condition parameters. It joins
approved source maps to the frozen design, validates the full registration,
and writes canonical bytes exclusively into a provisioned restricted store.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from .m36_runner import (
    assignment_key,
    condition_catalog_sha256,
    expected_condition_parameters,
    registered_assignments,
    validate_evaluator_manifest,
)
from .m36_security import RestrictedEvidenceStore, canonical_json_bytes


SOURCE_SCHEMA = "m36-approved-evaluator-source-map-v1"


def build_manifest(design: dict, source_map: dict, *, design_sha256: str) -> dict:
    """Join the registered design to an approved family/read seed source map."""
    if source_map.get("schema") != SOURCE_SCHEMA:
        raise ValueError("approved evaluator source map schema is unsupported")
    families = source_map.get("families")
    read_seeds = source_map.get("read_seeds")
    provenance = source_map.get("provenance")
    if not isinstance(families, list) or not isinstance(read_seeds, list):
        raise ValueError("approved source map must contain family and read-seed rows")
    if (
        not isinstance(provenance, dict)
        or set(provenance) != {"source_id", "source_version", "approval_reference"}
        or any(not isinstance(value, str) or not value.strip() or len(value) > 500
               for value in provenance.values())
    ):
        raise ValueError(
            "provenance must identify the approved source, version, and review reference"
        )

    family_rows = {}
    for row in families:
        if not isinstance(row, dict) or set(row) != {
            "family_id", "family_seed", "split",
        }:
            raise ValueError("family source rows must declare exactly ID, seed, and split")
        family = row["family_id"]
        if not isinstance(family, str) or family in family_rows:
            raise ValueError("family source IDs must be unique text")
        family_rows[family] = row

    read_rows = {}
    read_key_fields = ("block_id", "family_id", "condition_id", "repeat_id")
    for row in read_seeds:
        if not isinstance(row, dict) or set(row) != {*read_key_fields, "read_seed"}:
            raise ValueError("read-seed source rows have an invalid shape")
        key = tuple(row[field] for field in read_key_fields)
        if not all(isinstance(part, str) for part in key) or key in read_rows:
            raise ValueError("read-seed source keys must be unique registered text tuples")
        read_rows[key] = row["read_seed"]

    catalog = expected_condition_parameters(design)
    assignments = registered_assignments(design)
    output_rows = []
    expected_read_keys = set()
    for assignment in assignments:
        family = family_rows.get(assignment["family_id"])
        read_key = tuple(assignment[field] for field in read_key_fields)
        expected_read_keys.add(read_key)
        if family is None or read_key not in read_rows:
            raise ValueError("approved source map is missing a registered family or read seed")
        output_rows.append({
            **assignment,
            "split": family["split"],
            "family_seed": family["family_seed"],
            "read_seed": read_rows[read_key],
            "condition_parameters": catalog[
                (assignment["block_id"], assignment["condition_id"])
            ],
        })
    if set(family_rows) != {
        row["family_id"] for row in assignments
    } or set(read_rows) != expected_read_keys:
        raise ValueError("approved source map contains unregistered or unused rows")

    manifest = {
        "schema": "m36-evaluator-execution-manifest-v2",
        "design_sha256": design_sha256,
        "condition_catalog_sha256": condition_catalog_sha256(design),
        "seed_policy": {
            "family_seed_role": "independent_sequence_family",
            "read_seed_role": "independent_read_simulation",
            "technical_repeat_rule": "distinct_read_seed",
            "paired_assembler_rule": "same_read_seed_across_paired_assembler_assignments",
        },
        "source_map_sha256": hashlib.sha256(
            canonical_json_bytes(source_map)
        ).hexdigest(),
        "provenance": provenance,
        "assignments": output_rows,
    }
    validate_evaluator_manifest(design, manifest, design_sha256=design_sha256)
    return manifest


def store_manifest(
    design: dict,
    source_map_path: str | Path,
    *,
    design_path: str | Path,
    source_root: str | Path,
    restricted_root: str | Path,
    public_root: str | Path,
    destination: str = "evaluator_manifest.json",
) -> dict:
    """Validate a private source map and create an immutable restricted manifest."""
    source_root = Path(source_root).resolve(strict=True)
    design_path = Path(design_path).resolve(strict=True)
    source_path = Path(source_map_path)
    if source_path.is_symlink():
        raise ValueError("approved source map must not be a symlink")
    source_path = source_path.resolve(strict=True)
    restricted_root = Path(restricted_root).resolve(strict=True)
    if source_path == restricted_root or not source_path.is_relative_to(restricted_root):
        raise ValueError("approved source map must be inside restricted storage")
    if design_path.is_relative_to(restricted_root):
        raise ValueError("public design source must remain outside restricted storage")
    public_root = Path(public_root).resolve(strict=True)
    store = RestrictedEvidenceStore(
        restricted_root,
        source_root=source_root,
        public_root=public_root,
    )
    source_map, source_digest = store.load_manifest(source_path)
    design_digest = hashlib.sha256(design_path.read_bytes()).hexdigest()
    manifest = build_manifest(
        design, source_map, design_sha256=design_digest,
    )
    payload = canonical_json_bytes(manifest) + b"\n"
    stored_digest = store.write_bytes(destination, payload)
    stored, observed_digest = store.load_manifest(restricted_root / destination)
    validate_evaluator_manifest(design, stored, design_sha256=design_digest)
    if observed_digest != stored_digest:
        raise ValueError("restricted manifest digest changed after immutable storage")
    return {
        "status": "PASS",
        "assignment_count": len(manifest["assignments"]),
        "source_map_sha256": source_digest,
        "manifest_sha256": stored_digest,
        "design_sha256": design_digest,
        "condition_catalog_sha256": manifest["condition_catalog_sha256"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Join approved private M36 seeds/splits to the frozen registration "
            "and write an immutable evaluator manifest."
        ),
    )
    parser.add_argument("--design", required=True, type=Path)
    parser.add_argument("--source-map", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--restricted-root", required=True, type=Path)
    parser.add_argument("--public-root", required=True, type=Path)
    parser.add_argument("--destination", default="evaluator_manifest.json")
    args = parser.parse_args(argv)

    try:
        design_path = args.design.resolve(strict=True)
        design = json.loads(design_path.read_text(encoding="utf-8"))
        summary = store_manifest(
            design,
            args.source_map,
            design_path=design_path,
            source_root=args.source_root,
            restricted_root=args.restricted_root,
            public_root=args.public_root,
            destination=args.destination,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RunnerBlocked) as error:
        print(f"M36 manifest preparation blocked: {error}", file=sys.stderr)
        return 2
    # Do not print the source map or any per-assignment seed/split values.
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
