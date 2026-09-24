"""Check the installed distribution with isolated Python, outside source imports."""
from importlib.metadata import distribution
from importlib.resources import files
import json
import subprocess
import sys

package = distribution('satellite-discovery')
assert any(e.name == 'satellite-reviews' for e in package.entry_points)
for name in ('helpers.json', 'model_scope.json'):
    assert json.loads(files('satellite_discovery').joinpath(name).read_text(encoding='utf-8'))
for module in ('satellite_discovery', 'satellite_discovery.review_ui'):
    result = subprocess.run([sys.executable, '-I', '-m', module, '--help'], check=True, capture_output=True, text=True)
    assert 'usage:' in result.stdout
print('Installed distribution, entry point and packaged registries verified')
