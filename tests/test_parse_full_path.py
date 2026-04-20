"""Unit tests for the copy_group function in filtering_utility.core module."""

# -*- coding: utf-8 -*-

# pylint: disable=import-error, missing-docstring, invalid-name, line-too-long, protected-access

import unittest

from harmony_filtering_service.core import parse_full_path
#from harmony_filtering_service.exceptions import FilteringUtilityError


class TestParseFullPath(unittest.TestCase):
    def test_parse_valid_full_path(self):
        group, variable = parse_full_path("group1/varA")
        self.assertEqual(group, "group1")
        self.assertEqual(variable, "varA")

    def test_parse_full_path_with_multiple_slashes(self):
        group, variable = parse_full_path("group1/subgroup/varA")
        # In a previous version, this would treat the "subgroup" as the variable
        # This is undesirable behavior for cf-compliant datasets and will now
        # return the group and all subgroups as one entity
        self.assertEqual(group, "group1/subgroup")
        self.assertEqual(variable, "varA")

    def test_parse_no_slash_returns_rootgrp(self):
        # It is valid for a netCDF dataset to have data variables
        # outside of any group. xarray can handle this by opening
        # the "/" group (root group)
        group, variable = parse_full_path("varA")
        self.assertEqual(group, "/")
        self.assertEqual(variable, "varA")

    """
    Removed behavior where harmony-filtering-service raises an error when
    provided a variable with no group. The service is not user-configurable,
    so it is assumed that all variable names in the config.json are valid for
    the specified dataset.
    def test_parse_invalid_no_slash_raises(self):
        with self.assertRaises(FilteringUtilityError) as context:
            parse_full_path("invalidpath")
        self.assertIn(
            "not in the expected 'group/variable' format", str(context.exception)
        )
    """

if __name__ == "__main__":
    unittest.main()
