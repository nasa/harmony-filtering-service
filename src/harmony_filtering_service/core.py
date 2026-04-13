"""
Core module for Filtering Utility.

This module contains the core processing logic, including functions for
parsing filenames, copying netCDF groups, and processing products
based on provided settings and configuration.
"""

import os
import re
from typing import Any, Dict, Set

import numpy as np
import xarray as xr
from netCDF4 import Dataset as ncDataset

from harmony_filtering_service.exceptions import FilteringUtilityError
from harmony_filtering_service.logger import get_logger, log_msg, Logger, DummyLogger


def all_primary_vars_blank(
    primary_vars: Dict[str, xr.DataArray], myvariable: str
) -> bool:
    """
    Returns True if the specified variable (myvariable) is completely NaN.
    """
    if myvariable not in primary_vars:
        raise FilteringUtilityError(
            f"Variable '{myvariable}' not found in primary variables"
        )

    arr = primary_vars[myvariable]
    return int(arr.notnull().sum()) == 0  # True if all values are NaN


def parse_granule_filename(filename: str) -> Dict[str, str]:
    """
    Parse a TEMPO granule filename and extract metadata.

    Supports both standard and NRT filenames, e.g.:
      TEMPO_NO2_L3_V02_20240215T123255Z_S002.nc
      TEMPO_NO2_L3_NRT_V02_20250724T115622Z_S003.nc

    Returns a dict with keys:
      instrument, product, level, version, timestamp, sequence
    """
    parts = filename.split("_")
    instrument = parts[0]
    product = parts[1]

    # find index of the version tag, e.g. "V02"
    version_idx = next(i for i, p in enumerate(parts) if re.match(r"V\d+", p))

    # level is always in parts[2] ("L3" or "L3" in both cases)
    level_match = re.search(r"\d+", parts[2])
    level = level_match.group(0) if level_match else ""

    version = parts[version_idx]
    timestamp = parts[version_idx + 1]
    sequence = parts[version_idx + 2].split(".")[0]

    return {
        "instrument": instrument,
        "product": product,
        "level": level,
        "version": version,
        "timestamp": timestamp,
        "sequence": sequence,
    }

def parse_mur_filename(filename: str) -> Dict[str, str]:
    """Parse a MUR/MUR25 filename and extract metadata."""
    parts = os.path.splitext(filename)[0].split("-")
    timestamp = parts[0]
    level = parts[2].split("_")[0]
    product = parts[4]
    version = parts[-1]
    return {
        "instrument": "GHRSST MUR",
        "product": product,
        "level": level,
        "version": version,
        "timestamp": timestamp,
        "sequence": "",
    }


def parse_full_path(full_path: str) -> tuple[str, str]:
    """
    Parse a full path string in the format "group/variable" and return a tuple (group, variable).

    This function is used to determine in which group a variable is located
    inside the netCDF file.

    Parameters:
        full_path: A string in the format "group/variable".

    Returns:
        A tuple (group, variable_name). If the variable is in the root group,
        "/" is returned for the group name.
    """
    parts = full_path.split("/")
    if len(parts) < 2:
        group = "/"
        var_name = parts[0]
    else:
        group = "/".join(parts[:-1])
        var_name = parts[-1]
    return group, var_name


def get_ncattr(var: Any, attr: str, dft: Any | None = None) -> Any | None:
    return var.getncattr(attr) if attr in var.ncattrs() else dft


def handle_threshold(threshold: Any) -> list[float]:
    """Normalize a filter rule threshold from config.json into a list[float]"""
    if isinstance(threshold, list):
        return [float(t) for t in threshold]
    else:
        return [float(threshold)]


