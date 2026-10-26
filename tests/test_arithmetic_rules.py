"""
Unit tests for filter rules that use arithmetic operators ("add", "subtract",
"multiply", "divide") to combine a target variable with a criteria variable.

These were added to support corrections such as the SWOT L2 LR SSH crossover
correction, where the value to visualize is ssh_karin + height_cor_xover.
"""

# pylint: disable=missing-docstring, redefined-outer-name

import os

import numpy as np
import pytest
import xarray as xr
from netCDF4 import Dataset as ncDataset

from harmony_filtering_service.core import (
    ARITHMETIC_OPERATORS,
    apply_arithmetic,
    process_products,
)
from harmony_filtering_service.exceptions import FilteringUtilityError
from harmony_filtering_service.logger import DummyLogger

DIMS = ("num_lines", "num_pixels")


@pytest.fixture
def target():
    return xr.DataArray(
        np.array([[1.0, 2.0, 3.0], [4.0, np.nan, 6.0]]),
        dims=DIMS,
        name="ssh_karin",
        attrs={"units": "m", "long_name": "sea surface height"},
    )


@pytest.fixture
def criteria():
    return xr.DataArray(
        np.array([[0.5, -1.0, 2.0], [0.0, 1.0, np.nan]]),
        dims=DIMS,
        name="height_cor_xover",
        attrs={"units": "m", "long_name": "height correction from crossover calibration"},
    )


@pytest.mark.parametrize(
    "operator, expected",
    [
        ("add", [[1.5, 1.0, 5.0], [4.0, np.nan, np.nan]]),
        ("subtract", [[0.5, 3.0, 1.0], [4.0, np.nan, np.nan]]),
        ("multiply", [[0.5, -2.0, 6.0], [0.0, np.nan, np.nan]]),
        # 4.0 / 0.0 is NaN rather than inf
        ("divide", [[2.0, -2.0, 1.5], [np.nan, np.nan, np.nan]]),
    ],
)
def test_apply_arithmetic_operators(target, criteria, operator, expected):
    result = apply_arithmetic(target, criteria, operator, 1, "height_cor_xover", DummyLogger())
    np.testing.assert_allclose(result.values, np.array(expected))
    assert result.dims == target.dims


def test_arithmetic_operators_constant():
    assert set(ARITHMETIC_OPERATORS) == {"add", "subtract", "multiply", "divide"}


def test_apply_arithmetic_does_not_modify_inputs(target, criteria):
    target_before = target.copy(deep=True)
    criteria_before = criteria.copy(deep=True)
    apply_arithmetic(target, criteria, "add", 1, "height_cor_xover", DummyLogger())
    xr.testing.assert_identical(target, target_before)
    xr.testing.assert_identical(criteria, criteria_before)


def test_apply_arithmetic_keeps_target_name_and_attrs(target, criteria):
    result = apply_arithmetic(target, criteria, "add", 1, "height_cor_xover", DummyLogger())
    assert result.name == "ssh_karin"
    assert result.attrs == target.attrs


def test_apply_arithmetic_logs_pixels_lost_to_nan(target, criteria):
    messages = []

    class RecordingLogger(DummyLogger):
        def log(self, message: str) -> None:
            messages.append(message)

    apply_arithmetic(target, criteria, "divide", 7, "height_cor_xover", RecordingLogger())
    # target is valid at [1, 0] and [1, 2], but the result is NaN there
    # (division by zero and a NaN criteria value respectively).
    assert messages == [
        "Filter rule '7': applied 'divide' with secondary variable "
        "'height_cor_xover'; previously valid pixels now NaN = 2"
    ]


def test_apply_arithmetic_matches_dimensions_by_name(target, criteria):
    transposed = criteria.transpose("num_pixels", "num_lines")
    result = apply_arithmetic(target, transposed, "add", 1, "height_cor_xover", DummyLogger())
    expected = apply_arithmetic(target, criteria, "add", 1, "height_cor_xover", DummyLogger())
    assert result.dims == DIMS
    np.testing.assert_allclose(result.values, expected.values)


def test_apply_arithmetic_broadcasts_criteria_with_fewer_dimensions(target):
    per_line = xr.DataArray(np.array([10.0, 20.0]), dims=("num_lines",))
    result = apply_arithmetic(target, per_line, "add", 1, "per_line", DummyLogger())
    np.testing.assert_allclose(result.values, [[11.0, 12.0, 13.0], [24.0, np.nan, 26.0]])


