"""Artificial fixtures for strict ViReMa output and DVG evidence contracts."""
from copy import deepcopy
from pathlib import Path
import unittest

from test_metadata import scratch_directory
from satellite_discovery import dvg_evidence as dvg


class ViremaParserTests(unittest.TestCase):
    references = {'REF': 1000, 'OTHER': 500}

    def write_files(self, root, native, stdout):
        result = root / 'Virus_Recombination_Results.txt'
        log = root / 'stdout.txt'
        result.write_text(native, encoding='utf-8')
        log.write_text(stdout, encoding='utf-8')
        return result, log

    def test_positive_and_multiple_sections_preserve_native_entries(self):
        with scratch_directory() as folder:
            root = Path(folder)
            result, log = self.write_files(
                root,
                '@NewLibrary: REF_to_OTHER\n'
                '123_to_456_#_2\t10_to_20_#_1\t\n'
                '@EndofLibrary\n'
                '@NewLibrary: OTHER_RevStrand_to_REF\n'
                '30_to_40_#_3\t\n'
                '@EndofLibrary\n',
                'Total of 20 reads have been analysed:\n'
                'of which 6 were Viral Recombinations, 0 were Host Recombinations '
                'and 0 were Virus-to-Host Recombinations\n'
                'Time to complete in seconds:  0.01\n',
            )
            events = dvg.parse_virema_results(result, self.references, log)
            self.assertEqual(len(events), 3)
            self.assertEqual(events[0]['raw_entry'], '123_to_456_#_2')
            self.assertEqual(events[0]['raw_output_line'], '123_to_456_#_2\t10_to_20_#_1\t')
            self.assertEqual(events[0]['reference_id'], 'REF')
            self.assertEqual(events[0]['orientation'], {'donor': '+', 'acceptor': '+'})
            self.assertEqual(events[0]['raw_line_number'], 2)
            self.assertEqual(events[2]['reference_id'], 'OTHER')
            self.assertEqual(events[2]['orientation'], {'donor': '-', 'acceptor': '+'})
            self.assertEqual(events[2]['raw_line_number'], 5)

    def test_single_terminal_tab_is_accepted(self):
        with scratch_directory() as folder:
            result, log = self.write_files(
                Path(folder),
                '@NewLibrary: REF_to_REF\n'
                '1_to_2_#_1\t\n'
                '@EndofLibrary\n',
                'Total of 1 reads have been analysed:\n'
                'of which 1 were Viral Recombinations, 0 were Host Recombinations '
                'and 0 were Virus-to-Host Recombinations\n'
                'Time to complete in seconds:  0.01\n',
            )
            self.assertEqual(
                dvg.parse_virema_results(result, self.references, log)[0]['raw_entry'],
                '1_to_2_#_1')

    def test_nonempty_result_requires_upstream_final_newline(self):
        with scratch_directory() as folder:
            result, log = self.write_files(
                Path(folder),
                '@NewLibrary: REF_to_REF\n'
                '1_to_2_#_1\t\n'
                '@EndofLibrary',
                'Total of 1 reads have been analysed:\n'
                'of which 1 were Viral Recombinations, 0 were Host Recombinations '
                'and 0 were Virus-to-Host Recombinations\n'
                'Time to complete in seconds:  0.01\n',
            )
            with self.assertRaises(dvg.InvalidDVGResultError):
                dvg.parse_virema_results(result, self.references, log)

    def test_colon_is_allowed_in_fasta_reference_identifiers(self):
        with scratch_directory() as folder:
            refs = {'REF:variant': 10}
            result, log = self.write_files(
                Path(folder),
                '@NewLibrary: REF:variant_to_REF:variant\n'
                '1_to_2_#_1\t\n'
                '@EndofLibrary\n',
                'Total of 1 reads have been analysed:\n'
                'of which 1 were Viral Recombinations, 0 were Host Recombinations '
                'and 0 were Virus-to-Host Recombinations\n'
                'Time to complete in seconds:  0.01\n',
            )
            self.assertEqual(
                dvg.parse_virema_results(result, refs, log)[0]['reference_id'],
                'REF:variant')

    def test_empty_file_is_zero_only_with_complete_zero_stdout(self):
        with scratch_directory() as folder:
            result, log = self.write_files(
                Path(folder), '',
                'Total of 0 reads have been analysed:\n'
                'of which 0 were Viral Recombinations, 0 were Host Recombinations '
                'and 0 were Virus-to-Host Recombinations\n'
                'Time to complete in seconds:  0.01\n',
            )
            self.assertEqual(dvg.parse_virema_results(result, self.references, log), [])

    def test_expected_read_count_checks_zero_and_positive_results(self):
        with scratch_directory() as folder:
            root = Path(folder)
            result, log = self.write_files(
                root, '',
                'Total of 0 reads have been analysed:\n'
                'of which 0 were Viral Recombinations, 0 were Host Recombinations '
                'and 0 were Virus-to-Host Recombinations\n'
                'Time to complete in seconds:  0.01\n',
            )
            with self.assertRaises(dvg.InvalidDVGResultError):
                dvg.parse_virema_results(
                    result, self.references, log, expected_read_count=1)

            result, log = self.write_files(
                root,
                '@NewLibrary: REF_to_REF\n1_to_2_#_1\t\n@EndofLibrary\n',
                'Total of 2 reads have been analysed:\n'
                'of which 1 were Viral Recombinations, 0 were Host Recombinations '
                'and 0 were Virus-to-Host Recombinations\n'
                'Time to complete in seconds:  0.01\n',
            )
            with self.assertRaises(dvg.InvalidDVGResultError):
                dvg.parse_virema_results(
                    result, self.references, log, expected_read_count=1)

    def test_completion_marker_must_be_final_unique_and_complete(self):
        counts = (
            'Total of 0 reads have been analysed:\n'
            'of which 0 were Viral Recombinations, 0 were Host Recombinations '
            'and 0 were Virus-to-Host Recombinations\n'
        )
        invalid_tails = (
            '',
            'Time to complete in seconds:',
            'Time to complete in seconds:  0.01\n'
            'Time to complete in seconds:  0.02\n',
            'Time to complete in seconds:  0.01\n'
            'Unexpected trailing output\n',
        )
        for tail in invalid_tails:
            with self.subTest(tail=tail), scratch_directory() as folder:
                result, log = self.write_files(Path(folder), '', counts + tail)
                with self.assertRaises(dvg.InvalidDVGResultError):
                    dvg.parse_virema_results(result, self.references, log)

    def test_positive_output_must_match_stdout_support_sum(self):
        with scratch_directory() as folder:
            result, log = self.write_files(
                Path(folder),
                '@NewLibrary: REF_to_REF\n1_to_2_#_2\t\n@EndofLibrary\n',
                'Total of 3 reads have been analysed:\n'
                'of which 1 were Viral Recombinations, 0 were Host Recombinations '
                'and 0 were Virus-to-Host Recombinations\n',
            )
            with self.assertRaises(dvg.InvalidDVGResultError):
                dvg.parse_virema_results(result, self.references, log)

    def test_invalid_native_and_stdout_fixtures_are_rejected(self):
        cases = (
            ('not a section\n', 'Total of 1 reads have been analysed:\n'
             'of which 0 were Viral Recombinations, 0 were Host Recombinations and '
             '0 were Virus-to-Host Recombinations\n'),
            ('@NewLibrary: REF_to_REF\n1_to_2_#_1\t\n', 'Total of 1 reads have been analysed:\n'
             'of which 1 were Viral Recombinations, 0 were Host Recombinations and '
             '0 were Virus-to-Host Recombinations\n'),
            ('@NewLibrary: REF_to_REF\n1_to_2_#_1\t\n@EndofLibrary\n'
             '@NewLibrary: REF_to_REF\n3_to_4_#_1\t\n@EndofLibrary\n',
             'Total of 2 reads have been analysed:\n'
             'of which 2 were Viral Recombinations, 0 were Host Recombinations and '
             '0 were Virus-to-Host Recombinations\n'),
            ('@NewLibrary: REF_to_REF\n1_to_2_#_1\t\n@EndofLibrary\nunexpected\n',
             'Total of 1 reads have been analysed:\n'
             'of which 1 were Viral Recombinations, 0 were Host Recombinations and '
             '0 were Virus-to-Host Recombinations\n'),
            ('@NewLibrary: MISSING_to_REF\n1_to_2_#_1\t\n@EndofLibrary\n',
             'Total of 1 reads have been analysed:\n'
             'of which 1 were Viral Recombinations, 0 were Host Recombinations and '
             '0 were Virus-to-Host Recombinations\n'),
            ('@NewLibrary: REF_to_REF\n1001_to_2_#_1\t\n@EndofLibrary\n',
             'Total of 1 reads have been analysed:\n'
             'of which 1 were Viral Recombinations, 0 were Host Recombinations and '
             '0 were Virus-to-Host Recombinations\n'),
            ('@NewLibrary: REF_to_REF\n1_to_2_#_1\t\n@EndofLibrary\n',
             'Total of 1 reads have been analysed:\n'
             'of which 1 were Viral Recombinations, 0 were Host Recombinations and '
             '0 were Virus-to-Host Recombinations\n'
             'Total of 1 reads have been analysed:\n'),
            ('@NewLibrary: REF_to_REF\nbad_token\t\n@EndofLibrary\n',
             'Total of 1 reads have been analysed:\n'
             'of which 1 were Viral Recombinations, 0 were Host Recombinations and '
             '0 were Virus-to-Host Recombinations\n'),
            ('@NewLibrary: REF_to_REF\n1_to_2_#_1\t\n@EndofLibrary\n',
             'Total of 1 reads have been analysed:\n'),
            ('@NewLibrary: REF_to_REF\n1_to_2_#_1\t1_to_2_#_1\t\n@EndofLibrary\n',
             'Total of 2 reads have been analysed:\n'
             'of which 2 were Viral Recombinations, 0 were Host Recombinations and '
             '0 were Virus-to-Host Recombinations\n'),
        )
        for native, stdout in cases:
            with self.subTest(native=native, stdout=stdout), scratch_directory() as folder:
                result, log = self.write_files(Path(folder), native, stdout)
                with self.assertRaises(dvg.InvalidDVGResultError):
                    dvg.parse_virema_results(result, self.references, log)

    def test_multiple_junctions_per_read_are_not_rejected(self):
        with scratch_directory() as folder:
            result, log = self.write_files(
                Path(folder),
                '@NewLibrary: REF_to_REF\n'
                '1_to_2_#_2\t\n'
                '@EndofLibrary\n',
                'Total of 1 reads have been analysed:\n'
                'of which 2 were Viral Recombinations, 3 were Host Recombinations '
                'and 4 were Virus-to-Host Recombinations\n'
                'Time to complete in seconds:  0.01\n',
            )
            events = dvg.parse_virema_results(result, self.references, log)
            self.assertEqual(events[0]['supporting_read_count'], 2)

    def test_nonempty_zero_event_file_and_empty_positive_result_are_not_zero(self):
        for native, count in ((' \n', 0), ('', 1)):
            with self.subTest(native=native), scratch_directory() as folder:
                result, log = self.write_files(
                    Path(folder), native,
                    f'Total of 1 reads have been analysed:\n'
                    f'of which {count} were Viral Recombinations, 0 were Host Recombinations '
                    f'and 0 were Virus-to-Host Recombinations\n',
                )
                with self.assertRaises(dvg.InvalidDVGResultError):
                    dvg.parse_virema_results(result, self.references, log)


