## v0.3.2 - 2026-07-01
- Preserved the original input filename for unrecognized/undefined collections when filtering is skipped.

## v0.3.1 - 2026-06-08
- Reverted a regression introduced in v0.3.0 where jobs that produce no output would throw an error.

## v0.3.0 - 2026-05-13
- Added support for PODAAC's GAMSSA, AVHRRF STAR, AVHRR OI NCEI, and MODIS L3 SST datasets
- Refactored code for determining dataset-level metadata to use collection short name

## v0.2.0 - 2026-04-14
- Added support for PODAAC GHRSST MUR and MUR25 collections
- Added support for filter rules with "and" logical operators
- Various fixes and updates for unit tests

## v0.1.1 - 2026-03-09

## v0.1.0 — 2025-04-28
- Initial release
- Added Harmony‐service repo scaffold:
  - `docker/` with service & test Dockerfiles
  - `bin/` with `build-image` script
  - `harmony_filtering_service/adapter.py` and others
  - Stub `tests/` and GitHub Actions workflow
- Included README, CONTRIBUTING, and LICENSE placeholders
