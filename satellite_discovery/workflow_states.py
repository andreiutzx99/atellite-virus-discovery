"""Explicit workflow states and transitions for artifact workflows."""

STAGE_STATES = frozenset({
    'pending',
    'running',
    'complete',
    'skipped',
    'dependency_missing',
    'external_module_required',
    'failed',
    'interrupted',
})

STAGE_TRANSITIONS = {
    'pending': frozenset({
        'running', 'skipped', 'dependency_missing', 'external_module_required',
    }),
    'running': frozenset({
        'complete', 'dependency_missing', 'external_module_required',
        'failed', 'interrupted',
    }),
    'complete': frozenset(),
    'skipped': frozenset(),
    'dependency_missing': frozenset(),
    'external_module_required': frozenset(),
    'failed': frozenset(),
    'interrupted': frozenset(),
}

WORKFLOW_STATES = STAGE_STATES | frozenset({'partial'})
WORKFLOW_TRANSITIONS = {
    'pending': frozenset({'running'}),
    'running': frozenset({
        'complete', 'skipped', 'dependency_missing',
        'external_module_required', 'failed', 'interrupted', 'partial',
    }),
    'complete': frozenset(),
    'skipped': frozenset(),
    'dependency_missing': frozenset(),
    'external_module_required': frozenset(),
    'failed': frozenset(),
    'interrupted': frozenset(),
    'partial': frozenset(),
}


def transition(record, target, transitions=STAGE_TRANSITIONS, **fields):
    """Set a state only when the requested transition is valid."""
    current = record.get('status')
    if current not in transitions or target not in transitions[current]:
        raise ValueError(f'Invalid workflow state transition: {current!r} -> {target!r}')
    record.update(fields)
    record['status'] = target
    return record


def aggregate_stage_status(stages):
    """Summarize terminal stage states without treating blocked work as success."""
    states = [stage['status'] for stage in stages]
    if not states or all(state == 'complete' for state in states):
        return 'complete'
    if 'failed' in states:
        return 'failed'
    if 'interrupted' in states:
        return 'interrupted'
    if 'dependency_missing' in states:
        return 'dependency_missing'
    if 'external_module_required' in states:
        return 'external_module_required'
    if all(state == 'skipped' for state in states):
        return 'skipped'
    if any(state in {'pending', 'running'} for state in states):
        return 'running'
    return 'partial'