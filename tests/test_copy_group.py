"""Unit tests for the copy_group function in harmony_filtering_service.core module."""

# -*- coding: utf-8 -*-

# pylint: disable=import-error, missing-docstring, invalid-name, line-too-long, protected-access

import unittest
from unittest import mock

import numpy as np

from harmony_filtering_service.core import copy_group


class MockDimension:
    def __init__(self, length, unlimited=False):
        self._length = length
        self._unlimited = unlimited

    def __len__(self):
        return self._length

    def isunlimited(self):
        return self._unlimited


class MockVariable:
    def __init__(self, name, datatype, dimensions, data, attrs=None, filters=None):
        self.name = name
        self.datatype = datatype
        self.dimensions = dimensions
        self.shape = data.shape
        self._data = data
        self._attrs = attrs or {}
        self._filters = filters or {}

    def filters(self):
        return self._filters

    def getncattr(self, attr):
        return self._attrs[attr]

    def setncattr(self, name, value):
        self._attrs[name] = value

    def ncattrs(self):
        return list(self._attrs.keys())

    def __getitem__(self, key):
        return self._data

    def __setitem__(self, key, value):
        self._data = value


class MockGroup:
    def __init__(self, dimensions=None, variables=None, attrs=None, groups=None):
        self.dimensions = dimensions or {}
        self.variables = variables or {}
        self._attrs = attrs or {}
        self.groups = groups or {}

        self.created_dimensions = {}
        self.created_variables = {}
        self.created_groups = {}

    def createDimension(self, name, size):
        self.created_dimensions[name] = size

    def createVariable(self, name, datatype, dimensions, **kwargs):
        mv = MockVariable(name, datatype, dimensions, data=np.zeros(1))
        self.created_variables[name] = {
            "datatype": datatype,
            "dimensions": dimensions,
            "kwargs": kwargs,
            "variable": mv,
        }
        self.variables[name] = mv
        return mv

    def setncattr(self, name, value):
        self._attrs[name] = value

    def getncattr(self, name):
        return self._attrs[name]

    def ncattrs(self):
        return list(self._attrs.keys())

    def createGroup(self, name):
        new_group = MockGroup()
        self.created_groups[name] = new_group
        self.groups[name] = new_group
        return new_group


class TestCopyGroup(unittest.TestCase):
    @mock.patch("harmony_filtering_service.core.log_msg")
    def test_copy_group_basic(self, mock_log_msg):
        dim = MockDimension(10)
        dims = {"time": dim}

        filters = {"zlib": True, "complevel": 4, "shuffle": True}
        attrs = {"units": "m", "_FillValue": -9999}

        var1 = MockVariable(
            "var1",
            datatype=np.int32,
            dimensions=("time",),
            data=np.arange(10),
            attrs=attrs,
            filters=filters,
        )
        var2 = MockVariable(
            "var2", datatype=np.float64, dimensions=("time",), data=np.ones(10)
        )

        subvar = MockVariable(
            "sub_var", datatype=np.float64, dimensions=("time",), data=np.zeros(10)
        )
        subgroup = MockGroup(dimensions=dims, variables={"sub_var": subvar})

        src = MockGroup(
            dimensions=dims,
            variables={"var1": var1, "var2": var2},
            attrs={"global_attr": "value"},
            groups={"subgroup": subgroup},
        )
        dst = MockGroup()

        current_group = ""
        excluded_variables = {"var2"}
        filtered_primary = {"var1": mock.Mock(values=np.arange(10) * 2)}
        filtered_primary["var1"].isnull.return_value = [False] * 10

        copy_group(src, dst, current_group, filtered_primary, excluded_variables)

        # Dimensions copied correctly
        self.assertIn("time", dst.created_dimensions)
        self.assertEqual(dst.created_dimensions["time"], 10)

        # var2 is excluded and should not be copied, log_msg called
        mock_log_msg.assert_called_with(
            "Skipping excluded variable 'var2' in group ''.", None
        )
        self.assertNotIn("var2", dst.variables)

        # var1 copied and data replaced with filtered_primary values
        self.assertIn("var1", dst.variables)
        dst_var = dst.created_variables["var1"]["variable"]
        np.testing.assert_array_equal(dst_var._data, np.arange(10) * 2)

        # Attributes except _FillValue copied to dst var
        self.assertIn("units", dst_var._attrs)
        self.assertNotIn("_FillValue", dst_var._attrs)

        # Global attributes copied
        self.assertIn("global_attr", dst._attrs)
        self.assertEqual(dst._attrs["global_attr"], "value")

        # Subgroup created in destination and contains variable
        self.assertIn("subgroup", dst.created_groups)
        self.assertIn("sub_var", dst.created_groups["subgroup"].variables)

    def test_copy_group_no_filters(self):
        dim = MockDimension(5)
        dims = {"x": dim}

        var = MockVariable(
            "var", datatype=np.float32, dimensions=("x",), data=np.arange(5)
        )
        src = MockGroup(dimensions=dims, variables={"var": var})
        dst = MockGroup()

        copy_group(src, dst, "", {}, set())

        created_var_info = dst.created_variables.get("var")
        self.assertIsNotNone(created_var_info)
        kwargs = created_var_info["kwargs"]
        # No zlib or complevel in filters, so kwargs should not include them
        self.assertNotIn("zlib", kwargs)
        self.assertNotIn("complevel", kwargs)

    def test_copy_group_fill_value_none(self):
        dim = MockDimension(3)
        dims = {"dim": dim}
        attrs = {}
        var = MockVariable(
            "var",
            datatype=np.int32,
            dimensions=("dim",),
            data=np.arange(3),
            attrs=attrs,
            filters={"zlib": True},
        )
        src = MockGroup(dimensions=dims, variables={"var": var})
        dst = MockGroup()

        copy_group(src, dst, "", {}, set())

        created_var_info = dst.created_variables.get("var")
        self.assertIsNotNone(created_var_info)
        kwargs = created_var_info["kwargs"]
        # fill_value should be None since no _FillValue attribute
        self.assertIn("fill_value", kwargs)
        self.assertIsNone(kwargs["fill_value"])


if __name__ == "__main__":
    unittest.main()
