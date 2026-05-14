"""Unit tests for the copy_group function in harmony_filtering_service.core module."""

# -*- coding: utf-8 -*-

# pylint: disable=import-error, missing-docstring, invalid-name, line-too-long, protected-access, disable=too-many-arguments, unused-argument, too-many-positional-arguments

import os
import unittest
from unittest import mock

import numpy as np
import xarray as xr

from harmony_filtering_service.core import process_products


class TestProcessProducts(unittest.TestCase):
    """Unit tests for the process_products function in harmony_filtering_service.core module."""

    def setUp(self):
        # Common settings and config dicts setup
        self.settings = {
            "data_dir": "/fake/data_dir",
            "output_dir": "/fake/output_dir",
            "logging": {
                "log_to_console": True,
                "log_to_file": False,
                "log_file_path": "",
                "log_level": "DEBUG",
            },
        }
        self.product_type = "NO2"
        self.product_type_mur = "MUR"
        self.config = {
            self.product_type: {
                "filters": {
                    "variable_exclusion": {"excluded_variables": []},
                    "pixel_filter": [
                        {
                            "target_var": "primary/varA",
                            "criteria_var": "secondary/varB",
                            "level": "3",
                            "operator": "greater-than",
                            "threshold": 2,
                            "target_value": "nan",
                        },
                        {
                            "target_var": "primary/varC",
                            "criteria_var": "secondary/varD",
                            "level": "all",
                            "operator": "less-than",
                            "threshold": 5,
                            "target_value": "1.0",
                        },
                    ],
                }
            }
        }
        self.config_mur = {
            self.product_type_mur: {
                "filters": {
                    "variable_exclusion": {"excluded_variables": []},
                    "pixel_filter": [
                        {
                            "target_var": "varA",
                            "criteria_var": "varB",
                            "level": "all",
                            "operator": "equal-to",
                            "threshold": 2,
                            "target_value": "nan",
                        },
                        {
                            "target_var": "varA",
                            "criteria_var": "varC",
                            "level": "all",
                            "operator": "less-than-or-equal-to",
                            "threshold": 0.36,
                            "criteria_var_AND": "varA",
                            "operator_AND": "less-than",
                            "threshold_AND":  271.65,
                            "target_value": "nan",
                        },
                    ],
                }
            }
        }
        # File path and filename
        self.filename = f"TEMPO_{self.product_type}_L3_V01_20230101T000000Z_S001.nc"
        self.filename_mur = "20260302090000-JPL-L4_GHRSST-SSTfnd-MUR25-GLOB-v02.0-fv04.2.nc"
        self.file_path = os.path.join(self.settings["data_dir"], self.filename)
        self.file_path_mur = os.path.join(self.settings["data_dir"], self.filename_mur)

    @mock.patch("harmony_filtering_service.core.os.listdir")
    @mock.patch("harmony_filtering_service.core.os.path.exists", return_value=True)
    @mock.patch("harmony_filtering_service.core.get_logger")
    @mock.patch("harmony_filtering_service.core.log_msg")
    @mock.patch("harmony_filtering_service.core.parse_granule_filename")
    @mock.patch("harmony_filtering_service.core.parse_full_path")
    @mock.patch("harmony_filtering_service.core.xr.open_dataset")
    @mock.patch("harmony_filtering_service.core.ncDataset")
    @mock.patch("harmony_filtering_service.core.copy_group")
    # @mock.patch("harmony_filtering_service.core.compare_nc_files")
    def test_process_products_filters_applied(
        self,
        #mock_compare_nc_files,
        mock_copy_group,
        mock_ncDataset,
        mock_open_dataset,
        mock_parse_full_path,
        mock_parse_granule_filename,
        mock_log_msg,
        mock_get_logger,
        mock_path_exists,
        mock_listdir,
    ):
        # Setup mocks for listdir: simulate one file found
        mock_listdir.return_value = [self.file_path]

        # Setup parse_granule_filename returning metadata with level = "3"
        metadata = {
            "instrument": "TEMPO",
            "product": self.product_type,
            "level": "3",
            "version": "V03",
            "timestamp": "",
            "sequence": "",
        }
        mock_parse_granule_filename.return_value = {
            "instrument": "TEMPO",
            "product": self.product_type,
            "level": "3",
            "version": "V03",
            "timestamp": "20230101T000000Z",
            "sequence": "S001",
        }

        # Setup parse_full_path side effect for each full path used
        def parse_full_path_side_effect(full_path):
            # Return group and variable from string
            parts = full_path.split("/")
            return (parts[0], parts[1])

        mock_parse_full_path.side_effect = parse_full_path_side_effect

        # Setup xarray open_dataset mock per group
        # We use simple xarray DataArrays with some test data
        # ds_primary = mock.MagicMock()
        # ds_secondary = mock.MagicMock()
        # For primary vars
        primary_varA = xr.DataArray(np.array([10, 20, 30, 40]))
        primary_varC = xr.DataArray(np.array([5, 3, 7, 9]))
        # For secondary vars
        secondary_varB = xr.DataArray(np.array([1, 3, 4, 2]))
        secondary_varD = xr.DataArray(np.array([6, 4, 3, 8]))

        def open_dataset_side_effect(filepath, group, chunks="auto", drop_variables=[]):  # pylint: disable=unused-argument
            if group == "primary":
                ds = mock.MagicMock()
                ds.__getitem__.side_effect = lambda varname: (
                    primary_varA if varname == "varA" else primary_varC
                )
                return ds
            if group == "secondary":
                ds = mock.MagicMock()
                ds.__getitem__.side_effect = lambda varname: (
                    secondary_varB if varname == "varB" else secondary_varD
                )
                return ds
            return mock.MagicMock()

        mock_open_dataset.side_effect = open_dataset_side_effect

        # Setup ncDataset mock for src and dst netCDF files
        mock_src_nc = mock.Mock()
        mock_src_nc.ncattrs.return_value = ["attr1", "attr2"]
        mock_src_nc.getncattr.side_effect = lambda attr: "value"

        mock_dst_nc = mock.Mock()

        # Side effect for ncDataset constructor: first call is source, second is destination
        mock_ncDataset.side_effect = [mock_src_nc, mock_dst_nc]

        # Run function under test
        process_products(self.settings, self.config, metadata, self.filename, "primary/varA")

        # Check listdir was called with the correct pattern
        #mock_listdir.assert_called_once_with(
        #    os.path.join(self.settings["output_dir"])
        #)

        # Logger created once
        mock_get_logger.assert_called_once()

        # parse_granule_filename called with correct filename
        mock_parse_granule_filename.assert_called_once_with(self.filename)

        # parse_full_path called at least once
        self.assertTrue(mock_parse_full_path.called)

        # open_dataset called for groups 'primary' and 'secondary'
        open_dataset_calls = [
            mock.call(self.file_path, group="primary", chunks="auto", drop_variables=[]),
            mock.call(self.file_path, group="secondary", chunks="auto", drop_variables=[]),
        ]
        mock_open_dataset.assert_has_calls(open_dataset_calls, any_order=True)

        # copy_group called once
        self.assertTrue(mock_copy_group.called)

        # compare_nc_files called once
        #mock_compare_nc_files.assert_called_once_with(
        #    self.file_path, mock.ANY, mock.ANY
        #)

        # Log messages called multiple times - check some expected messages appear
        log_msgs = [args[0][0] for args in mock_log_msg.call_args_list]
        self.assertIn(f"Processing product '{self.product_type}'", log_msgs)
        self.assertIn(f"File: {self.file_path}", log_msgs)
        self.assertIn("Metadata extracted from filename:", log_msgs)
        self.assertIn("Before applying filters:", log_msgs)
        self.assertIn("After applying filters:", log_msgs)


    @mock.patch("harmony_filtering_service.core.os.path.exists", return_value=True)
    @mock.patch("harmony_filtering_service.core.os.listdir")
    @mock.patch("harmony_filtering_service.core.get_logger")
    @mock.patch("harmony_filtering_service.core.log_msg")
    @mock.patch("harmony_filtering_service.core.xr.open_dataset")
    @mock.patch("harmony_filtering_service.core.ncDataset")
    @mock.patch("harmony_filtering_service.core.copy_group")
    def test_process_products_compound_filter(
        self,
        mock_copy_group,
        mock_ncDataset,
        mock_open_dataset,
        mock_log_msg,
        mock_get_logger,
        mock_listdir,
        mock_path_exists,
    ):
        # Setup mocks for listdir: simulate one file found
        mock_listdir.return_value = [self.file_path_mur]

        # Metadata that would be parsed from collection shortname
        metadata = {
            "instrument": "MUR",
            "product": self.product_type_mur,
            "level": "L4",
            "version": "v04.2",
            "timestamp": "",
            "sequence": "",
        }

        # Setup xarray open_dataset mock per group
        # For primary vars
        primary_varA = xr.DataArray(np.array([271.5, 272.0, 271.0, 273.0]))
        # For criteria (filter) vars
        secondary_varB = xr.DataArray(np.array([1, 2, 1, 1]))
        secondary_varC = xr.DataArray(np.array([0.34, 0.4, 0.4, 0.35]))

        def open_dataset_side_effect(filepath, group, chunks="auto", drop_variables=[]):  # pylint: disable=unused-argument
            ds = mock.MagicMock()
            var_map = {
                "varA": primary_varA,
                "varB": secondary_varB,
                "varC": secondary_varC,
            }
            ds.__getitem__.side_effect = lambda varname: var_map[varname]
            return ds

        mock_open_dataset.side_effect = open_dataset_side_effect

        # Setup ncDataset mock for src and dst netCDF files
        mock_src_nc = mock.Mock()
        mock_src_nc.ncattrs.return_value = ["attr1", "attr2"]
        mock_src_nc.getncattr.side_effect = lambda attr: "value"

        mock_dst_nc = mock.Mock()

        # Side effect for ncDataset constructor: first call is source, second is destination
        mock_ncDataset.side_effect = [mock_src_nc, mock_dst_nc]

        # Run function under test
        process_products(self.settings, self.config_mur, metadata, self.filename_mur, "varA")

        # Logger created once
        mock_get_logger.assert_called_once()

        # open_dataset called for groups 'primary' and 'secondary'
        open_dataset_calls = [
            mock.call(self.file_path_mur, group="/", chunks="auto", drop_variables=[]),
        ]
        mock_open_dataset.assert_has_calls(open_dataset_calls, any_order=True)

        # copy_group called once
        self.assertTrue(mock_copy_group.called)

        # Log messages called multiple times - check some expected messages appear
        log_msgs = [args[0][0] for args in mock_log_msg.call_args_list]
        self.assertIn(f"Processing product '{self.product_type_mur}'", log_msgs)
        self.assertIn(f"File: {self.file_path_mur}", log_msgs)
        self.assertIn("Metadata extracted from filename:", log_msgs)
        self.assertIn("Before applying filters:", log_msgs)
        self.assertIn("After applying filters:", log_msgs)


if __name__ == "__main__":
    unittest.main()
