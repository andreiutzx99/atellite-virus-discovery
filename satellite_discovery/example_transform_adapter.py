"""Harmless reference adapter for testing the external-tool contract."""
from pathlib import Path
import sys

from .external_tool import ExternalToolAdapter


class ExampleTextTransformAdapter(ExternalToolAdapter):
    def __init__(self):
        super().__init__(
            kind='example_text_transform',
            module_name='example.text_transform',
            adapter_name='fixture-text-transform',
            adapter_version='1.0',
            tool_name='Python fixture text transformer',
            dependencies=[{
                'name': 'python',
                'command': sys.executable,
                'version_args': ['--version'],
            }],
            input_fields={'source'},
            output_files=['transformed.txt'],
            timeout=20,
            max_bytes=1_000_000,
            description='Copies a text fixture with a configured prefix; no analysis.',
        )

    def validate_config(self, config):
        if not isinstance(config, dict) or set(config) - {'prefix'}:
            raise ValueError('Example adapter config accepts only prefix')
        prefix = config.get('prefix', 'fixture:')
        if not isinstance(prefix, str) or len(prefix) > 128 or '\0' in prefix:
            raise ValueError('Example prefix must be text of at most 128 characters')
        return {'prefix': prefix}

    def build_command(self, executables, inputs, output, config):
        tool = Path(__file__).with_name('example_transform_tool.py').resolve(strict=True)
        return [
            executables['python'],
            '-I',
            str(tool),
            str(inputs['source']),
            str(output/'transformed.txt'),
            config['prefix'],
        ]