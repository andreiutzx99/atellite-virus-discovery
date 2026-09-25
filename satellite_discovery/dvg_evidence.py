"""Strict parsing and validation for caller-generated DVG evidence."""
import json
from pathlib import Path
import re
import stat


PARSER_VERSION = '1'

DVG_EVIDENCE_DETECTED = 'DVG_EVIDENCE_DETECTED'
NO_DVG_EVIDENCE_DETECTED = 'NO_DVG_EVIDENCE_DETECTED'
NOT_EVALUATED = 'NOT_EVALUATED'
ANALYSIS_UNAVAILABLE = 'ANALYSIS_UNAVAILABLE'
ANALYSIS_FAILED = 'ANALYSIS_FAILED'
INVALID_RESULT = 'INVALID_RESULT'

_STATUSES = {
    DVG_EVIDENCE_DETECTED,
    NO_DVG_EVIDENCE_DETECTED,
    NOT_EVALUATED,
    ANALYSIS_UNAVAILABLE,
    ANALYSIS_FAILED,
    INVALID_RESULT,
}
_MAX_NATIVE_BYTES = 32_000_000
_MAX_STDOUT_BYTES = 8_000_000
_MAX_EVENTS = 200_000
_HASH = re.compile(r'^[0-9a-f]{64}$')
_ENTRY = re.compile(r'^([1-9][0-9]*)_to_([1-9][0-9]*)_#_([1-9][0-9]*)$')


class InvalidDVGResultError(ValueError):
    """Raised when native or normalized evidence is incomplete or invalid."""


def _read_bounded_utf8(path, limit, label, *, allow_empty=False):
    path = Path(path)
    try:
        info = path.lstat()
    except OSError as error:
        raise InvalidDVGResultError(f'{label} is missing or unreadable') from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise InvalidDVGResultError(f'{label} must be a regular non-symlink file')
    if info.st_size > limit:
        raise InvalidDVGResultError(f'{label} exceeds the {limit}-byte limit')
    try:
        data = path.read_bytes()
        if len(data) > limit:
            raise InvalidDVGResultError(f'{label} exceeds the {limit}-byte limit')
        text = data.decode('utf-8', errors='strict')
    except (OSError, UnicodeDecodeError) as error:
        raise InvalidDVGResultError(f'{label} is unreadable or not valid UTF-8') from error
    if not text and not allow_empty:
        raise InvalidDVGResultError(f'{label} is empty')
    if '\x00' in text:
        raise InvalidDVGResultError(f'{label} contains a NUL byte')
    return text


def _library_parts(library, references):
    # Reference identifiers may themselves contain "_to_"; test every exact
    # split against the declared reference set rather than splitting blindly.
    matches = []
    aliases = {name: (name, '+') for name in references}
    aliases.update({name + '_RevStrand': (name, '-') for name in references})
    for donor_name, (donor_id, donor_orientation) in aliases.items():
        token = donor_name + '_to_'
        if library.startswith(token):
            acceptor_alias = library[len(token):]
            if acceptor_alias in aliases:
                acceptor_id, acceptor_orientation = aliases[acceptor_alias]
                matches.append((donor_id, acceptor_id, donor_orientation, acceptor_orientation))
    if len(matches) != 1:
        raise InvalidDVGResultError(
            f'Library section has unknown or ambiguous reference pair: {library!r}')
    return matches[0]


