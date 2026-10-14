#!/usr/bin/env python3
"""Sign one canonical scientific or operator payload with an external Ed25519 key."""
import argparse
import base64
import getpass
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from satellite_discovery.trusted_single_run_acquisition import canonical_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Unsigned payload bundle JSON")
    parser.add_argument("--private-key", required=True, help="Encrypted PEM key outside the repository")
    parser.add_argument("--key-id", required=True, help="Key ID assigned in external trusted_keys.json")
    parser.add_argument("--output", required=True, help="Output signed bundle JSON")
    args = parser.parse_args()
    key_path = Path(args.private_key).expanduser().resolve(strict=True)
    repo = Path(__file__).resolve().parents[1]
    if key_path == repo or repo in key_path.parents:
        parser.error("Private signing keys must be outside the repository.")
    bundle = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(bundle, dict) or not isinstance(bundle.get("payload"), dict):
        parser.error("Input must contain a payload object.")
    password = getpass.getpass("Private-key passphrase: ").encode("utf-8")
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=password)
    if not isinstance(key, Ed25519PrivateKey):
        parser.error("Only Ed25519 private keys are accepted.")
    bundle.setdefault("signatures", [])
    if any(item.get("key_id") == args.key_id for item in bundle["signatures"]):
        parser.error("This key has already signed the bundle.")
    signature = key.sign(canonical_json(bundle["payload"]))
    bundle["signatures"].append({
        "key_id": args.key_id,
        "signature": base64.b64encode(signature).decode("ascii"),
    })
    Path(args.output).write_text(
        json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
