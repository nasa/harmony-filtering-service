"""File-based regressions for filtering variables with unlimited dimensions."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import numpy as np
import xarray as xr
from netCDF4 import Dataset

from harmony_filtering_service.core import copy_group, process_products


class TestUnlimitedDimensions(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make_file(self, shape, unlimited=True, group_name="", dtype="f4"):
        path = self.root / "input.nc"
        values = np.arange(np.prod(shape), dtype=dtype).reshape(shape) + 10
        with Dataset(path, "w") as dataset:
            dataset.title = "unchanged root metadata"
            group = dataset.createGroup(group_name) if group_name else dataset
            dims = tuple(f"dim_{i}" for i in range(len(shape)))
            for i, (dim, size) in enumerate(zip(dims, shape)):
                group.createDimension(dim, None if unlimited and i == 0 else size)
            science = group.createVariable(
                "science", dtype, dims, fill_value=-9999, zlib=True, complevel=3
            )
            science.units = "test units"
            science[:] = values
            quality = group.createVariable("quality", "i1", dims)
            quality[:] = np.ones(shape, dtype="i1")
        return path, dims, values

    def test_filtered_shapes_follow_source_not_empty_destination(self):
        for shape in ((1,), (1, 1), (1, 3), (2, 1), (2, 3), (1, 1, 3)):
            for group in ("", "product"):
                for dtype in ("f4", "i2"):
                    with self.subTest(shape=shape, group=group, dtype=dtype):
                        path, dims, values = self.make_file(shape, group_name=group, dtype=dtype)
                        before = path.read_bytes()
                        changed = xr.DataArray(values * 2, dims=dims)
                        key = f"{group}/science" if group else "science"
                        output = self.root / "output.nc"
                        with Dataset(path) as source, Dataset(output, "w") as target:
                            copy_group(source, target, "", {key: changed}, set())
                        with Dataset(output) as target:
                            actual_group = target[group] if group else target
                            actual = actual_group["science"]
                            self.assertEqual(actual.shape, shape)
                            np.testing.assert_array_equal(actual[:], values * 2)
                            self.assertEqual(actual.dimensions, dims)
                            self.assertTrue(actual_group.dimensions[dims[0]].isunlimited())
                            self.assertEqual(actual.units, "test units")
                            self.assertEqual(actual.getncattr("_FillValue"), -9999)
                            self.assertTrue(actual.filters()["zlib"])
                            self.assertEqual(actual.filters()["complevel"], 3)
                            self.assertEqual(target.title, "unchanged root metadata")
                            np.testing.assert_array_equal(
                                actual_group["quality"][:], np.ones(shape)
                            )
                        self.assertEqual(path.read_bytes(), before)

    def test_singleton_record_survives_without_another_variable_to_extend_it(self):
        for shape in ((1,), (1, 1), (1, 3)):
            with self.subTest(shape=shape):
                path, dims, values = self.make_file(shape)
                output = self.root / "output.nc"
                with Dataset(path) as source, Dataset(output, "w") as target:
                    copy_group(
                        source,
                        target,
                        "",
                        {"science": xr.DataArray(values * 2, dims=dims)},
                        {"quality"},
                    )
                with Dataset(output) as target:
                    self.assertEqual(target["science"].shape, shape)
                    np.testing.assert_array_equal(target["science"][:], values * 2)
                    self.assertNotIn("quality", target.variables)

    def test_fixed_dimensions_and_unfiltered_copy_are_unchanged(self):
        for unlimited, filtered in ((False, True), (False, False), (True, False)):
            with self.subTest(unlimited=unlimited, filtered=filtered):
                path, dims, values = self.make_file((1, 3), unlimited=unlimited)
                output = self.root / "output.nc"
                mapping = {"science": xr.DataArray(values, dims=dims)} if filtered else {}
                with Dataset(path) as source, Dataset(output, "w") as target:
                    copy_group(source, target, "", mapping, {"quality"})
                with Dataset(output) as target:
                    np.testing.assert_array_equal(target["science"][:], values)
                    self.assertEqual(target["science"].shape, (1, 3))
                    self.assertEqual(target.dimensions[dims[0]].isunlimited(), unlimited)
                    self.assertNotIn("quality", target.variables)

    def test_full_filtering_retains_one_observation(self):
        for shape in ((1, 1), (1, 3)):
            for group in ("", "product"):
                with self.subTest(shape=shape, group=group):
                    path, _, values = self.make_file(shape, group_name=group)
                    original = path.read_bytes()
                    output_dir = self.root / "filtered"
                    output_dir.mkdir(exist_ok=True)
                    target = f"{group}/science" if group else "science"
                    criteria = f"{group}/quality" if group else "quality"
                    settings = {
                        "data_dir": str(self.root),
                        "output_dir": str(output_dir),
                        "logging": {
                            "log_to_console": False,
                            "log_to_file": False,
                            "log_file_path": "",
                            "log_level": "INFO",
                        },
                    }
                    config = {
                        "TEST": {
                            "filters": {
                                "variable_exclusion": {"excluded_variables": []},
                                "pixel_filter": [
                                    {
                                        "target_var": target,
                                        "criteria_var": criteria,
                                        "operator": "equal-to",
                                        "threshold": 1,
                                        "target_value": "7",
                                        "level": "all",
                                    }
                                ],
                            }
                        }
                    }
                    metadata = {
                        "instrument": "TEST",
                        "product": "TEST",
                        "level": "3",
                        "version": "1",
                        "timestamp": "",
                        "sequence": "",
                    }
                    process_products(settings, config, metadata, path.name, target)
                    with Dataset(output_dir / "input_filtered.nc") as result:
                        actual = result[target]
                        self.assertEqual(actual.shape, shape)
                        np.testing.assert_array_equal(actual[:], np.full(shape, 7.0))
                        np.testing.assert_array_equal(result[criteria][:], np.ones(shape))
                    self.assertEqual(path.read_bytes(), original)
                    np.testing.assert_array_equal(
                        values, np.arange(np.prod(shape)).reshape(shape) + 10
                    )
