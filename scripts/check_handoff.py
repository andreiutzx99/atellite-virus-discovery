"""Read-only source handoff checks. Does not certify CI or application completeness."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess


REQUIRED_FILES = (
    'docs/DEVELOPMENT_HANDOFF.md', 'pyproject.toml', '.github/workflows/tests.yml',
    'satellite_discovery/artifact_workflow.py', 'tests/test_handoff.py',
    'scripts/check_handoff.py',
)


def git(repo, *args):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0')
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                            text=True, encoding='utf-8', errors='replace',
                            timeout=30, env=env)
    if result.returncode:
        # Do not echo remote URLs, credentials or arbitrary server output.
        raise RuntimeError('Git check failed: ' + args[0])
    return result.stdout.strip()


def inspect(repo, expected_commit=None):
    """Compare HEAD, local main, tracking main and live origin main; never fetch/write."""
    result = {'schema': 'source-handoff-v1',
              'checked_utc': datetime.now(timezone.utc).isoformat(),
              'source_status': 'NOT READY', 'ci_status': 'not_checked',
              'application_completeness': 'not_assessed', 'problems': [],
              'scope': 'Tracked source and non-ignored uncommitted files; ignored data, '
                       'tools, environments, other clones and server-only branches are not certified.'}
    try:
        repo = Path(repo).resolve(strict=True)
        if expected_commit is not None and not re.fullmatch(r'[0-9a-fA-F]{40}|[0-9a-fA-F]{64}', expected_commit):
            raise ValueError('Expected commit must be a full hexadecimal object ID')
        if Path(git(repo, 'rev-parse', '--show-toplevel')).resolve() != repo:
            raise ValueError('Provide the repository root')
        if git(repo, 'rev-parse', '--is-shallow-repository') != 'false':
            raise ValueError('Full Git history is required to assess unmerged local branches')
        result['branch'] = git(repo, 'symbolic-ref', '--quiet', '--short', 'HEAD')
        result['head'] = git(repo, 'rev-parse', 'HEAD')
        result['local_main'] = git(repo, 'rev-parse', 'refs/heads/main')
        result['tracking_main'] = git(repo, 'rev-parse', 'refs/remotes/origin/main')
        remote = git(repo, 'ls-remote', '--exit-code', 'origin', 'refs/heads/main').split()
        if len(remote) != 2 or remote[1] != 'refs/heads/main':
            raise ValueError('Live origin main could not be verified')
        result['remote_main'] = remote[0]
        result['source_tree'] = git(repo, 'rev-parse', 'HEAD^{tree}')
        result['uncommitted'] = bool(git(repo, 'status', '--porcelain', '--untracked-files=all'))
        result['unmerged_local_branches'] = git(repo, 'for-each-ref', '--format=%(refname:short)',
                                                '--no-merged=refs/heads/main', 'refs/heads').splitlines()
        result['stashes_present'] = bool(git(repo, 'stash', 'list', '--format=%gd'))
        tracked = set(git(repo, 'ls-tree', '-r', '--name-only', 'HEAD').splitlines())
        result['missing_required_files'] = [p for p in REQUIRED_FILES if p not in tracked]
        problems = result['problems']
        if result['branch'] != 'main':
            problems.append('The checked-out branch is not main')
        if len({result[k] for k in ('head', 'local_main', 'tracking_main', 'remote_main')}) != 1:
            problems.append('HEAD, local main, tracking main and live origin main do not match')
        if expected_commit and result['head'] != expected_commit.lower():
            problems.append('HEAD does not match the expected handoff commit')
        if result['uncommitted']:
            problems.append('Uncommitted or untracked non-ignored files remain')
        if result['unmerged_local_branches']:
            problems.append('Local branches contain commits outside main; inspect before handoff')
        if result['stashes_present']:
            problems.append('Stashed work requires inspection before handoff')
        if result['missing_required_files']:
            problems.append('Required handoff files are absent from the committed tree')
        # Detect ordinary concurrent edits/ref movement; this is a snapshot, not a lock.
        if git(repo, 'rev-parse', 'HEAD') != result['head'] or git(repo, 'status', '--porcelain', '--untracked-files=all'):
            problems.append('Checkout changed or is dirty at the end of verification')
        if not problems:
            result['source_status'] = 'READY'
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        result['problems'].append('Git command timed out' if isinstance(exc, subprocess.TimeoutExpired) else str(exc))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--expected-commit')
    args = parser.parse_args(argv)
    result = inspect(args.repo, args.expected_commit)
    print(json.dumps(result, indent=2))
    return 0 if result['source_status'] == 'READY' else 1


if __name__ == '__main__':
    raise SystemExit(main())