def parse_virema_results(path, references: dict[str, int], stdout_path, *,
                         expected_read_count=None):
    """Parse pinned ViReMa 0.25 compiled virus-virus junction output.

    A truly empty compiled file is the only zero-event representation. A
    positive result must consist solely of complete three-line library blocks.
    """
    if (not isinstance(references, dict) or not references
            or any(not isinstance(name, str) or not name or name.endswith('_RevStrand')
                   or not isinstance(length, int) or isinstance(length, bool) or length < 1
                   for name, length in references.items())):
        raise InvalidDVGResultError('Reference identifiers and positive lengths are required')
    if (expected_read_count is not None
            and (not isinstance(expected_read_count, int) or isinstance(expected_read_count, bool)
                 or expected_read_count < 1)):
        raise InvalidDVGResultError('expected_read_count must be a positive integer')
    # Native suffix aliases are generated from the declared forward reference.
    native = _read_bounded_utf8(path, _MAX_NATIVE_BYTES, 'ViReMa result',
                                allow_empty=True)
    stdout = _read_bounded_utf8(stdout_path, _MAX_STDOUT_BYTES, 'ViReMa stdout')
    analyzed = re.findall(
        r'(?m)^Total of ([0-9]+) reads have been analysed:\s*$', stdout)
    recombinations = re.findall(
        r'(?m)^of which ([0-9]+) were Viral Recombinations, ([0-9]+) were Host '
        r'Recombinations and ([0-9]+) were Virus-to-Host Recombinations\s*$', stdout)
    completion_marker = re.compile(r'^Time to complete in seconds:  [0-9]+(?:\.[0-9]+)?$')
    completion_lines = [
        line for line in stdout.splitlines() if completion_marker.fullmatch(line)
    ]
    nonempty_stdout_lines = [line for line in stdout.splitlines() if line.strip()]
    if (len(analyzed) != 1 or len(recombinations) != 1
            or len(completion_lines) != 1 or not nonempty_stdout_lines
            or not completion_marker.fullmatch(nonempty_stdout_lines[-1])):
        raise InvalidDVGResultError('ViReMa stdout is missing or duplicates required count markers')
    if (expected_read_count is not None
            and int(analyzed[0]) != expected_read_count):
        raise InvalidDVGResultError('ViReMa analysed-read count does not match expected_read_count')

    if native == '':
        if int(recombinations[0][0]) != 0:
            raise InvalidDVGResultError('Empty result conflicts with positive stdout recombination count')
        return []
    if not native.endswith('\n'):
        raise InvalidDVGResultError('Non-empty ViReMa result is truncated without its final newline')

    # Keep native line endings out of token values while retaining the exact
    # human-visible output line for provenance.
    lines = native.splitlines()
    if any(not line for line in lines):
        raise InvalidDVGResultError('ViReMa result contains an unexpected blank line')
    events = []
    seen_libraries = set()
    seen_entries = set()
    supporting_reads = 0
    index = 0
    while index < len(lines):
        header = lines[index]
        match = re.fullmatch(
            r'@NewLibrary: ([A-Za-z0-9_.:|+-]+_to_[A-Za-z0-9_.:|+-]+)', header)
        if not match:
            raise InvalidDVGResultError(f'Unexpected or malformed ViReMa section header at line {index + 1}')
        library = match.group(1)
        if library in seen_libraries:
            raise InvalidDVGResultError(f'Duplicate ViReMa library section: {library}')
        seen_libraries.add(library)
        if index + 2 >= len(lines) or lines[index + 2] != '@EndofLibrary':
            raise InvalidDVGResultError(f'Truncated ViReMa section for {library}')
        output_line = lines[index + 1]
        if output_line.startswith('@') or not output_line or not output_line.endswith('\t'):
            raise InvalidDVGResultError(f'Missing event line for {library}')
        donor, acceptor, donor_orientation, acceptor_orientation = _library_parts(
            library, references)
        entries = output_line.split('\t')
        entries.pop()  # Exactly one terminal tab is part of the native format.
        if not entries or any(not entry for entry in entries):
            raise InvalidDVGResultError(f'Malformed event list for {library}')
        for entry in entries:
            parsed = _ENTRY.fullmatch(entry)
            if not parsed:
                raise InvalidDVGResultError(f'Malformed ViReMa event token: {entry!r}')
            breakpoint_1, breakpoint_2, support = map(int, parsed.groups())
            if breakpoint_1 > references[donor] or breakpoint_2 > references[acceptor]:
                raise InvalidDVGResultError(f'ViReMa event coordinate exceeds reference bounds: {entry!r}')
            duplicate_key = (library, entry)
            if duplicate_key in seen_entries:
                raise InvalidDVGResultError(f'Duplicate ViReMa event token: {entry!r}')
            seen_entries.add(duplicate_key)
            supporting_reads += support
            events.append({
                'reference_id': donor,
                'acceptor_reference_id': acceptor,
                'breakpoint_1': breakpoint_1,
                'breakpoint_2': breakpoint_2,
                'orientation': {
                    'donor': donor_orientation,
                    'acceptor': acceptor_orientation,
                },
                'supporting_read_count': support,
                'raw_output_line': output_line,
                'raw_line_number': index + 2,
                'raw_entry': entry,
                'raw_library': library,
                'event_type': 'virus-virus_junction',
            })
            if len(events) > _MAX_EVENTS:
                raise InvalidDVGResultError('ViReMa result exceeds the event limit')
        index += 3
    if not events:
        raise InvalidDVGResultError('Non-empty ViReMa result contains no events')
    if supporting_reads != int(recombinations[0][0]):
        raise InvalidDVGResultError(
            'Summed event support does not match ViReMa stdout recombination count')
    return events


