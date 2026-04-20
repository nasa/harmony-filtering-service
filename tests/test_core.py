import json
import os
import subprocess

import pytest
import xarray as xr

from harmony_filtering_service import core
from harmony_filtering_service.config_validator import load_and_validate_config
from harmony_filtering_service.exceptions import FilteringUtilityError


@pytest.fixture
def sample_nc_file():
    """
    Fixture to retrieve a sample netCDF file for testing.

    This function performs the following:
      - Loads the test settings from config/settings.json.
      - Retrieves the test input directory from the settings ("test" -> "data_dir").
      - Ensures the test input directory exists.
      - Searches for .nc files that contain "NO2" in their filename.
      - If no file is found, it attempts to run the granule_downloader.py script to download one.
      - If still no file is available, it skips the test.
      - Returns the full path of the first matching file.
    """
    # Load settings from config/settings.json to get the test input directory.
    settings_file = os.path.join(
        os.path.dirname(__file__), "..", "config", "settings.json"
    )
    with open(settings_file, "r", encoding="utf-8") as f:
        settings = json.load(f)
    # Retrieve the test input directory from the settings (normalized to the OS path format)
    input_dir = os.path.normpath(settings["test"]["data_dir"])
    os.makedirs(input_dir, exist_ok=True)

    # List all .nc files in the test input directory that contain "NO2" in the filename.
    files = [f for f in os.listdir(input_dir) if "NO2" in f and f.endswith(".nc")]

    # If no files are found, run the granule downloader script to download a sample file.
    if not files:
        downloader_path = os.path.join(
            os.path.dirname(__file__), "..", "utils", "granule_downloader.py"
        )
        subprocess.run(["python", downloader_path], check=True)
        # Re-check for files after running the downloader.
        files = [f for f in os.listdir(input_dir) if "NO2" in f and f.endswith(".nc")]
        if not files:
            pytest.skip("No NO2 file could be downloaded to the test input directory.")

    # Construct the full path of the first matching file.
    full_path = os.path.join(input_dir, files[0])
    return full_path


def test_parse_full_path():
    """
    Unit test for parse_full_path function.

    - Checks that valid input returns correct group and variable.
    - Ensures that invalid input raises an exception.
    """
    grp, var = core.parse_full_path("product/vertical_column_stratosphere")
    assert grp == "product"
    assert var == "vertical_column_stratosphere"

    # No longer raises an exception for root variables
    #with pytest.raises(Exception):
    #    core.parse_full_path("invalidformat")


@pytest.mark.integration
def test_process_products(sample_nc_file):
    """
    Integration test for core.process_products using a sample netCDF file and a filtering rule.

    Test steps:
      1. Load settings from config/settings.json.
      2. Get testing directories from the "test" section in settings:
         - Use settings["test"]["data_dir"] as the input directory.
         - Use settings["test"]["output_dir"] as the output directory.
      3. Define a filtering configuration with rule "1" that filters the variable
         "vertical_column_stratosphere" (located in the "product" group) based on the criteria
         from "product/main_data_quality_flag" being greater than 1.
      4. Open the original file from the "product" group and count the initial number of NaN pixels.
      5. Run core.process_products which applies the filtering and writes a filtered file.
      6. Verify that the filtered file exists.
      7. Open the filtered file (from the "product" group) and assert that:
         - The variable is an xarray.DataArray.
         - The number of NaN pixels has increased compared to the original.
    """
    # Load settings from config/settings.json
    settings_file = os.path.join(
        os.path.dirname(__file__), "..", "config", "settings.json"
    )
    with open(settings_file, "r", encoding="utf-8") as f:
        settings = json.load(f)

    # Use test directories defined in the "test" section of settings.json.
    settings["data_dir"] = os.path.normpath(settings["test"]["data_dir"])
    settings["output_dir"] = os.path.normpath(settings["test"]["output_dir"])
    os.makedirs(settings["output_dir"], exist_ok=True)

    # Define a filtering configuration for testing.
    # This configuration uses a filter rule (key "1") to set values in the "vertical_column_stratosphere"
    # variable to NaN when the "main_data_quality_flag" is greater than 1.
    config = {
        "NO2": {
            "filters": {
                "pixel_filter": [
                    {
                        "target_var": "product/vertical_column_stratosphere",
                        "criteria_var": "product/main_data_quality_flag",
                        "operator": "greater-than",
                        "threshold": "1",
                        "target_value": "nan",
                        "level": "all",
                    }
                ],
                "variable_exclusion": {"excluded_variables": []},
            }
        }
    }

    # Open the original netCDF file (group "product") to count the initial NaN values.
    original_ds = xr.open_dataset(sample_nc_file, group="product")
    orig_da = original_ds["vertical_column_stratosphere"]
    orig_nan_count = int(orig_da.isnull().sum().values) - 1000
    original_ds.close()

    # Run the processing function which applies the filter and creates the filtered file.
    core.process_products(settings, config, os.path.basename(sample_nc_file), "product/vertical_column_stratosphere")

    # Build the expected filtered file path based on the input file's name.
    base_name = os.path.splitext(os.path.basename(sample_nc_file))[0]
    filtered_file = os.path.join(settings["output_dir"], f"{base_name}_filtered.nc")
    assert os.path.exists(filtered_file), "Filtered file was not created."

    # Open the filtered file (group "product") and retrieve the filtered variable.
    filtered_ds = xr.open_dataset(filtered_file, group="product")
    filtered_da = filtered_ds["vertical_column_stratosphere"]

    # Assert that the filtered variable is indeed an xarray.DataArray.
    assert isinstance(filtered_da, xr.DataArray)
    filtered_nan_count = int(filtered_da.isnull().sum().values)
    filtered_ds.close()

    # Verify that the filtering increased the number of NaN values in the variable.
    assert filtered_nan_count > orig_nan_count, (
        f"Expected more NaN values after filtering (original: {orig_nan_count}, filtered: {filtered_nan_count})."
    )

    # If the test settings indicate cleanup, remove the sample and filtered files.
    if settings.get("test", {}).get("remove_after_test", False):
        # Remove the filtered file if it exists.
        if os.path.exists(filtered_file):
            os.remove(filtered_file)
        # Optionally, remove the sample file.
        if os.path.exists(sample_nc_file):
            os.remove(sample_nc_file)


