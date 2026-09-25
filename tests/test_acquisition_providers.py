import copy
import gzip
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from test_metadata import scratch_directory
from satellite_discovery.acquisition_fallback import (
    AcquisitionFailed, DependencyMissingError, VerificationError,
    classify, run as run_acquisition,
)
from satellite_discovery.acquisition_providers import (
    AcquisitionContext, NCBISraToolkitProvider, default_provider_registry,
)
from satellite_discovery.read_workflow import prepare_reads
from satellite_discovery.sequence_downloader import download_file, make_plan


def fallback_row():
    return {
        "run_accession": "SRR12345",
        "selection": "eligible_for_review",
        "platform": "ILLUMINA",
        "proposed_helper": "oc43-vr1558",
        "attributes": {"virus stock": "ATCC VR-1558"},
        "library_strategy": "RNA-Seq",
        "total_spots": 1000,
        "layout": "PAIRED",
        "study_accession": "SRP1",
        "fastq_ftp": None,
        "fastq_md5": None,
        "fastq_bytes": None,
    }


def write_tool(directory, name, source):
    directory = Path(directory)
    if os.name == "nt":
        script = directory / (name + ".py")
        script.write_text(source, encoding="utf-8")
        launcher = directory / (name + ".cmd")
        launcher.write_text(
            f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n',
            encoding="utf-8",
        )
        return launcher
    path = directory / name
    path.write_text("#!/usr/bin/env python3\n" + source, encoding="utf-8")
    path.chmod(0o755)
    return path