def copy_group(
    src_grp: Any,
    dst_grp: Any,
    current_group: str,
    filtered_primary: Dict[str, Any],
    excluded_variables: Set[str],
    logger: Any = None,
) -> None:
    """
    Recursively copy a group from the source netCDF dataset to the destination.

    This function handles the duplication of dimensions, variables, and attributes.
    It applies special handling to variables: if a variable has a filtered version
    in 'filtered_primary', it uses that data; otherwise, it copies the original data.
    Variables whose full path (group/variable) is in the 'excluded_variables' set
    are skipped.

    Parameters:
        src_grp: The source netCDF group (from the original file).
        dst_grp: The destination netCDF group (for the filtered output).
        current_group: A string representing the current group path (empty string for root).
        filtered_primary: A dictionary mapping full variable paths to filtered arrays.
        excluded_variables: A set containing full paths of variables that should be excluded.
        logger: Optional logger instance for tracking progress and issues.
    """
    # Copy dimensions from the source group to the destination group
    for dim_name, dim in src_grp.dimensions.items():
        # For unlimited dimensions, pass None; otherwise, use the length of the dimension
        dst_grp.createDimension(dim_name, len(dim) if not dim.isunlimited() else None)

    # Iterate over all variables in the source group
    for var_name, var in src_grp.variables.items():
        # Construct the full variable path (including the group if applicable)
        full_var_path = f"{current_group}/{var_name}" if current_group else var_name

        # Skip this variable if it is in the exclusion list
        if full_var_path in excluded_variables and full_var_path not in filtered_primary:
            log_msg(
                f"Skipping excluded variable '{full_var_path}' in group '{current_group}'.",
                logger,
            )
            continue

        ## 🚫 Skip variables with more than 2 dimensions
        # if len(var.dimensions) > 2:
        #    print(
        #        f"Skipping variable '{full_var_path}' with {len(var.dimensions)} dimensions (expected ≤2D, got {var.dimensions})."
        #    )
        #    continue

        ## 🚫 Skip logic to also ignore string-type arrays
        # if var.datatype.kind in {"S", "U"}:  # string or unicode
        #    print(
        #        f"Skipping string variable '{full_var_path}' (type {var.datatype})"
        #    )
        #    continue

        filters = var.filters() or {}
        zlib_flag = filters.get("zlib", False)
        complevel = filters.get("complevel", None)
        shuffle = filters.get("shuffle", False)
        # Check if a fill value is defined for the variable
        fill_value = get_ncattr(var, "_FillValue")

        # Create the variable in the destination file with similar settings
        if zlib_flag:
            if complevel is not None:
                dst_var = dst_grp.createVariable(
                    var_name,
                    var.datatype,
                    var.dimensions,
                    zlib=True,
                    complevel=complevel,
                    shuffle=shuffle,
                    fill_value=fill_value,
                )
            else:
                dst_var = dst_grp.createVariable(
                    var_name,
                    var.datatype,
                    var.dimensions,
                    zlib=True,
                    shuffle=shuffle,
                    fill_value=fill_value,
                )
        else:
            dst_var = dst_grp.createVariable(
                var_name, var.datatype, var.dimensions, fill_value=fill_value
            )

        # Copy variable attributes (skip _FillValue as it is already applied)
        for attr in var.ncattrs():
            if attr == "_FillValue":
                continue
            dst_var.setncattr(attr, var.getncattr(attr))

        # Determine if there's filtered data for this variable; if so, use it; otherwise, copy original data.
        key = f"{current_group}/{var_name}" if current_group else var_name

        # if key in filtered_primary:
        #    dst_var[:] = filtered_primary[key].values
        # else:
        #    dst_var[:] = var[:]

        if key in filtered_primary:
            data = filtered_primary[key].values
            # np.nan will be cast to 0 when writing the data to
            # the netcdf dataset if the primary variable is an int*
            # set it to the _FillValue manually
            if "int" in str(var.datatype) and fill_value is not None:
                # the "or" is redundant but satisfies type checker
                scale = get_ncattr(var, "scale_factor", 1.0) or 1.0
                offset = get_ncattr(var, "add_offset", 0.0) or 0.0
                cast_fillval = scale * float(fill_value) + offset
                data = np.array(np.where(filtered_primary[key].isnull(), cast_fillval, data))
            if data.shape != dst_var.shape:
                data = np.squeeze(data)
            dst_var[:] = data
        else:
            dst_var[:] = var[:]

    # Copy global attributes from the source group
    for attr in src_grp.ncattrs():
        dst_grp.setncattr(attr, src_grp.getncattr(attr))

    # Recursively copy any subgroups within this group
    for subgrp_name, subgrp in src_grp.groups.items():
        new_subgrp = dst_grp.createGroup(subgrp_name)
        new_current_group = (
            f"{current_group}/{subgrp_name}" if current_group else subgrp_name
        )
        copy_group(
            subgrp,
            new_subgrp,
            new_current_group,
            filtered_primary,
            excluded_variables,
            logger,
        )