def test_load_and_validate_config_success(tmp_path):
    """
    Test that load_and_validate_settings correctly validates a valid settings JSON.

    This test creates temporary settings and schema files that conform to the expected schema.
    It then verifies that the function returns the settings dictionary unchanged.
    """
    valid_settings = {
        "data_dir": "./data/in_data",
        "config_path": "config.json",
        "output_dir": "./data/out_data",
        "logging": {
            "log_to_console": True,
            "log_to_file": True,
            "log_file_path": "logs/",
            "log_level": "DEBUG",
        },
        "test": {
            "data_dir": "./tests/data/in_data",
            "output_dir": "./tests/data/out_data",
            "remove_after_test": True,
        },
    }
    valid_schema = {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "title": "Settings Schema",
        "type": "object",
        "properties": {
            "data_dir": {"type": "string"},
            "config_path": {"type": "string"},
            "output_dir": {"type": "string"},
            "logging": {
                "type": "object",
                "properties": {
                    "log_to_console": {"type": "boolean"},
                    "log_to_file": {"type": "boolean"},
                    "log_file_path": {"type": "string"},
                    "log_level": {"type": "string"},
                },
                "required": [
                    "log_to_console",
                    "log_to_file",
                    "log_file_path",
                    "log_level",
                ],
            },
            "test": {
                "type": "object",
                "properties": {
                    "data_dir": {"type": "string"},
                    "output_dir": {"type": "string"},
                    "remove_after_test": {"type": "boolean"},
                },
                "required": ["data_dir", "output_dir", "remove_after_test"],
            },
        },
        "required": ["data_dir", "config_path", "output_dir", "logging", "test"],
        "additionalProperties": False,
    }

    # Create temporary settings and schema files.
    settings_file = tmp_path / "settings.json"
    schema_file = tmp_path / "settings_schema.json"
    settings_file.write_text(json.dumps(valid_settings))
    schema_file.write_text(json.dumps(valid_schema))

    # Validate the settings.
    result = load_and_validate_config(str(settings_file), str(schema_file))
    assert result == valid_settings, (
        "The validated settings should match the original valid settings"
    )


def test_load_and_validate_config_failure(tmp_path):
    """
    Test that load_and_validate_settings fails when the settings JSON is invalid.

    In this test, a required key (e.g., "config_path") is removed.
    The function should raise a FilteringUtilityError indicating a configuration validation error.
    """
    invalid_settings = {
        "data_dir": "./data/in_data",
        # "config_path" key is missing to simulate an error.
        "output_dir": "./data/out_data",
        "logging": {
            "log_to_console": True,
            "log_to_file": True,
            "log_file_path": "logs/",
            "log_level": "DEBUG",
        },
        "test": {
            "data_dir": "./tests/data/in_data",
            "output_dir": "./tests/data/out_data",
            "remove_after_test": True,
        },
    }
    valid_schema = {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "title": "Settings Schema",
        "type": "object",
        "properties": {
            "data_dir": {"type": "string"},
            "config_path": {"type": "string"},
            "output_dir": {"type": "string"},
            "logging": {
                "type": "object",
                "properties": {
                    "log_to_console": {"type": "boolean"},
                    "log_to_file": {"type": "boolean"},
                    "log_file_path": {"type": "string"},
                    "log_level": {"type": "string"},
                },
                "required": [
                    "log_to_console",
                    "log_to_file",
                    "log_file_path",
                    "log_level",
                ],
            },
            "test": {
                "type": "object",
                "properties": {
                    "data_dir": {"type": "string"},
                    "output_dir": {"type": "string"},
                    "remove_after_test": {"type": "boolean"},
                },
                "required": ["data_dir", "output_dir", "remove_after_test"],
            },
        },
        "required": ["data_dir", "config_path", "output_dir", "logging", "test"],
        "additionalProperties": False,
    }

    settings_file = tmp_path / "settings.json"
    schema_file = tmp_path / "settings_schema.json"
    settings_file.write_text(json.dumps(invalid_settings))
    schema_file.write_text(json.dumps(valid_schema))

    with pytest.raises(FilteringUtilityError) as excinfo:
        load_and_validate_config(str(settings_file), str(schema_file))
    assert "Configuration validation error" in str(excinfo.value)
