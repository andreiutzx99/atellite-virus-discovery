"""Trusted-code registry for artifact workflow stages.

Workflow JSON selects registered names and supplies data only. It cannot load
Python modules, call arbitrary functions, or provide shell commands.
"""
from dataclasses import dataclass
import re


_STAGE_NAME = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,63}\Z')
_MODULE_NAME = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,127}\Z')


def valid_module_name(value):
    return isinstance(value, str) and bool(_MODULE_NAME.fullmatch(value))


@dataclass(frozen=True)
class StageDefinition:
    kind: str
    input_fields: frozenset[str] | None
    optional_input_fields: frozenset[str]
    handler: object
    version: str
    external_tool: bool
    module_name: str | None
    config_validator: object
    dynamic_inputs: bool = False
    description: str = ''


class WorkflowStageRegistry:
    """Deterministic registry populated by trusted application code."""

    def __init__(self):
        self._stages = {}
        self._modules = {}

    def register(self, kind, input_fields, handler, *, optional_input_fields=(),
                 version='1',
                 external_tool=False, module_name=None, config_validator=None,
                 dynamic_inputs=False, description=''):
        if not isinstance(kind, str) or not _STAGE_NAME.fullmatch(kind):
            raise ValueError('Stage kind must be a safe registered name')
        if kind in self._stages:
            raise ValueError(f'Duplicate stage registration: {kind}')
        if isinstance(version, bool) or not isinstance(version, str) or not version.strip():
            raise ValueError('Stage version must be a non-empty string')
        if dynamic_inputs:
            if input_fields is not None or optional_input_fields:
                raise ValueError('Dynamic-input stages must not declare fixed fields')
            fields = None
            optional_fields = frozenset()
        else:
            if not isinstance(input_fields, (set, frozenset, tuple, list)):
                raise ValueError('Stage input fields must be a collection')
            if not isinstance(optional_input_fields, (set, frozenset, tuple, list)):
                raise ValueError('Optional stage input fields must be a collection')
            if any(not isinstance(name, str) or not _STAGE_NAME.fullmatch(name)
                   for name in tuple(input_fields)+tuple(optional_input_fields)):
                raise ValueError('Stage input names must be safe identifiers')
            fields = frozenset(input_fields)
            optional_fields = frozenset(optional_input_fields)
            if fields & optional_fields:
                raise ValueError('An input cannot be both required and optional')
        if handler is None and kind != 'external_module':
            raise ValueError('Registered stage requires a trusted handler')
        if module_name is not None:
            if not valid_module_name(module_name):
                raise ValueError('Module name must be a safe identifier')
            if module_name in self._modules:
                raise ValueError(f'Duplicate module registration: {module_name}')
        validator = config_validator or _empty_config
        if not callable(validator):
            raise ValueError('Configuration validator must be callable')
        definition = StageDefinition(
            kind=kind,
            input_fields=fields,
            optional_input_fields=optional_fields,
            handler=handler,
            version=version,
            external_tool=bool(external_tool),
            module_name=module_name,
            config_validator=validator,
            dynamic_inputs=dynamic_inputs,
            description=description,
        )
        self._stages[kind] = definition
        if module_name is not None:
            self._modules[module_name] = definition
        return definition

    def register_external_adapter(self, adapter):
        """Register an already constructed trusted adapter instance."""
        required = ('kind', 'input_fields', 'adapter_version', 'module_name',
                    'validate_config', 'inspect_dependency', 'execute')
        if any(not hasattr(adapter, name) for name in required):
            raise ValueError('External adapter does not implement the required contract')
        return self.register(
            adapter.kind,
            adapter.input_fields,
            adapter,
            optional_input_fields=getattr(adapter, 'optional_input_fields', ()),
            version=adapter.adapter_version,
            external_tool=True,
            module_name=adapter.module_name,
            config_validator=adapter.validate_config,
            description=getattr(adapter, 'description', ''),
        )

    def get(self, kind):
        try:
            return self._stages[kind]
        except (KeyError, TypeError):
            raise ValueError(f'Unknown workflow stage: {kind!r}') from None

    def get_module(self, name):
        return self._modules.get(name)

    def has_module(self, name):
        return name in self._modules

    def validate_config(self, kind, value):
        definition = self.get(kind)
        if not isinstance(value, dict):
            raise ValueError('Stage config must be an object')
        normalized = definition.config_validator(dict(value))
        if not isinstance(normalized, dict):
            raise ValueError('Stage config validator must return an object')
        return normalized

    @property
    def fields(self):
        """Compatibility view of fixed-input stage contracts."""
        return {
            kind: set(definition.input_fields | definition.optional_input_fields)
            for kind, definition in self._stages.items()
            if not definition.dynamic_inputs
        }

    def describe(self):
        """Return stable, reportable registration metadata (never callables)."""
        return [
            {
                'kind': definition.kind,
                'input_fields': sorted(definition.input_fields or ()),
                'optional_input_fields': sorted(definition.optional_input_fields),
                'version': definition.version,
                'external_tool': definition.external_tool,
                'module_name': definition.module_name,
                'description': definition.description,
                'dynamic_inputs': definition.dynamic_inputs,
            }
            for definition in sorted(self._stages.values(), key=lambda item: item.kind)
        ]

    def module_names(self):
        return tuple(sorted(self._modules))


def _empty_config(config):
    if config:
        raise ValueError('This stage does not accept configuration')
    return {}