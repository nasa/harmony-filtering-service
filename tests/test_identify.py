"""Unit tests for the identify_dataset function in harmony_filtering_service.identify module."""

import pytest

from harmony_filtering_service.identify import identify_dataset


UNDEFINED = {
    "instrument": "UNDEFINED",
    "product": "UNDEFINED",
    "level": "",
    "version": "",
    "timestamp": "",
    "sequence": "",
}


@pytest.mark.parametrize("short_name,version_id,expected", [
    # AVHRRF: '-GLOB-' removed from regex, so these now match
    (
        "AVHRRF_MB-STAR-L3U-v2.80",
        None,
        {"instrument": "AVHRRF_MB", "product": "AVHRRF_STAR", "level": "L3U", "version": "v2.80",
         "timestamp": "", "sequence": ""},
    ),
    (
        "AVHRRF_MC-STAR-L3U-v2.80",
        None,
        {"instrument": "AVHRRF_MC", "product": "AVHRRF_STAR", "level": "L3U", "version": "v2.80",
         "timestamp": "", "sequence": ""},
    ),
    # GAMSSA: matches cleanly
    (
        "GAMSSA_28km-ABOM-L4-GLOB-v01",
        None,
        {"instrument": "GAMSSA", "product": "GAMSSA", "level": "L4", "version": "v01",
         "timestamp": "", "sequence": ""},
    ),
    # MODIS MID-IR: matches instrument, level, and version from name
    (
        "MODIS_TERRA_L3_SST_MID-IR_MONTHLY_4KM_NIGHTTIME_V2019.0",
        None,
        {"instrument": "MODIS_TERRA", "product": "MODIS_L3_SST_MID_IR", "level": "L3",
         "version": "V2019.0", "timestamp": "", "sequence": ""},
    ),
    (
        "MODIS_AQUA_L3_SST_MID-IR_MONTHLY_9KM_NIGHTTIME_V2019.0",
        None,
        {"instrument": "MODIS_AQUA", "product": "MODIS_L3_SST_MID_IR", "level": "L3",
         "version": "V2019.0", "timestamp": "", "sequence": ""},
    ),
    # MODIS THERMAL: matches instrument, level, and version from name
    (
        "MODIS_TERRA_L3_SST_THERMAL_8DAY_4KM_DAYTIME_V2019.0",
        None,
        {"instrument": "MODIS_TERRA", "product": "MODIS_L3_SST_THERMAL", "level": "L3",
         "version": "V2019.0", "timestamp": "", "sequence": ""},
    ),
    (
        "MODIS_AQUA_L3_SST_THERMAL_8DAY_4KM_NIGHTTIME_V2019.0",
        None,
        {"instrument": "MODIS_AQUA", "product": "MODIS_L3_SST_THERMAL", "level": "L3",
         "version": "V2019.0", "timestamp": "", "sequence": ""},
    ),
    # MUR: 'MUR' with zero optional digits, version extracted from name
    (
        "MUR-JPL-L4-GLOB-v4.1",
        None,
        {"instrument": "MUR", "product": "MUR", "level": "L4", "version": "v4.1",
         "timestamp": "", "sequence": ""},
    ),
    # MUR25: 'MUR' with two digits, version extracted from name
    (
        "MUR25-JPL-L4-GLOB-v04.2",
        None,
        {"instrument": "MUR25", "product": "MUR", "level": "L4", "version": "v04.2",
         "timestamp": "", "sequence": ""},
    ),
    # TEMPO CLDO4: no version_group in regex, version comes from version_id argument
    (
        "TEMPO_CLDO4_L2",
        "V03",
        {"instrument": "TEMPO", "product": "CLDO4", "level": "L2", "version": "V03",
         "timestamp": "", "sequence": ""},
    ),
    # TEMPO CLDO4 NRT: re.match anchors at start so '_NRT' suffix is ignored
    (
        "TEMPO_CLDO4_L2_NRT",
        "V03",
        {"instrument": "TEMPO", "product": "CLDO4", "level": "L2", "version": "V03",
         "timestamp": "", "sequence": ""},
    ),
    (
        "TEMPO_CLDO4_L3",
        "V03",
        {"instrument": "TEMPO", "product": "CLDO4", "level": "L3", "version": "V03",
         "timestamp": "", "sequence": ""},
    ),
    (
        "TEMPO_CLDO4_L3_NRT",
        "V03",
        {"instrument": "TEMPO", "product": "CLDO4", "level": "L3", "version": "V03",
         "timestamp": "", "sequence": ""},
    ),
    # TEMPO HCHO: same pattern as CLDO4, version comes from version_id argument
    (
        "TEMPO_HCHO_L2",
        "V03",
        {"instrument": "TEMPO", "product": "HCHO", "level": "L2", "version": "V03",
         "timestamp": "", "sequence": ""},
    ),
    (
        "TEMPO_HCHO_L2_NRT",
        "V03",
        {"instrument": "TEMPO", "product": "HCHO", "level": "L2", "version": "V03",
         "timestamp": "", "sequence": ""},
    ),
])
def test_identify_dataset(short_name, version_id, expected):
    assert identify_dataset(short_name, version_id) == expected