class ProviderRegistryTests(unittest.TestCase):
    def test_default_registry_has_deterministic_trusted_order(self):
        registry = default_provider_registry()
        self.assertEqual(registry.names, ["ena_fastq", "ncbi_sra_toolkit"])
        self.assertEqual(
            [row["name"] for row in registry.describe()],
            ["ena_fastq", "ncbi_sra_toolkit"],
        )
        with self.assertRaisesRegex(ValueError, "priority order"):
            registry.ordered(["ncbi_sra_toolkit", "ena_fastq"])

    def test_missing_ncbi_tools_are_reported_as_dependency_missing(self):
        provider = NCBISraToolkitProvider()
        context = AcquisitionContext(fallback_row(), Path("unused"), 1_000_000)
        with patch("satellite_discovery.acquisition_providers.shutil.which", return_value=None):
            with self.assertRaises(DependencyMissingError) as error:
                provider.resolve(context)
        self.assertEqual(classify(error.exception), "dependency_missing")
        self.assertIn("prefetch", str(error.exception))
        self.assertIn("vdb-validate", str(error.exception))
        self.assertIn("fasterq-dump", str(error.exception))

    def test_ncbi_prefetch_validate_convert_and_reuse_with_bounded_tools(self):
        fastq = "@read1/1\n" + "ACGT" * 10 + "\n+\n" + "I" * 40 + "\n"
        fastq2 = "@read1/2\n" + "TGCA" * 10 + "\n+\n" + "I" * 40 + "\n"
        with scratch_directory() as root:
            tools_dir = Path(root) / "tools"
            tools_dir.mkdir()
            calls = Path(root) / "prefetch.calls"
            tools = {
                "prefetch": write_tool(tools_dir, "prefetch", f"""
import pathlib, sys
if '--version' in sys.argv:
    print('prefetch fixture 1')
else:
    accession = sys.argv[1]
    target = pathlib.Path(accession) / (accession + '.sra')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b'fixture-sra')
    pathlib.Path({str(calls)!r}).write_text('called')
"""),
                "vdb-validate": write_tool(tools_dir, "vdb-validate", """
import pathlib, sys
if '--version' in sys.argv:
    print('vdb-validate fixture 1')
elif not pathlib.Path(sys.argv[1]).is_file():
    raise SystemExit(1)
"""),
                "fasterq-dump": write_tool(tools_dir, "fasterq-dump", f"""
import pathlib, sys
if '--version' in sys.argv:
    print('fasterq-dump fixture 1')
else:
    args = sys.argv[1:]
    accession = pathlib.Path(args[0]).stem
    out = pathlib.Path(args[args.index('--outdir') + 1])
    (out / (accession + '_1.fastq')).write_text({fastq!r})
    (out / (accession + '_2.fastq')).write_text({fastq2!r})
"""),
            }
            provider = NCBISraToolkitProvider()
            context = AcquisitionContext(
                {**fallback_row(), "layout": "PAIRED"},
                Path(root) / "run", 100_000,
            )
            with patch(
                "satellite_discovery.acquisition_providers.shutil.which",
                side_effect=lambda name: str(tools[name]),
            ):
                artifact = provider.acquire(context)
                verification = provider.verify(artifact, context)
                reused = provider.acquire(context)
            self.assertTrue(verification["verified"])
            self.assertEqual([item["role"] for item in artifact["files"]], ["R1", "R2"])
            self.assertEqual(reused["files"][0]["path"], artifact["files"][0]["path"])
            self.assertEqual(calls.read_text(), "called")
            self.assertTrue((Path(artifact["attempt_directory"]) / "vdb-validate.log").is_file())
            command = json.loads(
                (Path(artifact["attempt_directory"]) / "commands.json").read_text()
            )
            self.assertIn("--split-3", command["fasterq_dump"])
            for item in artifact["files"]:
                with gzip.open(item["path"], "rt", encoding="ascii") as handle:
                    self.assertTrue(handle.readline().startswith("@read1/"))

    def test_unknown_primary_size_reserves_the_explicit_budget(self):
        plan = make_plan([fallback_row()], 1, 123_456)
        self.assertEqual(plan["planned_bytes"], 123_456)
        selected = plan["selected"][0]
        self.assertFalse(selected["size_known"])
        self.assertEqual(selected["budget_reservation"], 123_456)
        self.assertEqual(plan["unknown_size_accessions"], ["SRR12345"])
        self.assertEqual(selected["providers"], ["ena_fastq", "ncbi_sra_toolkit"])

    def test_integrity_fallback_requires_explicit_policy_and_records_attempts(self):
        attempts = []
        called = []

        def ena():
            called.append("ena")
            raise VerificationError("checksum mismatch")

        def ncbi():
            called.append("ncbi")
            return {"provider": "ncbi_sra_toolkit"}

        result = run_acquisition(
            ["ena_fastq", "ncbi_sra_toolkit"],
            {"ena_fastq": ena, "ncbi_sra_toolkit": ncbi},
            lambda artifact: {"verified": True},
            lambda history: attempts.append(copy.deepcopy(history)),
            fallback_on={"integrity_failure"},
        )
        self.assertEqual(result["provider"], "ncbi_sra_toolkit")
        self.assertEqual(called, ["ena", "ncbi"])
        self.assertEqual([row["provider"] for row in attempts[-1]],
                         ["ena_fastq", "ncbi_sra_toolkit"])
        self.assertEqual(attempts[-1][0]["failure_class"], "integrity_failure")
        self.assertEqual(attempts[-1][1]["status"], "complete")

        called.clear()
        with self.assertRaises(AcquisitionFailed):
            run_acquisition(
                ["ena_fastq", "ncbi_sra_toolkit"],
                {"ena_fastq": ena, "ncbi_sra_toolkit": ncbi},
                lambda artifact: {"verified": True},
                lambda history: None,
            )
        self.assertEqual(called, ["ena"])

    def test_read_workflow_records_unavailable_fallback_dependency(self):
        row = fallback_row()

        class NoMetadataClient:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, *args, **kwargs):
                raise RuntimeError("network intentionally disabled in this test")

        with scratch_directory() as root:
            Path(root, "datasets.json").write_text(json.dumps([row]), encoding="utf-8")
            with patch("satellite_discovery.read_workflow.Client", NoMetadataClient), \
                    patch("satellite_discovery.acquisition_providers.shutil.which", return_value=None):
                result = prepare_reads(root, max_bytes=1_000)
            self.assertEqual(result["status"], "dependency_missing")
            item = result["runs"][0]
            self.assertEqual(item["status"], "dependency_missing")
            self.assertEqual(
                [attempt["failure_class"] for attempt in item["acquisition_attempts"]],
                ["metadata_unavailable", "dependency_missing"],
            )
            self.assertEqual(item["failure"]["providers_attempted"],
                             ["ena_fastq", "ncbi_sra_toolkit"])
            self.assertIn("prefetch", item["failure"]["next_step"])
            run_log = Path(root, "phase3", "run.log").read_text(encoding="utf-8")
            self.assertIn("Run acquisition failed", run_log)
            self.assertIn("Acquisition did not complete", run_log)

    def test_ena_transfer_attempts_record_running_and_verified_states(self):
        from test_reads import Response, spec_for
        content = b"small fixture"
        history, events = [], []
        with scratch_directory() as root, patch(
            "satellite_discovery.sequence_downloader.urlopen",
            return_value=Response(content),
        ):
            download_file(
                spec_for(content), root, progress=lambda _: None,
                attempt_history=history,
                attempt_recorder=lambda item: events.append(copy.deepcopy(item)),
            )
        self.assertEqual([event["status"] for event in events], ["running", "complete"])
        self.assertEqual(history[0]["status"], "complete")
        self.assertEqual(history[0]["observed_bytes"], len(content))


if __name__ == "__main__":
    unittest.main()