def test_apply_arithmetic_works_lazily_with_dask(target, criteria):
    result = apply_arithmetic(
        target.chunk({"num_lines": 1}),
        criteria.chunk({"num_pixels": 1}),
        "add",
        1,
        "height_cor_xover",
        DummyLogger(),
    )
    assert result.chunks is not None
    np.testing.assert_allclose(result.values, [[1.5, 1.0, 5.0], [4.0, np.nan, np.nan]])


def test_apply_arithmetic_rejects_criteria_with_extra_dimensions(target):
    other = xr.DataArray(np.ones((2, 3, 2)), dims=("num_lines", "num_pixels", "num_sides"))
    with pytest.raises(FilteringUtilityError, match="cannot 'add' secondary variable 'other'"):
        apply_arithmetic(target, other, "add", 1, "other", DummyLogger())


def test_apply_arithmetic_rejects_conflicting_dimension_sizes(target):
    other = xr.DataArray(np.ones((5, 3)), dims=DIMS)
    with pytest.raises(FilteringUtilityError, match="cannot 'subtract' secondary variable"):
        apply_arithmetic(target, other, "subtract", 1, "other", DummyLogger())


def test_apply_arithmetic_rejects_unknown_operator(target, criteria):
    with pytest.raises(FilteringUtilityError, match="Unsupported arithmetic operator 'power'"):
        apply_arithmetic(target, criteria, "power", 3, "height_cor_xover", DummyLogger())


# --------------------------------------------------------------------------
# process_products, end to end against a small SWOT-like netCDF file
# --------------------------------------------------------------------------

FILL = np.int32(2147483647)
SCALE = 0.0001
SWOT_FILENAME = "SWOT_L2_LR_SSH_Basic_040_011_20251019T000000_20251019T005000_PID0_01.nc"

SSH = np.array([[1.0, 2.0, 3.0], [4.0, np.nan, 6.0], [7.0, 8.0, 9.0], [10.0, 11.0, 12.0]])
SSHA = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, np.nan], [1.0, 1.1, 1.2]])
XOVER = np.array([[0.1, -0.2, 0.0], [0.5, 0.5, np.nan], [0.01, 0.02, 0.03], [1.0, 1.0, 1.0]])
SSH_QUAL = np.array([[0, 0, 0], [0, 0, 0], [0, 1, 0], [0, 0, 0]])


def _add_packed_variable(nc, name, values):
    """Store values the way SWOT does: int32, scale_factor 1e-4, int32 max fill."""
    var = nc.createVariable(name, "i4", DIMS, fill_value=FILL)
    var.setncattr("scale_factor", SCALE)
    var.setncattr("add_offset", 0.0)
    var.setncattr("units", "m")
    var.setncattr("coordinates", "longitude latitude")
    var.set_auto_maskandscale(False)
    var[:] = np.where(np.isnan(values), FILL, np.round(values / SCALE)).astype("i4")


@pytest.fixture
def swot_like_file(tmp_path):
    data_dir = tmp_path / "in"
    data_dir.mkdir()
    path = data_dir / SWOT_FILENAME
    with ncDataset(path, "w") as nc:
        nc.setncattr("title", "SWOT-like test granule")
        nc.createDimension("num_lines", SSH.shape[0])
        nc.createDimension("num_pixels", SSH.shape[1])
        lat = nc.createVariable("latitude", "f8", DIMS)
        lat[:] = np.linspace(-10, 10, SSH.size).reshape(SSH.shape)
        lon = nc.createVariable("longitude", "f8", DIMS)
        lon[:] = np.linspace(100, 110, SSH.size).reshape(SSH.shape)
        _add_packed_variable(nc, "ssh_karin", SSH)
        _add_packed_variable(nc, "ssha_karin", SSHA)
        _add_packed_variable(nc, "height_cor_xover", XOVER)
        qual = nc.createVariable("ssh_karin_qual", "i4", DIMS)
        qual[:] = SSH_QUAL
    return path


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


METADATA = {
    "instrument": "SWOT",
    "product": "SWOT_TEST",
    "level": "L2",
    "version": "D",
    "timestamp": "",
    "sequence": "",
}


def _config(pixel_filter, excluded=("height_cor_xover", "ssh_karin_qual")):
    return {
        "SWOT_TEST": {
            "filters": {
                "pixel_filter": pixel_filter,
                "variable_exclusion": {"excluded_variables": list(excluded)},
            }
        }
    }


