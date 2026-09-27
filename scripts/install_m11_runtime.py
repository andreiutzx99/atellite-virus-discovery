#!/usr/bin/env python3
"""Install the locked official ViennaRNA wheel and record its runtime identity."""

from pathlib import Path
import subprocess
import sys

from satellite_discovery.m11_runtime import write_runtime_receipt


ROOT = Path(__file__).resolve().parents[1]


def main():
    subprocess.run(
        [
            sys.executable, "-m", "pip", "install",
            "--only-binary=:all:", "--require-hashes", "--force-reinstall",
            "-r", str(ROOT / "requirements-m11.lock"),
        ],
        check=True,
    )
    receipt = write_runtime_receipt()
    print(f"Provisioned pinned M11 ViennaRNA runtime; receipt: {receipt}")


if __name__ == "__main__":
    main()