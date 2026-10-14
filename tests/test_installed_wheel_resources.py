import subprocess
import sys
import tempfile
import unittest
import zipfile
import os
import shutil
from pathlib import Path


ROOT = Path(__file__).parents[1]


class InstalledWheelResourceTests(unittest.TestCase):
    def test_wheel_contains_importable_exploratory_policy_resource(self):
        with tempfile.TemporaryDirectory(prefix="satellite-wheel-smoke-") as temp:
            wheelhouse = Path(temp)
            pip = shutil.which("pip")
            self.assertIsNotNone(pip, "pip executable is required for the wheel smoke test")
            result = subprocess.run(
                [pip, "wheel", "--no-deps", "--wheel-dir", str(wheelhouse), str(ROOT)],
                capture_output=True, text=True, cwd=ROOT,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            wheels = list(wheelhouse.glob("satellite_discovery-*.whl"))
            self.assertEqual(len(wheels), 1)
            with zipfile.ZipFile(wheels[0]) as wheel:
                self.assertIn(
                    "satellite_discovery/public_virus_exploratory_intake_policy.json",
                    wheel.namelist(),
                )
                self.assertIn(
                    "satellite_discovery/trusted_single_run_acquisition.py",
                    wheel.namelist(),
                )
            target = wheelhouse / "installed"
            target.mkdir()
            with zipfile.ZipFile(wheels[0]) as wheel:
                wheel.extractall(target)
            env = dict(os.environ, PYTHONPATH=str(target))
            smoke = subprocess.run(
                [sys.executable, "-c",
                 "from importlib.resources import files; "
                 "assert files('satellite_discovery').joinpath("
                 "'public_virus_exploratory_intake_policy.json').is_file(); "
                 "import satellite_discovery.trusted_single_run_acquisition"],
                check=True, capture_output=True, text=True, cwd=temp, env=env,
            )


if __name__ == "__main__":
    unittest.main()
