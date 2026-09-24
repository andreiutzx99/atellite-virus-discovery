"""Generic Python subprocess fixtures only; no external biological tools."""
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from test_metadata import scratch_directory
from satellite_discovery import bounded_process as runner
from satellite_discovery import stage_lock


class ProcessCleanupTests(unittest.TestCase):
    def tree_command(self, root, parent_exits=False):
        child = root/'child.py'
        child.write_text("from pathlib import Path\nimport time\np=Path('heartbeat')\nfor n in range(500):\n p.write_text(str(n))\n time.sleep(.02)\n")
        parent = root/'parent.py'
        parent.write_text("import subprocess,sys,time\nfrom pathlib import Path\nsubprocess.Popen([sys.executable,'child.py'])\nwhile not Path('heartbeat').exists(): time.sleep(.01)\n"+
                          ("" if parent_exits else "time.sleep(30)\n"))
        return [sys.executable,str(parent)]

    def assert_worker_stopped(self,root):
        heartbeat=root/'heartbeat'
        self.assertTrue(heartbeat.exists(),'Worker must actually start before cleanup is tested')
        before=heartbeat.read_bytes()
        time.sleep(.2)
        self.assertEqual(before,heartbeat.read_bytes(),'Worker continued writing after cleanup returned')

    def test_timeout_stops_worker_tree_and_preserves_logs(self):
        with scratch_directory() as folder:
            root=Path(folder)
            with self.assertRaises(TimeoutError):
                runner.run(self.tree_command(root),root,'timeout.log',timeout=2)
            self.assert_worker_stopped(root)
            self.assertTrue((root/'timeout.log').exists())

    def test_interruption_stops_worker_tree(self):
        with scratch_directory() as folder:
            root=Path(folder); command=self.tree_command(root);sleep=time.sleep
            def interrupt_after_start(seconds):
                if (root/'heartbeat').exists():raise KeyboardInterrupt
                sleep(seconds)
            with patch.object(runner.time,'sleep',side_effect=interrupt_after_start):
                with self.assertRaises(KeyboardInterrupt):runner.run(command,root,'interrupt.log',timeout=5)
            self.assert_worker_stopped(root)

    @unittest.skipUnless(os.name=='posix','POSIX process-group guarantee only')
    def test_normal_parent_exit_cleans_remaining_group(self):
        with scratch_directory() as folder:
            root=Path(folder)
            runner.run(self.tree_command(root,True),root,'success.log',timeout=5)
            self.assert_worker_stopped(root)

    def test_nonzero_exit_is_failure_with_exit_status(self):
        with scratch_directory() as folder:
            with self.assertRaisesRegex(RuntimeError,'exit 7'):
                runner.run([sys.executable,'-c','raise SystemExit(7)'],folder,'failure.log')

    def test_fast_output_still_has_final_budget_check(self):
        with scratch_directory() as folder:
            root=Path(folder)
            with self.assertRaisesRegex(ValueError,'byte budget'):
                runner.run([sys.executable,'-c',"from pathlib import Path; Path('large').write_bytes(b'x'*10000)"],root,'large.log',max_bytes=100)
            self.assertTrue((root/'large').exists())

    def test_dangling_log_link_is_rejected_before_launch(self):
        with scratch_directory() as folder:
            root=Path(folder)
            try:(root/'tool.log').symlink_to(root/'not-created')
            except OSError:self.skipTest('Symlinks unavailable for this account')
            with patch.object(runner.subprocess,'Popen') as process:
                with self.assertRaisesRegex(ValueError,'link'):runner.run(['unused'],root,'tool.log')
                process.assert_not_called()
            self.assertFalse((root/'not-created').exists())

    @unittest.skipUnless(os.name=='posix','POSIX special-file fixture')
    def test_special_files_are_rejected_without_opening(self):
        with scratch_directory() as folder:
            root=Path(folder);os.mkfifo(root/'pipe')
            with self.assertRaisesRegex(ValueError,'special file'):runner.stage_bytes(root)

    def test_cleanup_error_preserves_primary_exception_and_log(self):
        with scratch_directory() as folder:
            root=Path(folder)
            def fail_after_cleanup(process):
                process.kill();process.wait(timeout=5)
                raise RuntimeError('artificial tree cleanup failure')
            with patch.object(runner,'stop_tree',side_effect=fail_after_cleanup):
                with self.assertRaises(TimeoutError) as caught:
                    runner.run([sys.executable,'-c','import time; time.sleep(30)'],root,'cleanup.log',timeout=.1)
            self.assertIn('artificial tree cleanup failure',' '.join(caught.exception.__notes__))
            self.assertIn('Cleanup warning',(root/'cleanup.log').read_text())


class StageLockTests(unittest.TestCase):
    def test_lock_identifies_owner_and_releases(self):
        import json
        with scratch_directory() as folder:
            path=Path(folder)/'.lock';token=stage_lock.acquire(path)
            data=json.loads(token)
            self.assertEqual(data['pid'],os.getpid())
            self.assertIn('host',data)
            self.assertIn('created_utc',data)
            with self.assertRaisesRegex(ValueError,'recorded PID'):stage_lock.acquire(path)
            self.assertEqual(path.read_bytes(),token)
            stage_lock.release(path,token)
            self.assertFalse(path.exists())

    def test_legacy_or_malformed_lock_is_not_removed(self):
        with scratch_directory() as folder:
            path=Path(folder)/'.lock'
            for value in (b'',b'{broken',b'x'*5000,b'[]'):
                path.write_bytes(value)
                with self.assertRaisesRegex(ValueError,'no automatic'):stage_lock.acquire(path)
                self.assertEqual(path.read_bytes(),value)

    def test_replacement_owner_is_preserved(self):
        with scratch_directory() as folder:
            path=Path(folder)/'.lock';token=stage_lock.acquire(path)
            path.write_bytes(b'replacement owner')
            with self.assertWarnsRegex(RuntimeWarning,'ownership changed'):stage_lock.release(path,token)
            self.assertEqual(path.read_bytes(),b'replacement owner')

    def test_disappeared_lock_does_not_mask_stage_error(self):
        with scratch_directory() as folder:
            path=Path(folder)/'.lock';token=stage_lock.acquire(path);path.unlink()
            with self.assertWarnsRegex(RuntimeWarning,'disappeared'):stage_lock.release(path,token)
