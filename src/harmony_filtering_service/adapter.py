# src/harmony_filtering_service/adapter.py
import argparse
import json
import re
import shutil
from pathlib import Path
from tempfile import mkdtemp
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

        ## 0) Determine variables that need processing
        var_list = source.process("variables")

        if var_list:
            var_list = list(map(lambda var: var.name, var_list))
            self.logger.info("Processing variables %s", var_list)
            myvariable = var_list[0]
            self.logger.info("First variable is %s", myvariable)
        else:
            self.logger.info(
                "THIS SHOULD NOT HAPPEN IN IMAGENATOR. Processing all variables."
            )

        # 1) download into a throw-away dir
        workdir = mkdtemp()
        try:
            asset = next(v for v in item.assets.values() if "data" in (v.roles or []))

            parsed = urlparse(asset.href)
            in_fname = Path(unquote(parsed.path)).name
            # strip leading “digits_” if present
            clean_fname = re.sub(r"^\d+_", "", in_fname)
            # self.logger.info("Syedd: Extracted clean filename: %s", clean_fname)

            # 2) load and prepare settings.json (creates data_dir & output_dir)
            base = Path(__file__).parent.parent

            # 4) load your filtering config.json
            cfg = json.loads(
                (base / "config" / "config.json").read_text(encoding="utf-8")
            )

            # 5) run your core filtering logic
            # process_products(settings, cfg)

            self.logger.info("clean_fname: %s", clean_fname)

            ## Extract just the product name (e.g., NO2) from the filename
            # product_match = re.match(r"TEMPO_([A-Z0-9]+)_L", clean_fname)

            # if not product_match:
            #    self.logger.error(
            #        "Could not find product type from filename: %s", clean_fname
            #    )
            #    return

            # product_type = product_match.group(1)
            # self.logger.info("Detected product type: %s", product_type)

            # Extract instrument + product right here
            match = re.match(r"([A-Z0-9]+)_([A-Z0-9]+)_L", clean_fname)
            if not match:
                # Attempt to determine if the product matches the MUR naming convention
                # if the product is not TEMPO
                cleaner_fname = re.sub(r"^\d+-", "", clean_fname)
                # cleaner_fname examples: JPL-L4_GHRSST-SSTfnd-MUR-GLOB-v02.0-fv04.1 or
                # JPL-L4_GHRSST-SSTfnd-MUR25-GLOB-v02.0-fv04.2
                match_mur = re.match(r"JPL-L4_GHRSST-SSTfnd-([A-Z0-9]+)-GLOB", cleaner_fname)
                if not match_mur:
                    self.logger.error(
                        "Could not parse instrument/product from filename: %s", clean_fname
                    )

                    instrument = "UNDEFINED"
                    product_type = "UNDEFINED"
                else:
                    instrument = match_mur.group(1)
                    # MUR and MUR25 use the same filter rules in the config.json
                    product_type = "MUR"
                # return
            else:
                instrument = match.group(1)
                product_type = match.group(2)
                self.logger.info(
                    "Instrument: %s, Product: %s", instrument, product_type
                )

            local_in = download(
                asset.href,
                workdir,
                logger=self.logger,
                access_token=self.message.accessToken,
            )

            # ─── Case 1: TEMPO instrument → normal filtering ───
            if instrument in ["TEMPO", "MUR", "MUR25"]:
                if product_type not in cfg:
                    self.logger.error(
                        "Product type '%s' NOT found in config", product_type
                    )
                    return

                settings_path = base / "config" / "settings.json"
                settings = load_and_prepare_settings(settings_path)

                # 3) move the downloaded file into data_dir
                data_dir = Path(settings["data_dir"])
                data_dir.mkdir(parents=True, exist_ok=True)

                staged_input = data_dir / clean_fname
                shutil.copy(local_in, staged_input)

                if not staged_input.exists():
                    self.logger.error(
                        "^^^: Expected staged_input output but none found at %s",
                        staged_input,
                    )
                    return

                # self.logger.info("******* in_fname: %s", in_fname)
                # self.logger.info("******* staged_input: %s", staged_input)

                filtered_cfg = {product_type: cfg[product_type]}
                # process_products(settings, filtered_cfg, clean_fname)
                try:
                    # process_products(settings, filtered_cfg, clean_fname)
                    process_products(settings, filtered_cfg, clean_fname, myvariable)
                except FilteringUtilityError as e:
                    self.logger.error(str(e))
                    raise

                # 6) find the one filtered file and stage it
                out_dir = Path(settings["output_dir"])
                base_stem = staged_input.stem
                filtered = out_dir / f"{base_stem}_filtered.nc"

                if not filtered.exists():
                    self.logger.error(
                        "^^^^: Expected filtered output but none found at %s", filtered
                    )
                    return

                final_file = filtered

                # ===== SAVE A LOCAL COPY OF THE FILTERED NETCDF =====
                # local_out_dir = Path("/worker/local_debug_output")
                # local_out_dir.mkdir(parents=True, exist_ok=True)

                # local_copy_path = local_out_dir / final_file.name
                # shutil.copy(final_file, local_copy_path)

                # self.logger.info(f"Local copy of filtered file saved to: {local_copy_path}")

            # ─── Case 2: Other instrument → just stage original ───
            else:
                self.logger.info(
                    "Unrecognized instrument detected (%s). Skipping filtering.",
                    instrument,
                )
                final_file = Path(local_in)

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

        finally:
            shutil.rmtree(workdir)


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
