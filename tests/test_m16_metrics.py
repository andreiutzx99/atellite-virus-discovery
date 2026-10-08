import json
import unittest
from decimal import Decimal

from satellite_discovery import m16_contracts, m16_stage


def _validate_metrics(value):
    encoded = m16_contracts.canonical_json_bytes(value)
    parsed = json.loads(encoded.decode("utf-8"), parse_float=Decimal)
    return m16_contracts.validate_metric_summary(parsed)


class M16MetricTests(unittest.TestCase):
    def test_label_and_prediction_axes_are_independent(self):
        public = {
            "items": [
                {"item_id": "a", "label_state": "SEALED_SYNTHETIC_EXPECTATION"},
                {"item_id": "b", "label_state": "UNKNOWN"},
                {"item_id": "c", "label_state": "NOT_APPLICABLE"},
                {"item_id": "d", "label_state": "SEALED_SYNTHETIC_EXPECTATION"},
            ],
        }
        key = {
            "items": [
                {"item_id": "a", "expected_software_outcome": {"result": "a"}},
                {"item_id": "d", "expected_software_outcome": "expected-d"},
            ],
        }
        predictions = [
            {
                "item_id": "a",
                "execution_state": "COMPLETED",
                "outcome_state": "EMITTED",
                "emitted_value": {"result": "a"},
            },
            {
                "item_id": "b",
                "execution_state": "COMPLETED",
                "outcome_state": "UNKNOWN",
                "emitted_value": None,
            },
            {
                "item_id": "c",
                "execution_state": "NOT_EVALUATED",
                "outcome_state": "UNKNOWN",
                "emitted_value": None,
            },
            {
                "item_id": "d",
                "execution_state": "COMPLETED",
                "outcome_state": "ABSTAINED",
                "emitted_value": None,
            },
        ]

        result = m16_stage._metrics(public, predictions, key)
        self.assertEqual(result["n_items"], 4)
        self.assertEqual(result["n_labelled"], 2)
        self.assertEqual(result["n_unknown_label"], 1)
        self.assertEqual(result["n_not_applicable_label"], 1)
        self.assertEqual(result["n_emitted"], 1)
        self.assertEqual(result["n_exact_match"], 1)
        self.assertEqual(result["coverage"].value, Decimal("0.500000"))
        self.assertEqual(result["fixture_agreement_rate"].value, Decimal("1.000000"))
        self.assertEqual(
            result["fixture_match_over_labelled"].value, Decimal("0.500000")
        )
        self.assertEqual(sum(result["prediction_counts"].values()), 4)
        self.assertEqual(
            _validate_metrics(result),
            {"record_count": 4, "n_labelled": 2},
        )

    def test_zero_labelled_and_zero_emitted_denominators_are_null(self):
        public = {
            "items": [
                {"item_id": "u", "label_state": "UNKNOWN"},
                {"item_id": "n", "label_state": "NOT_APPLICABLE"},
            ],
        }
        key = {"items": []}
        predictions = [
            {
                "item_id": "u",
                "execution_state": "COMPLETED",
                "outcome_state": "UNKNOWN",
                "emitted_value": None,
            },
            {
                "item_id": "n",
                "execution_state": "COMPLETED",
                "outcome_state": "NOT_APPLICABLE",
                "emitted_value": None,
            },
        ]
        result = m16_stage._metrics(public, predictions, key)
        self.assertEqual(result["n_labelled"], 0)
        self.assertEqual(result["n_unknown_label"], 1)
        self.assertEqual(result["n_not_applicable_label"], 1)
        self.assertIsNone(result["coverage"])
        self.assertIsNone(result["fixture_agreement_rate"])
        self.assertIsNone(result["fixture_match_over_labelled"])
        _validate_metrics(result)

    def test_every_declared_execution_state_is_counted(self):
        states = sorted(m16_contracts.EXECUTION_STATES)
        public = {
            "items": [
                {"item_id": f"item-{index}", "label_state": "UNKNOWN"}
                for index, _state in enumerate(states)
            ],
        }
        predictions = [
            {
                "item_id": f"item-{index}",
                "execution_state": state,
                "outcome_state": "UNKNOWN",
                "emitted_value": None,
            }
            for index, state in enumerate(states)
        ]
        result = m16_stage._metrics(public, predictions, {"items": []})
        self.assertEqual(sum(result["prediction_counts"].values()), len(states))
        self.assertEqual(result["prediction_counts"]["OUTCOME_UNKNOWN"], 1)
        for state in states:
            if state != "COMPLETED":
                self.assertEqual(result["prediction_counts"][state], 1)
        self.assertEqual(result["n_labelled"], 0)
        _validate_metrics(result)


if __name__ == "__main__":
    unittest.main()
