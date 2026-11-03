"""
Tests for the SWOT_L2_LR_SSH filter rules shipped in config/config.json.

These run process_products with the real configuration against a small file
laid out like a SWOT L2 LR SSH Basic or Expert granule: variables in the root
group on (num_lines, num_pixels), heights packed as int32 with a scale factor,
and bit-flag quality variables.
"""

# pylint: disable=missing-docstring, redefined-outer-name

import json
import os

import numpy as np
import pytest
import xarray as xr
from netCDF4 import Dataset as ncDataset

from harmony_filtering_service.core import process_products
from harmony_filtering_service.identify import identify_dataset

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "config.json")
PRODUCT = "SWOT_L2_LR_SSH"
FILENAME = "SWOT_L2_LR_SSH_Basic_040_011_20251019T000000_20251019T005000_PID0_01.nc"
DIMS = ("num_lines", "num_pixels")

HEIGHT_FILL = np.int32(2147483647)
HEIGHT_SCALE = 0.0001
XOVER_QUAL_FILL = np.uint8(255)

SSH = np.array([[1.0, 2.0, 3.0], [4.0, np.nan, 6.0], [7.0, 8.0, 9.0], [10.0, 11.0, 12.0]])
SSHA = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, np.nan], [1.0, 1.1, 1.2]])
XOVER = np.array([[0.1, -0.2, 0.0], [0.5, 0.5, np.nan], [0.01, 0.02, 0.03], [1.0, 1.0, 1.0]])
# Bit flags: any set bit means the pixel should not be used. 2147483648 is the
# highest bit (bad_not_usable), to check that large flag values are handled.
SSH_QUAL = np.array([[0, 0, 0], [0, 0, 0], [0, 4, 0], [0, 0, 2147483648]], dtype="u4")
SSHA_QUAL = np.array([[0, 0, 0], [0, 0, 0], [0, 0, 0], [1, 0, 0]], dtype="u4")
# 0 = good, 1 = suspect, 2 = bad; NaN marks a fill value
XOVER_QUAL = np.array([[0, 1, 0], [0, 0, 0], [0, 0, 2], [0, 0, 0]], dtype="f8")
XOVER_QUAL[0, 2] = np.nan
SWH = np.arange(12, dtype="f8").reshape(SSH.shape)


def _add_packed_height(nc, name, values):
    var = nc.createVariable(name, "i4", DIMS, fill_value=HEIGHT_FILL)
    var.setncattr("scale_factor", HEIGHT_SCALE)
    var.setncattr("add_offset", 0.0)
    var.setncattr("units", "m")
    var.setncattr("coordinates", "longitude latitude")
    var.set_auto_maskandscale(False)
    var[:] = np.where(np.isnan(values), HEIGHT_FILL, np.round(values / HEIGHT_SCALE)).astype("i4")


@pytest.fixture
def swot_granule(tmp_path):
    data_dir = tmp_path / "in"
    data_dir.mkdir()
    with ncDataset(data_dir / FILENAME, "w") as nc:
        nc.createDimension("num_lines", SSH.shape[0])
        nc.createDimension("num_pixels", SSH.shape[1])
        lat = nc.createVariable("latitude", "f8", DIMS)
        lat[:] = np.linspace(-10, 10, SSH.size).reshape(SSH.shape)
        lon = nc.createVariable("longitude", "f8", DIMS)
        lon[:] = np.linspace(100, 110, SSH.size).reshape(SSH.shape)
        _add_packed_height(nc, "ssh_karin", SSH)
        _add_packed_height(nc, "ssha_karin", SSHA)
        _add_packed_height(nc, "height_cor_xover", XOVER)
        for name, flags in (("ssh_karin_qual", SSH_QUAL), ("ssha_karin_qual", SSHA_QUAL)):
            qual = nc.createVariable(name, "u4", DIMS)
            qual[:] = flags
        xover_qual = nc.createVariable(
            "height_cor_xover_qual", "u1", DIMS, fill_value=XOVER_QUAL_FILL
        )
        xover_qual.set_auto_maskandscale(False)
        xover_qual[:] = np.where(np.isnan(XOVER_QUAL), XOVER_QUAL_FILL, XOVER_QUAL).astype("u1")
        swh = nc.createVariable("swh_karin", "f8", DIMS)
        swh[:] = SWH
    return data_dir / FILENAME


@pytest.fixture
def swot_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    # The adapter only passes the identified product's rules to process_products
    return {PRODUCT: config[PRODUCT]}


def _settings(tmp_path):
    return {
        "data_dir": str(tmp_path / "in"),
        "output_dir": str(tmp_path / "out"),
        "logging": {
            "log_to_console": False,
            "log_to_file": False,
            "log_file_path": "",
            "log_level": "RUN",
        },
    }


def _run(tmp_path, config, variable):
    metadata = identify_dataset("SWOT_L2_LR_SSH_Basic_D", None)
    process_products(_settings(tmp_path), config, metadata, FILENAME, variable)
    out_path = tmp_path / "out" / FILENAME.replace(".nc", "_filtered.nc")
    assert out_path.exists()
    return xr.open_dataset(out_path)


def test_swot_collections_map_to_configured_product():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    for short_name in ("SWOT_L2_LR_SSH_BASIC_D", "SWOT_L2_LR_SSH_Expert_2.0"):
        assert identify_dataset(short_name, None)["product"] == PRODUCT
    assert PRODUCT in config


@pytest.mark.parametrize(
    "variable, values, own_qual, other_variable",
    [
        ("ssh_karin", SSH, SSH_QUAL, "ssha_karin"),
        ("ssha_karin", SSHA, SSHA_QUAL, "ssh_karin"),
    ],
)
def test_swot_rules(
    tmp_path, swot_granule, swot_config, variable, values, own_qual, other_variable
):
    expected = values + XOVER
    expected[(own_qual != 0) | (XOVER_QUAL != 0)] = np.nan  # NaN quality (fill) != 0 too

    with _run(tmp_path, swot_config, variable) as ds:
        # Valid only where both quality flags are 0, with the crossover
        # correction added; NaN where either height is a fill value.
        np.testing.assert_allclose(ds[variable].values, expected, atol=1e-9)
        # Output keeps the source packing and fill value.
        assert ds[variable].encoding["dtype"] == np.dtype("int32")
        assert ds[variable].encoding["scale_factor"] == HEIGHT_SCALE
        assert ds[variable].encoding["_FillValue"] == HEIGHT_FILL
        assert {"latitude", "longitude"} <= set(ds[variable].coords)
        # The correction and quality variables are excluded from the output, so
        # the correction cannot be applied a second time downstream, as is the
        # target variable that was not requested.
        for excluded in (
            other_variable,
            "height_cor_xover",
            "height_cor_xover_qual",
            "ssh_karin_qual",
            "ssha_karin_qual",
        ):
            assert excluded not in ds
        # Variables without rules are copied unchanged.
        np.testing.assert_array_equal(ds["swh_karin"].values, SWH)
