"""Release checks against disposable local Git repositories, with no network/data analysis."""
import importlib.util
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('check_handoff', Path(__file__).resolve().parents[1] / 'scripts/check_handoff.py')
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


@unittest.skipUnless(shutil.which('git'), 'Git is required for handoff fixture tests')
class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='handoff-test-')).resolve()
        self.remote = self.root / 'remote.git'
        self.repo = self.root / 'checkout'
        self.run_git('init', '--bare', str(self.remote), cwd=self.root)
        self.run_git('init', '-b', 'main', str(self.repo), cwd=self.root)
        self.run_git('config', 'user.name', 'Fixture')
        self.run_git('config', 'user.email', 'fixture@example.invalid')
        for name in handoff.REQUIRED_FILES:
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture\n', encoding='utf-8')
        self.commit()
        self.run_git('remote', 'add', 'origin', str(self.remote))
        self.run_git('push', '-u', 'origin', 'main')

    def tearDown(self):
        def writable(func, path, error):
            Path(path).chmod(stat.S_IWRITE | stat.S_IREAD)
            func(path)
        if self.root.parent != Path(tempfile.gettempdir()).resolve():
            raise RuntimeError('Unexpected scratch location')
        shutil.rmtree(self.root, onerror=writable)

    def run_git(self, *args, cwd=None):
        return subprocess.run(['git', '-C', str(cwd or self.repo), *args], check=True,
                              capture_output=True, text=True, timeout=30).stdout.strip()

    def commit(self):
        self.run_git('add', '.')
        self.run_git('commit', '-m', 'Fixture change')

    def test_clean_published_main_and_merged_branch_are_ready_without_mutation(self):
        self.run_git('branch', 'already-merged')
        index = (self.repo / '.git/index').read_bytes()
        result = handoff.inspect(self.repo, self.run_git('rev-parse', 'HEAD'))
        self.assertEqual(result['source_status'], 'READY', result)
        self.assertEqual(result['ci_status'], 'not_checked')
        self.assertEqual(result['local_main'], result['remote_main'])
        self.assertEqual(index, (self.repo / '.git/index').read_bytes())

    def test_untracked_and_modified_files_block_handoff(self):
        for path in ('new.txt', handoff.REQUIRED_FILES[0]):
            with self.subTest(path=path):
                (self.repo / path).write_text('changed')
                result = handoff.inspect(self.repo)
                self.assertEqual(result['source_status'], 'NOT READY')
                self.assertTrue(result['uncommitted'])
                if path == 'new.txt':
                    (self.repo / path).unlink()
                else:
                    (self.repo / path).write_text('fixture\n')

    def test_unpublished_main_commit_blocks_handoff(self):
        (self.repo / 'new.txt').write_text('new')
        self.commit()
        self.assertEqual(handoff.inspect(self.repo)['source_status'], 'NOT READY')

    def test_live_remote_detects_stale_tracking_ref(self):
        old = self.run_git('rev-parse', 'HEAD')
        (self.repo / 'new.txt').write_text('new')
        self.commit()
        new = self.run_git('rev-parse', 'HEAD')
        self.run_git('push', 'origin', 'main')
        self.run_git('reset', '--hard', old)
        self.run_git('update-ref', 'refs/remotes/origin/main', old)
        result = handoff.inspect(self.repo)
        self.assertEqual(result['remote_main'], new)
        self.assertEqual(result['source_status'], 'NOT READY')

    def test_unmerged_branch_blocks_even_when_main_is_published(self):
        self.run_git('switch', '-c', 'unfinished')
        (self.repo / 'new.txt').write_text('new')
        self.commit()
        self.run_git('switch', 'main')
        result = handoff.inspect(self.repo)
        self.assertEqual(result['source_status'], 'NOT READY')
        self.assertEqual(result['unmerged_local_branches'], ['unfinished'])

    def test_stashed_work_blocks_handoff(self):
        (self.repo / handoff.REQUIRED_FILES[0]).write_text('change')
        self.run_git('stash', 'push')
        self.assertTrue(handoff.inspect(self.repo)['stashes_present'])
        self.assertEqual(handoff.inspect(self.repo)['source_status'], 'NOT READY')

    def test_missing_committed_handoff_file_blocks(self):
        (self.repo / handoff.REQUIRED_FILES[0]).unlink()
        self.commit()
        self.run_git('push', 'origin', 'main')
        result = handoff.inspect(self.repo)
        self.assertEqual(result['missing_required_files'], [handoff.REQUIRED_FILES[0]])
        self.assertEqual(result['source_status'], 'NOT READY')

    def test_wrong_expected_commit_blocks(self):
        self.assertEqual(handoff.inspect(self.repo, '0' * 40)['source_status'], 'NOT READY')

    def test_detached_head_blocks(self):
        self.run_git('switch', '--detach')
        self.assertEqual(handoff.inspect(self.repo)['source_status'], 'NOT READY')

    def test_unavailable_remote_blocks_without_leaking_remote_output(self):
        self.run_git('remote', 'set-url', 'origin', str(self.root / 'absent.git'))
        result = handoff.inspect(self.repo)
        self.assertEqual(result['source_status'], 'NOT READY')
        self.assertEqual(result['problems'], ['Git check failed: ls-remote'])

    def test_timeout_and_invalid_expected_commit_fail_closed(self):
        with patch.object(handoff, 'git', side_effect=subprocess.TimeoutExpired('git', 30)):
            result = handoff.inspect(self.repo)
            self.assertEqual(result['source_status'], 'NOT READY')
            self.assertEqual(result['problems'], ['Git command timed out'])
        self.assertEqual(handoff.inspect(self.repo, '--bad')['source_status'], 'NOT READY')

    def test_shallow_clone_requires_full_history(self):
        clone = self.root / 'shallow'
        self.run_git('clone', '--depth=1', '--branch=main', self.remote.as_uri(), str(clone), cwd=self.root)
        result = handoff.inspect(clone)
        self.assertEqual(result['source_status'], 'NOT READY')
        self.assertIn('Full Git history', result['problems'][0])