# Arithmetic rules only need target_var, criteria_var, operator and level.
XOVER_RULES = [
    {
        "target_var": "ssh_karin",
        "criteria_var": "height_cor_xover",
        "operator": "add",
        "level": "all",
    },
    {
        "target_var": "ssha_karin",
        "criteria_var": "height_cor_xover",
        "operator": "add",
        "level": "all",
    },
]


def _read_output(tmp_path):
    out_path = os.path.join(str(tmp_path / "out"), SWOT_FILENAME.replace(".nc", "_filtered.nc"))
    assert os.path.exists(out_path)
    return xr.open_dataset(out_path)


@pytest.mark.parametrize(
    "variable, original, untouched, original_untouched",
    [("ssh_karin", SSH, "ssha_karin", SSHA), ("ssha_karin", SSHA, "ssh_karin", SSH)],
)
def test_process_products_applies_crossover_correction(
    tmp_path, swot_like_file, variable, original, untouched, original_untouched
):
    process_products(_settings(tmp_path), _config(XOVER_RULES), METADATA, SWOT_FILENAME, variable)

    with _read_output(tmp_path) as ds:
        # Requested variable is corrected; NaN where either input was fill.
        np.testing.assert_allclose(ds[variable].values, original + XOVER, atol=1e-9)
        # Only the requested variable has rules applied.
        np.testing.assert_allclose(ds[untouched].values, original_untouched, atol=1e-9)
        # The correction term can be excluded from the output and still be used.
        assert "height_cor_xover" not in ds
        assert "ssh_karin_qual" not in ds
        # Packing, fill value and coordinates of the source are preserved.
        assert ds[variable].encoding["dtype"] == np.dtype("int32")
        assert ds[variable].encoding["scale_factor"] == SCALE
        assert ds[variable].encoding["_FillValue"] == FILL
        assert {"latitude", "longitude"} <= set(ds[variable].coords)


def test_process_products_combines_arithmetic_and_comparison_rules(tmp_path, swot_like_file):
    rules = XOVER_RULES + [
        {
            "target_var": "ssh_karin",
            "criteria_var": "ssh_karin_qual",
            "operator": "not-equal-to",
            "threshold": "0",
            "target_value": "nan",
            "level": "all",
        }
    ]
    process_products(_settings(tmp_path), _config(rules), METADATA, SWOT_FILENAME, "ssh_karin")

    expected = SSH + XOVER
    expected[SSH_QUAL != 0] = np.nan
    with _read_output(tmp_path) as ds:
        np.testing.assert_allclose(ds["ssh_karin"].values, expected, atol=1e-9)


def test_process_products_comparison_rules_use_uncorrected_criteria(tmp_path, swot_like_file):
    # A comparison rule reads the criteria variable as stored in the file, even
    # when it is the same variable an earlier arithmetic rule corrected.
    rules = XOVER_RULES + [
        {
            "target_var": "ssh_karin",
            "criteria_var": "ssh_karin",
            "operator": "greater-than",
            "threshold": "10.5",
            "target_value": "nan",
            "level": "all",
        }
    ]
    process_products(_settings(tmp_path), _config(rules), METADATA, SWOT_FILENAME, "ssh_karin")

    expected = SSH + XOVER
    expected[np.nan_to_num(SSH) > 10.5] = np.nan
    with _read_output(tmp_path) as ds:
        np.testing.assert_allclose(ds["ssh_karin"].values, expected, atol=1e-9)


def test_process_products_skips_arithmetic_rule_for_other_level(tmp_path, swot_like_file):
    rules = [
        dict(XOVER_RULES[0], level="3"),
        # A rule that applies at every level but filters nothing, so that the
        # target variable is still loaded and written.
        {
            "target_var": "ssh_karin",
            "criteria_var": "ssh_karin_qual",
            "operator": "greater-than",
            "threshold": "5",
            "target_value": "nan",
            "level": "all",
        },
    ]
    process_products(_settings(tmp_path), _config(rules), METADATA, SWOT_FILENAME, "ssh_karin")

    with _read_output(tmp_path) as ds:
        np.testing.assert_allclose(ds["ssh_karin"].values, SSH, atol=1e-9)


def test_process_products_rejects_and_criteria_on_arithmetic_rule(tmp_path, swot_like_file):
    rules = [
        dict(
            XOVER_RULES[0],
            criteria_var_AND="ssh_karin_qual",
            operator_AND="equal-to",
            threshold_AND="0",
        )
    ]
    with pytest.raises(FilteringUtilityError, match="not supported with arithmetic operator 'add'"):
        process_products(_settings(tmp_path), _config(rules), METADATA, SWOT_FILENAME, "ssh_karin")
