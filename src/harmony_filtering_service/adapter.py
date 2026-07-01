# src/harmony_filtering_service/adapter.py
import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import harmony_service_lib
import xarray as xr
from harmony_service_lib.util import download, stage
from pystac import Asset, Item

from harmony_filtering_service.adapter_utils import (
    load_and_prepare_settings,
)  # see below
from harmony_filtering_service.core import process_products
from harmony_filtering_service.exceptions import FilteringUtilityError
from harmony_filtering_service.identify import identify_dataset

# ensure ENV=dev if nothing else
# os.environ.setdefault("ENV", "dev")

# In adapter.py, update your flatten_product_group to also drop the unwanted vars:


def flatten_product_group(src: Path) -> Path:
    """
    Read src, pull all vars from the 'product' group up into the root,
    drop weight + the specified product‐group vars, write to a new
    '_flattened' file, and return that path.
    """
    ds0 = xr.open_dataset(src)

    # 1) merge product group if present
    try:
        with xr.open_dataset(src, group="product") as ds_prod:
            ds0.update(ds_prod)
    except OSError:
        # no 'product' group → nothing to flatten or drop in it
        pass

    # 2) drop unwanted variables if they exist
    vars_to_drop = [
        "weight",
        "vertical_column_troposphere",
        "vertical_column_troposphere_uncertainty",
        "main_data_quality_flag",
    ]
    present = [v for v in vars_to_drop if v in ds0]
    if present:
        ds0 = ds0.drop_vars(present)

    # 3) write out flattened+pruned file
    out = src.with_name(src.stem + "_flattened.nc")
    ds0.to_netcdf(out, mode="w")
    return out


def convert_time_and_stage(src: Path) -> str:
    """
    Read src with decode_times=False, apply decode_cf(use_cftime),
    write to /tmp/<basename>_cf.nc, and return the path to stage.
    """
    # 1) Open without decoding
    ds = xr.open_dataset(src, decode_times=False)
    # 2) Apply CF decoder with cftime
    ds_cf = xr.decode_cf(ds, use_cftime=True)

    # 3) Write out to a temp file under /tmp (owned by dockeruser)
    tmp = Path("/tmp") / (src.stem + "_cf.nc")
    ds_cf.to_netcdf(tmp, mode="w")

    return str(tmp)


class FilteringAdapter(harmony_service_lib.BaseHarmonyAdapter):  # type: ignore[misc]
    def process_item(self, item: Item, source: Any) -> Item:
        result = item.clone()
        result.assets = {}

        # 0) Determine variables that need processing
        var_list = source.process("variables")

        if var_list:
            var_list = list(map(lambda var: var.name, var_list))
            self.logger.info("Processing variables %s", var_list)
            myvariable = var_list[0]
            self.logger.info("First variable is %s", myvariable)
        else:
            myvariable = "all"
            self.logger.info(
                "THIS SHOULD NOT HAPPEN IN IMAGENATOR. Processing all variables."
            )

        # 1) Identify the product type etc. using the collection short name
        metadata = identify_dataset(source["shortName"], source["versionId"])
        instrument = metadata["instrument"]
        product_type = metadata["product"]
        self.logger.info(
            f"Instrument: {instrument}, Product: {product_type}"
        )

        # 2) Download into the data dir
        base = Path(__file__).parent.parent
        settings_path = base / "config" / "settings.json"
        settings = load_and_prepare_settings(settings_path)
        data_dir = Path(settings["data_dir"])
        data_dir.mkdir(parents=True, exist_ok=True)

        asset = next((v for v in item.assets.values() if "data" in (v.roles or [])), None)
        if asset is None:
            raise FilteringUtilityError("No data asset found in item")

        local_in = download(
            asset.href,
            data_dir,
            logger=self.logger,
            access_token=self.message.accessToken,
        )

        # Always recover the original filename from the asset href
        parsed = urlparse(asset.href)
        in_fname = Path(unquote(parsed.path)).name

        # Strip leading “digits_” if present
        clean_fname = re.sub(r"^\d+_", "", in_fname)
        self.logger.info("clean_fname: %s", clean_fname)

        # Rename the downloaded file in data_dir to the original/clean filename
        staged_input = data_dir / clean_fname
        shutil.move(local_in, staged_input)

        if product_type != "UNDEFINED":
            # 3) Load the config.json and retrieve the rules for the product_type
            cfg = json.loads(
                (base / "config" / "config.json").read_text(encoding="utf-8")
            )
            filtered_cfg = {product_type: cfg.get(product_type)}

            # 4) Run the filtering rules on the product
            try:
                process_products(
                    settings,
                    filtered_cfg,
                    metadata,
                    clean_fname,
                    myvariable
                )
            except FilteringUtilityError as e:
                self.logger.error(str(e))
                raise

            # 5) find the one filtered file and stage it
            out_dir = Path(settings["output_dir"])
            base_stem = staged_input.stem
            filtered = out_dir / f"{base_stem}_filtered.nc"

            if not filtered.exists():
                emsg = f"^^^^: Expected filtered output but none found at {filtered}"
                self.logger.error(emsg)
                return

            final_file = filtered
        else:
            self.logger.info(
                f"Unrecognized instrument detected ({instrument}). Skipping filtering."
            )
            final_file = staged_input

        url = stage(
            final_file,
            final_file.name,
            "application/x-netcdf",
            location=self.message.stagingLocation,
            logger=self.logger,
        )

        # add it to the STAC
        result.assets["data"] = Asset(
            href=url,
            title=final_file.name,
            media_type="application/x-netcdf",
            roles=["data"],
        )

        return result


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="filtering", description="Run the filtering service"
    )
    harmony_service_lib.setup_cli(parser)
    args = parser.parse_args()
    if harmony_service_lib.is_harmony_cli(args):
        harmony_service_lib.run_cli(parser, args, FilteringAdapter)
    else:
        parser.error("Only --harmony CLIs are supported")


if __name__ == "__main__":
    main()