def build_filter(
        criteria_arr: xr.DataArray,
        operator: str,
        threshold: list[float],
        rule_key: int,
) -> xr.DataArray:
    if operator == "greater-than":
        return criteria_arr > threshold[0]
    elif operator == "less-than":
        return criteria_arr < threshold[0]
    elif operator == "greater-than-or-equal-to":
        return criteria_arr >= threshold[0]
    elif operator == "less-than-or-equal-to":
        return criteria_arr <= threshold[0]
    elif operator == "equal-to":
        return criteria_arr == threshold[0]
    elif operator == "not-equal-to":
        return criteria_arr != threshold[0]
    elif operator == "in":
        return ~criteria_arr.isin(
            threshold
        )  # TRUE where NOT in [0,1,2,5]
    else:
        raise FilteringUtilityError(
            f"Unsupported operator '{operator}' in rule '{rule_key}'."
        )


def apply_mask(
        target_arr: xr.DataArray,
        mask: xr.DataArray,
        target_value: float,
        rule_key: int,
        filter_name: str,
        logger: Logger | DummyLogger,
) -> xr.DataArray:
    nan_mask = target_arr.isnull()
    active_mask = mask & ~nan_mask

    filtered_count = int(active_mask.sum())
    log_msg(
        f"Filter rule '{rule_key}': secondary variable '{filter_name}' filtered pixels = {filtered_count}",
        logger,
    )

    # Clamp only VALID pixels; never overwrite original NaNs
    return target_arr.where(~active_mask, other=target_value)