def _is_nonnegative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_hashes(value, context='document'):
    """Validate any explicitly named SHA-256 fields in a JSON-like structure."""
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and ('sha256' in key.lower() or key.lower() == 'hash'):
                if item is not None and (not isinstance(item, str) or not _HASH.fullmatch(item)):
                    raise InvalidDVGResultError(f'{context} contains an invalid SHA-256 value')
            _validate_hashes(item, context)
    elif isinstance(value, list):
        for item in value:
            _validate_hashes(item, context)


def _validate_event(event, index, caller, reference_lengths=None):
    label = f'event {index}'
    if not isinstance(event, dict):
        raise InvalidDVGResultError(f'{label} must be an object')
    for field in ('reference_id', 'acceptor_reference_id'):
        if not isinstance(event.get(field), str) or not event[field]:
            raise InvalidDVGResultError(f'{label} is missing {field}')
    if reference_lengths is not None:
        for field, ref_field in (('breakpoint_1', 'reference_id'),
                                 ('breakpoint_2', 'acceptor_reference_id')):
            bound = reference_lengths.get(event[ref_field])
            if bound is None:
                raise InvalidDVGResultError(f'{label} refers to an undeclared reference')
            if not _is_nonnegative_int(event.get(field)) or not 1 <= event[field] <= bound:
                raise InvalidDVGResultError(f'{label} coordinate is outside reference bounds')
    else:
        for field in ('breakpoint_1', 'breakpoint_2'):
            if not _is_nonnegative_int(event.get(field)) or event[field] < 1:
                raise InvalidDVGResultError(f'{label} has an invalid {field}')
    support = event.get('supporting_read_count')
    if support is not None and (not _is_nonnegative_int(support) or support < 1):
        raise InvalidDVGResultError(f'{label} has an invalid supporting read count')
    if 'orientation' in event:
        orientation = event['orientation']
        if (not isinstance(orientation, dict)
                or orientation.get('donor') not in {'+', '-'}
                or orientation.get('acceptor') not in {'+', '-'}):
            raise InvalidDVGResultError(f'{label} has invalid strand orientation')
    if 'caller' in event and event['caller'] != caller:
        raise InvalidDVGResultError(f'{label} caller does not match its document')
    if 'event_type' in event and (
            not isinstance(event['event_type'], str) or not event['event_type']):
        raise InvalidDVGResultError(f'{label} has an invalid event type')
    for field in ('evidence_id', 'raw_entry', 'raw_library'):
        if field in event and (not isinstance(event[field], str) or not event[field]):
            raise InvalidDVGResultError(f'{label} has an invalid {field}')
    if 'reference_length' in event and (
            not _is_nonnegative_int(event['reference_length']) or event['reference_length'] < 1):
        raise InvalidDVGResultError(f'{label} has an invalid reference length')
    if 'acceptor_reference_length' in event and (
            not _is_nonnegative_int(event['acceptor_reference_length'])
            or event['acceptor_reference_length'] < 1):
        raise InvalidDVGResultError(f'{label} has an invalid acceptor reference length')
    if event.get('reference_length') is not None and event['breakpoint_1'] > event['reference_length']:
        raise InvalidDVGResultError(f'{label} breakpoint_1 exceeds its declared reference length')
    if (event.get('acceptor_reference_length') is not None
            and event['breakpoint_2'] > event['acceptor_reference_length']):
        raise InvalidDVGResultError(f'{label} breakpoint_2 exceeds its declared reference length')


def validate_evidence_document(value):
    """Validate a normalized ``dvg-evidence-v1`` JSON document."""
    if not isinstance(value, dict) or value.get('schema') != 'dvg-evidence-v1':
        raise InvalidDVGResultError('Evidence document schema must be dvg-evidence-v1')
    caller = value.get('caller')
    status = value.get('status')
    events = value.get('events')
    if not isinstance(caller, str) or not caller.strip():
        raise InvalidDVGResultError('Evidence document requires a caller')
    if status not in _STATUSES:
        raise InvalidDVGResultError('Evidence document has an unsupported status')
    if not isinstance(events, list) or len(events) > _MAX_EVENTS:
        raise InvalidDVGResultError('Evidence document events must be a bounded list')
    reference_lengths = value.get('reference_lengths')
    if reference_lengths is not None:
        if (not isinstance(reference_lengths, dict)
                or any(not isinstance(k, str) or not k or not _is_nonnegative_int(v) or v < 1
                       for k, v in reference_lengths.items())):
            raise InvalidDVGResultError('Evidence document reference_lengths is malformed')
    for index, event in enumerate(events, 1):
        _validate_event(event, index, caller, reference_lengths)
    if status == DVG_EVIDENCE_DETECTED and not events:
        raise InvalidDVGResultError('Detected evidence status requires at least one event')
    if status == NO_DVG_EVIDENCE_DETECTED and events:
        raise InvalidDVGResultError('No-evidence status cannot contain events')
    if status in {NOT_EVALUATED, ANALYSIS_UNAVAILABLE, ANALYSIS_FAILED, INVALID_RESULT} and events:
        raise InvalidDVGResultError('Incomplete evaluation status cannot contain successful events')
    _validate_hashes(value)
    return value