class EvidenceValidationTests(unittest.TestCase):
    def evidence(self):
        return {
            'schema': 'dvg-evidence-v1',
            'caller': 'virema',
            'status': dvg.DVG_EVIDENCE_DETECTED,
            'reference_lengths': {'REF': 100, 'OTHER': 50},
            'events': [{
                'evidence_id': 'virema-event-1',
                'caller': 'virema',
                'reference_id': 'REF',
                'acceptor_reference_id': 'OTHER',
                'breakpoint_1': 10,
                'breakpoint_2': 20,
                'orientation': {'donor': '+', 'acceptor': '-'},
                'supporting_read_count': 2,
                'event_type': 'virus-virus_junction',
                'sequence_sha256': 'a' * 64,
            }],
        }

    def test_valid_evidence_and_summary(self):
        value = self.evidence()
        self.assertIs(dvg.validate_evidence_document(value), value)
        summary = {
            'schema': 'dvg-summary-v1', 'caller': 'virema',
            'status': dvg.DVG_EVIDENCE_DETECTED, 'event_count': 1,
        }
        self.assertIs(dvg.validate_summary(summary), summary)

    def test_evidence_reference_bounds_hash_status_and_schema_are_checked(self):
        mutations = (
            lambda item: item['events'][0].update(breakpoint_1=101),
            lambda item: item['events'][0].update(reference_id='missing'),
            lambda item: item['events'][0].update(sequence_sha256='not-a-hash'),
            lambda item: item.update(status=dvg.NO_DVG_EVIDENCE_DETECTED),
            lambda item: item.update(schema='wrong-schema'),
        )
        for mutate in mutations:
            value = self.evidence()
            mutate(value)
            with self.subTest(value=value), self.assertRaises(dvg.InvalidDVGResultError):
                dvg.validate_evidence_document(value)

    def test_summary_bounds_and_status_consistency(self):
        valid = {'schema': 'dvg-summary-v1', 'caller': 'a',
                 'status': dvg.NO_DVG_EVIDENCE_DETECTED, 'event_count': 0}
        self.assertIs(dvg.validate_summary(valid), valid)
        for key, value in (
                ('status', 'UNKNOWN'), ('event_count', -1), ('event_count', 1),
                ('schema', 'wrong')):
            malformed = deepcopy(valid)
            malformed[key] = value
            with self.subTest(malformed=malformed), self.assertRaises(dvg.InvalidDVGResultError):
                dvg.validate_summary(malformed)

    def test_aggregation_classifications_preserve_caller_statuses(self):
        def summary(caller, status, count=0, refs=None):
            item = {'schema': 'dvg-summary-v1', 'caller': caller,
                    'status': status, 'event_count': count}
            if refs is not None:
                item['event_references'] = refs
            return item

        one_event = [{'reference_id': 'R', 'acceptor_reference_id': 'R',
                      'breakpoint_1': 2, 'breakpoint_2': 4}]
        checks = (
            ([summary('a', dvg.DVG_EVIDENCE_DETECTED, 1, one_event)], 'CALLER_ONLY'),
            ([summary('a', dvg.DVG_EVIDENCE_DETECTED, 1, one_event),
              summary('b', dvg.DVG_EVIDENCE_DETECTED, 1, one_event)], 'MULTIPLE_CALLERS'),
            ([summary('a', dvg.DVG_EVIDENCE_DETECTED, 1, one_event),
              summary('b', dvg.DVG_EVIDENCE_DETECTED, 1,
                      [{'reference_id': 'X', 'acceptor_reference_id': 'X',
                        'breakpoint_1': 3, 'breakpoint_2': 5}])], 'CONFLICTING_OUTPUTS'),
            ([summary('a', dvg.NO_DVG_EVIDENCE_DETECTED)], 'NO_EVIDENCE_FROM_EVALUATED_CALLERS'),
            ([summary('a', dvg.ANALYSIS_UNAVAILABLE)], 'CALLER_UNAVAILABLE'),
            ([summary('a', dvg.ANALYSIS_FAILED)], 'CALLER_FAILED'),
        )
        for inputs, expected in checks:
            with self.subTest(expected=expected):
                result = dvg.aggregate_evaluations(inputs)
                self.assertEqual(result['classification'], expected)
                self.assertNotIn('NON_DVG', repr(result))
                self.assertEqual(len(result['evaluations']), len(inputs))


if __name__ == '__main__':
    unittest.main()