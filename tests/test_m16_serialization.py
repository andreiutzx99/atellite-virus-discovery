import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from satellite_discovery import m16_contracts


class M16SerializationTests(unittest.TestCase):
    def test_canonical_bytes_are_sorted_stable_and_rate_precision_is_fixed(self):
        first = {
            "z": Decimal("1.25"),
            "rate": m16_contracts.FixedRate(Decimal("0.5")),
            "a": "fixture",
        }
        second = {"a": "fixture", "rate": first["rate"], "z": first["z"]}
        encoded = m16_contracts.canonical_json_bytes(first)
        self.assertEqual(encoded, m16_contracts.canonical_json_bytes(second))
        self.assertTrue(encoded.startswith(b'{"a":'))
        self.assertLess(encoded.index(b'"a"'), encoded.index(b'"rate"'))
        self.assertLess(encoded.index(b'"rate"'), encoded.index(b'"z"'))
        self.assertIn(b'"rate":0.500000', encoded)
        self.assertEqual(
            m16_contracts.semantic_sha256(first),
            m16_contracts.semantic_sha256(second),
        )

    def test_pretty_output_uses_sorted_keys_lf_and_one_trailing_newline(self):
        with tempfile.TemporaryDirectory(prefix="m16-json-") as directory:
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            m16_contracts.write_json(first, {"z": 2, "a": {"d": 4, "b": 3}})
            m16_contracts.write_json(second, {"a": {"b": 3, "d": 4}, "z": 2})
            raw = first.read_bytes()
            self.assertEqual(raw, second.read_bytes())
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            self.assertNotIn(b"\r", raw)
            self.assertTrue(raw.endswith(b"\n"))
            self.assertFalse(raw.endswith(b"\n\n"))
            self.assertLess(raw.index(b'"a"'), raw.index(b'"z"'))

    def test_input_parser_rejects_bom_crlf_duplicates_and_non_finite_values(self):
        invalid_values = (
            b"\xef\xbb\xbf{}",
            b"{\r\n\"a\":1\r\n}\r\n",
            b'{"a":1,"a":2}',
            b'{"a":NaN}',
            b'{"a":Infinity}',
            b"\xff",
        )
        for raw in invalid_values:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    m16_contracts.parse_json_bytes(raw)

        parsed = m16_contracts.parse_json_bytes(b'{"value":1.25}')
        self.assertEqual(parsed["value"], Decimal("1.25"))

    def test_binary_floats_and_non_finite_decimal_values_are_never_serialized(self):
        with self.assertRaises(ValueError):
            m16_contracts.canonical_json_bytes({"rate": 0.5})
        with self.assertRaises(ValueError):
            m16_contracts.canonical_json_bytes({"rate": Decimal("NaN")})


if __name__ == "__main__":
    unittest.main()
