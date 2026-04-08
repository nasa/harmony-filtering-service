"""Unit tests for the copy_group function in filtering_utility.core module."""

# -*- coding: utf-8 -*-

# pylint: disable=import-error, missing-docstring, invalid-name, line-too-long, protected-access

import unittest

from harmony_filtering_service.core import parse_granule_filename


class TestParseGranuleFilename(unittest.TestCase):
    def test_parse_valid_filename(self):
        filename = "TEMPO_NO2_L3_V03_20240215T123255Z_S002.nc"
        expected = {
            "instrument": "TEMPO",
            "product": "NO2",
            "level": "3",
            "version": "V03",
            "timestamp": "20240215T123255Z",
            "sequence": "S002",
        }
        result = parse_granule_filename(filename)
        self.assertEqual(result, expected)

    def test_parse_level_without_digits_returns_empty_string(self):
        filename = "TEMPO_CO_LX_V05_20230505T123456Z_S050.nc"
        result = parse_granule_filename(filename)
        self.assertEqual(result["level"], "")

    def test_parse_filename_with_extra_extension(self):
        filename = "TEMPO_NO2_L3_V03_20240215T123255Z_S002.extra.nc"
        expected = {
            "instrument": "TEMPO",
            "product": "NO2",
            "level": "3",
            "version": "V03",
            "timestamp": "20240215T123255Z",
            "sequence": "S002",
        }
        result = parse_granule_filename(filename)
        self.assertEqual(result, expected)

    def test_parse_filename_with_missing_parts_raises_stop_iteration(self):
        filename = "TEMPO_NO2"
        # As of python3.11, the next statement in this function raises StopIteration
        # on incomplete filenames
        with self.assertRaises(StopIteration):
            parse_granule_filename(filename)


if __name__ == "__main__":
    unittest.main()