def process_products(
    settings: Dict[str, Any], config: Dict[str, Any], clean_fname: str, myvariable: str
) -> None:
    """
    Main processing loop for filtering products.
    """
    data_dir = settings["data_dir"]
    output_dir = settings["output_dir"]
    log_to_console = settings["logging"]["log_to_console"]
    log_to_file = settings["logging"]["log_to_file"]
    log_file_path = settings["logging"]["log_file_path"]
    log_level = settings["logging"]["log_level"]

    print("=== Entered process_products ===")
    if log_level == "DEBUG":
        print(
            f"[DEBUG] Output directory contents before writing: {os.listdir(output_dir) if os.path.exists(output_dir) else 'Directory does not exist'}"
        )

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    excluded_variables: Set[str] = set()
    for product_type in config:
        ev = (
            config[product_type]["filters"]
            .get("variable_exclusion", {})
            .get("excluded_variables", [])
        )
        excluded_variables.update(ev)

    for product_type in config:
        file_path = os.path.join(data_dir, clean_fname)
        if not os.path.exists(file_path):
            print(f"[ERROR] File {file_path} does not exist. Skipping.")
            continue

        logger = get_logger(
            product_type, log_level, log_to_console, log_to_file, log_file_path
        )
        log_msg(f"Processing product '{product_type}'", logger)
        log_msg(f"File: {file_path}", logger)

        filename = os.path.basename(file_path)
        if not filename.startswith("TEMPO"):
            metadata = parse_mur_filename(filename)
        else:
            metadata = parse_granule_filename(filename)
        print(f"[INFO] Parsed metadata: {metadata}")
        log_msg("Metadata extracted from filename:", logger)
        log_msg(f"  Instrument: {metadata['instrument']}", logger)
        log_msg(f"  Product: {metadata['product']}", logger)
        log_msg(f"  Level: {metadata['level']}", logger)
        log_msg(f"  Version: {metadata['version']}", logger)
        log_msg(f"  Timestamp: {metadata['timestamp']}", logger)
        log_msg(f"  Sequence: {metadata['sequence']}", logger)

        granule_level = metadata["level"]
        product_filters = config[product_type]["filters"]["pixel_filter"]
        print(
            f"[INFO] Applying {len(product_filters)} filter rule(s) to product '{product_type}'..."
        )
        # primary_full_paths = {rule["target_var"] for rule in product_filters}
        # secondary_full_paths = {rule["criteria_var"] for rule in product_filters}

        # only keep the rules that should run on this granule (Fixed on 7/31/2025)
        applicable = [
            rule
            for rule in product_filters
            if rule["level"] == "all" or rule["level"] == granule_level
        ]

        primary_full_paths = {rule["target_var"] for rule in applicable if rule["target_var"] == myvariable}
        secondary_full_paths = {rule["criteria_var"] for rule in applicable if rule["target_var"] == myvariable}
        and_full_paths = {rule.get("criteria_var_AND") for rule in applicable if "criteria_var_AND" in rule}
        # this is a no-op if there are no "criteria_var_AND" rules,
        # since and_full_paths would be the empty set
        secondary_full_paths = secondary_full_paths.union(and_full_paths)
        all_paths = primary_full_paths.union(secondary_full_paths)

        # If the variable is in the root group, grp will be "/"
        groups_to_open = set()
        vars_needed_per_group: Dict[str, list] = {}
        for fp in all_paths:
            grp, var_name = parse_full_path(fp)
            groups_to_open.add(grp)
            vars_needed_per_group.setdefault(grp, []).append(var_name)

        opened_groups = {
            grp: xr.open_dataset(
                file_path, group=grp, chunks="auto",
                drop_variables=[v for v in xr.open_dataset(file_path, group=grp).data_vars
                                if v not in vars_needed_per_group[grp]]
            )
            for grp in groups_to_open
        }

        # Jackie: Refactored this line to be more readable
        primary_vars: Dict[str, Any] = {}
        for fp in primary_full_paths:
            grp, var_name = parse_full_path(fp)
            if var_name not in excluded_variables or var_name == myvariable:
                primary_vars[fp] = opened_groups[grp][var_name]

        print(f"[SSSyed] '{primary_vars}'...")

        # ✅ Only keep the Harmony-requested variable(s)
        #########requested_vars = [myvariable]  # passed in from adapter
        # primary_vars = {
        #     fp: opened_groups[parse_full_path(fp)[0]][parse_full_path(fp)[1]]
        #     for fp in primary_full_paths
        #     if fp in requested_vars and fp not in excluded_variables
        # }

        # # Load ONLY the Harmony-requested variable (myvariable)
        # primary_vars = {
        #     fp: opened_groups[parse_full_path(fp)[0]][parse_full_path(fp)[1]]
        #     for fp in primary_full_paths
        #     if fp == myvariable and fp not in excluded_variables
        # }

        secondary_vars = {
            fp: opened_groups[parse_full_path(fp)[0]][parse_full_path(fp)[1]]
            for fp in secondary_full_paths
        }

        if log_level == "DEBUG":
            log_msg("Before applying filters:", logger)
            for fp, arr in primary_vars.items():
                min_val = float(arr.min().values)
                max_val = float(arr.max().values)
                total_nan = int(arr.isnull().sum())
                _, var_name = parse_full_path(fp)
                log_msg(
                    f"  Primary variable '{var_name}': min = {min_val}, max = {max_val}, total NaNs = {total_nan}",
                    logger,
                )

        any_filter_applied = False
        for idx, rule in enumerate(product_filters, start=1):
            rule_key = idx
            primary_full_path = rule["target_var"]
            secondary_full_path = rule["criteria_var"]
            filter_level = rule["level"]
            if filter_level not in ("all", granule_level):
                log_msg(
                    f"Skipping filter rule '{rule_key}' due to level mismatch.", logger
                )
                continue
            if primary_full_path != myvariable and primary_full_path in excluded_variables:
                log_msg(
                    f"Skipping filter rule '{rule_key}' as primary variable '{primary_full_path}' is excluded.",
                    logger,
                )
                continue

            operator = rule["operator"]
            thresholds = handle_threshold(rule["threshold"])  # normalize value to list[float]
            target_value = (
                float(rule["target_value"]) if rule["target_value"] != "nan" else np.nan
            )

            if primary_full_path in primary_vars and secondary_full_path in secondary_vars:
                mask_arr = build_filter(
                    secondary_vars[secondary_full_path],
                    operator,
                    thresholds,
                    rule_key,
                )
                # Allow for combining a single additional criteria in a rule with logical &
                # This can be made more extensible with a refactoring of the config schema
                if "criteria_var_AND" in rule and "threshold_AND" in rule and "operator_AND" in rule:
                    criteria_var_and = rule["criteria_var_AND"]
                    operator_and = rule["operator_AND"]
                    threshold_and = handle_threshold(rule["threshold_AND"])
                    mask_b = build_filter(
                        secondary_vars[criteria_var_and],
                        operator_and,
                        threshold_and,
                        rule_key,
                    )
                    mask_arr = mask_b & mask_arr

                if not mask_arr.any():
                    log_msg("No pixels to filter for this rule. Skipping.", logger)
                    continue

                primary_vars[primary_full_path] = apply_mask(
                    primary_vars[primary_full_path],
                    mask_arr,
                    target_value,
                    rule_key,
                    secondary_full_path,
                    logger,
                )
                any_filter_applied = True

        if not any_filter_applied:
            log_msg("No filters applied. Copying original data.", logger)

        if log_level == "DEBUG":
            log_msg("After applying filters:", logger)
            for fp, arr in primary_vars.items():
                min_val = float(arr.min().values)
                max_val = float(arr.max().values)
                total_nan = int(arr.isnull().sum())
                _, var_name = parse_full_path(fp)
                log_msg(
                    f"  Primary variable '{var_name}': min = {min_val}, max = {max_val}, total NaNs = {total_nan}",
                    logger,
                )
            print("SRR_Primary_vars keys:", list(primary_vars.keys()))
            print("Syed_Checking key:", myvariable)

        # After logging "After applying filters:"
        if all_primary_vars_blank(primary_vars, myvariable):
            print(
                f"[WARNING_blank_file_1] Variable '{myvariable}' is completely blank after filtering in '{filename}'. Skipping file creation."
            )
            # Close opened xarray datasets before skipping
            for ds in opened_groups.values():
                ds.close()
            log_msg(
                f"Skipped file '{filename}' because '{myvariable}' was entirely NaN after filtering.",
                logger,
            )
            log_msg("=" * 60, logger)
            logger.close()
            continue  # 🚫 Do not proceed to file creation

        # Close xarray handles before copying groups
        for ds in opened_groups.values():
            ds.close()

        base_name = os.path.basename(os.path.splitext(file_path)[0])
        new_file_path = os.path.join(output_dir, base_name + "_filtered.nc")
        print(f"[WRITE] Writing filtered file to: {new_file_path}")
        src_nc = ncDataset(file_path, "r")
        dst_nc = ncDataset(new_file_path, "w")
        for attr in src_nc.ncattrs():
            dst_nc.setncattr(attr, src_nc.getncattr(attr))
        copy_group(src_nc, dst_nc, "", primary_vars, excluded_variables, logger)
        dst_nc.close()
        src_nc.close()
        print("[INFO] Done writing filtered file and closing datasets.")
        log_msg(f"Filtered file saved as: {new_file_path}", logger)

        for ds in opened_groups.values():
            ds.close()
        log_msg("=" * 60, logger)
        logger.close()