def validate_summary(value):
    """Validate a caller-neutral ``dvg-summary-v1`` evaluation summary."""
    if not isinstance(value, dict) or value.get('schema') != 'dvg-summary-v1':
        raise InvalidDVGResultError('Summary schema must be dvg-summary-v1')
    if not isinstance(value.get('caller'), str) or not value['caller'].strip():
        raise InvalidDVGResultError('Summary requires a caller')
    if value.get('status') not in _STATUSES:
        raise InvalidDVGResultError('Summary has an unsupported status')
    count = value.get('event_count')
    if not _is_nonnegative_int(count):
        raise InvalidDVGResultError('Summary event_count must be a non-negative integer')
    status = value['status']
    if status == DVG_EVIDENCE_DETECTED and count < 1:
        raise InvalidDVGResultError('Detected summary requires a positive event_count')
    if status == NO_DVG_EVIDENCE_DETECTED and count != 0:
        raise InvalidDVGResultError('No-evidence summary requires event_count zero')
    if status in {NOT_EVALUATED, ANALYSIS_UNAVAILABLE, ANALYSIS_FAILED, INVALID_RESULT} and count != 0:
        raise InvalidDVGResultError('Incomplete summary cannot report successful events')
    for key in ('event_references', 'events'):
        if key in value and not isinstance(value[key], list):
            raise InvalidDVGResultError(f'Summary {key} must be a list')
    _validate_hashes(value)
    return value


def _event_signatures(summary):
    records = summary.get('event_references', summary.get('events', []))
    signatures = set()
    for record in records:
        if isinstance(record, str):
            signatures.add(record)
        elif isinstance(record, dict):
            refs = (record.get('reference_id'), record.get('acceptor_reference_id'),
                    record.get('breakpoint_1'), record.get('breakpoint_2'),
                    json.dumps(record.get('orientation', {}), sort_keys=True))
            signatures.add(json.dumps(refs, sort_keys=True))
        else:
            signatures.add(json.dumps(record, sort_keys=True))
    return signatures


def aggregate_evaluations(evaluation_summaries):
    """Combine caller summaries without inferring any biological negative class."""
    if not isinstance(evaluation_summaries, (list, tuple)):
        raise InvalidDVGResultError('Evaluation summaries must be a list')
    summaries = []
    callers = set()
    for summary in evaluation_summaries:
        validate_summary(summary)
        if summary['caller'] in callers:
            raise InvalidDVGResultError('Evaluation summaries contain a duplicate caller')
        callers.add(summary['caller'])
        summaries.append(summary)
    detected = [item for item in summaries if item['status'] == DVG_EVIDENCE_DETECTED]
    unavailable = [item for item in summaries if item['status'] == ANALYSIS_UNAVAILABLE]
    failed = [item for item in summaries if item['status'] in {ANALYSIS_FAILED, INVALID_RESULT}]
    evaluated = [item for item in summaries if item['status'] in {
        DVG_EVIDENCE_DETECTED, NO_DVG_EVIDENCE_DETECTED}]
    if detected:
        signature_sets = [_event_signatures(item) for item in detected]
        if len(detected) == 1:
            classification = 'CALLER_ONLY'
        elif all(signature_sets) and all(items == signature_sets[0] for items in signature_sets[1:]):
            classification = 'MULTIPLE_CALLERS'
        elif any(signature_sets) and len(set(map(frozenset, signature_sets))) > 1:
            classification = 'CONFLICTING_OUTPUTS'
        else:
            classification = 'MULTIPLE_CALLERS'
    elif unavailable:
        classification = 'CALLER_UNAVAILABLE'
    elif failed:
        classification = 'CALLER_FAILED'
    elif evaluated:
        classification = 'NO_EVIDENCE_FROM_EVALUATED_CALLERS'
    else:
        classification = 'NOT_EVALUATED'
    return {
        'schema': 'dvg-aggregate-v1',
        'classification': classification,
        'evaluations': [
            {'caller': item['caller'], 'status': item['status'],
             'event_count': item['event_count']}
            for item in summaries
        ],
    }