"""Check the installed distribution with isolated Python, outside source imports."""
from importlib.metadata import distribution
from importlib.resources import files
import json
import subprocess
import sys
from pathlib import Path
import shutil
import tempfile
import uuid

package = distribution('satellite-discovery')
assert any(e.name == 'satellite-reviews' for e in package.entry_points)
for name in ('helpers.json', 'model_scope.json'):
    assert json.loads(files('satellite_discovery').joinpath(name).read_text(encoding='utf-8'))
for module in ('satellite_discovery', 'satellite_discovery.review_ui'):
    result = subprocess.run([sys.executable, '-I', '-m', module, '--help'], check=True, capture_output=True, text=True)
    assert 'usage:' in result.stdout
print('Installed distribution, entry point and packaged registries verified')

from satellite_discovery.artifact_workflow import run
from satellite_discovery.dependency_review import run as dependencies

temporary_root=Path(tempfile.gettempdir()).resolve()
root=temporary_root/('satellite-install-'+uuid.uuid4().hex)
root.mkdir(mode=0o755)
try:
    dependencies(Path.cwd(),root/'dependencies')
    (root/'input.fa').write_text('>artificial\nACGTACGT\n')
    spec={'schema':'artifact-workflow-v1','stages':[
        {'id':'inventory','kind':'inventory','inputs':{'fasta':'input.fa'}},
        {'id':'quality','kind':'sequence_quality','inputs':{'fasta':{'stage':'inventory','artifact':'sequences.fasta'}}}]}
    (root/'workflow.json').write_text(json.dumps(spec))
    report=run(root/'workflow.json',root/'output')
    before=(root/'output/inventory/manifest.json').read_bytes()
    run(root/'workflow.json',root/'output')
    assert report.is_file() and before==(root/'output/inventory/manifest.json').read_bytes()
    assert json.loads((root/'output/reproducibility.json').read_text())['status']=='complete'
    print('Installed dependency check, artificial workflow, report, provenance and verified resume passed')
finally:
    if root.resolve().parent!=temporary_root:raise RuntimeError('Scratch path escaped its parent')
    shutil.rmtree(root)
