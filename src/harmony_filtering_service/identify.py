
import re


COLLECTION_REGEXES = [
    {
        "regex": r"(TEMPO)_O3TOT_(L\d)",
        "instrument_group": 1,
        "product_type": "O3TOT",
        "level_group": 2
    },
    {
        "regex": r"(TEMPO)_CLDO4_(L\d)",
        "instrument_group": 1,
        "product_type": "CLDO4",
        "level_group": 2
    },
    {
        "regex": r"(TEMPO)_HCHO_(L\d)",
        "instrument_group": 1,
        "product_type": "HCHO",
        "level_group": 2
    },
    {
        "regex": r"(TEMPO)_NO2_(L\d)",
        "instrument_group": 1,
        "product_type": "NO2",
        "level_group": 2
    },
    {
        "regex": r"(MUR\d?\d?)-JPL-(L4)-GLOB-([vV][0-9.]+)",
        "instrument_group": 1,
        "product_type": "MUR",
        "level_group": 2,
        "version_group": 3
    },
    {
        "regex": r"(MODIS_[A-Z]+)_(L3)_SST_MID-IR_[A-Z0-9]+_\dKM_[A-Z]+_([vV][0-9.]+)",
        "instrument_group": 1,
        "product_type": "MODIS_L3_SST_MID_IR",
        "level_group": 2,
        "version_group": 3
    },
    {
        "regex": r"(MODIS_[A-Z]+)_(L3)_SST_THERMAL_[A-Z0-9]+_\dKM_[A-Z]+_([vV][0-9.]+)",
        "instrument_group": 1,
        "product_type": "MODIS_L3_SST_THERMAL",
        "level_group": 2,
        "version_group": 3
    },
    {
        "regex": r"(GAMSSA)_28km-ABOM-(L4)-GLOB-([vV][0-9.]+)",
        "instrument_group": 1,
        "product_type": "GAMSSA",
        "level_group": 2,
        "version_group": 3
    },
    {
        "regex": r"(AVHRRF_[A-Z]+)-STAR-(L[A-Z0-9]+)-([vV][0-9.]+)",
        "instrument_group": 1,
        "product_type": "AVHRRF_STAR",
        "level_group": 2,
        "version_group": 3
    },
    {
        "regex": r"(AVHRR)_OI-NCEI-(L4)-GLOB-([vV][0-9.]+)",
        "instrument_group": 1,
        "product_type": "AVHRR_OI_NCEI",
        "level_group": 2,
        "version_group": 3
    },
]

def identify_dataset(short_name: str, version_id: str | None) -> dict[str, str]:
    """
    Given a collection's short name and an optional version ID, determine relevant
    meteadata about the collection to identify whether it should have filter rules
    applied by harmony-filtering-service.

    Parameters:
        short_name: The collection short name from the Harmony source

    """
    for case in COLLECTION_REGEXES:
        match = re.match(str(case["regex"]), short_name)
        if match:
            print(str(case["instrument_group"]))
            instrument = match.group(int(case["instrument_group"]))
            product_type = str(case["product_type"])
            level = match.group(int(case["level_group"]))
            vgroup = case.get("version_group")
            if vgroup:
                version = match.group(int(vgroup))
            else:
                version = version_id or "V01"
            return {
                "instrument": instrument,
                "product": product_type,
                "level": level,
                "version": version,
                "timestamp": "",
                "sequence": "",
            }
    return {
        "instrument": "UNDEFINED",
        "product": "UNDEFINED",
        "level": "",
        "version": "",
        "timestamp": "",
        "sequence": "",
    }
