# Harmony Filtering Service

The **Harmony Filtering Service** is a microservice in the NASA Harmony ecosystem responsible for applying user-defined filters to Earth science coverages (e.g. netCDF granules).  It accepts OGC-API–Coverages /coverage/rangeset requests with filtering parameters, runs them through a configurable filter pipeline, and returns filtered coverages downstream.

---

## Table of Contents

- [Key Features](#key-features)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
- [Configuration](#configuration)
- [Running the Service](#running-the-service)
- [API Reference](#api-reference)
- [Logging & Monitoring](#logging--monitoring)
- [Testing](#testing)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [License](#license)

---

## Key Features

- **OGC-API–Coverages compliant**: Supports `/collections/{collectionId}/coverage/rangeset` POST with `variable`, `bbox`, optional filter parameters.
- **Pluggable filter pipeline**: Chain of filter “steps” can be added via configuration (e.g. quality-flag masking, threshold clipping).
- **Scale-out friendly**: Stateless container; stores no local state between requests.
- **Configurable logging**: JSON-structured logs, configurable log levels, and integration with external log aggregators.
- **Automated testing**: Unit tests, integration tests against golden-master coverages, and end-to-end smoke tests.

---

## Getting Started

### Prerequisites

- **Python 3.11+**
- **Docker & Docker Compose** (for containerized local runs)
- **Access to Harmony’s EDL credentials** (for upstream authentication)

### Installation

1. **Clone the Harmony repo**
   ```bash
   git clone https://github.com/nasa/harmony-filtering-service.git
   cd harmony-filtering-service

2. **Install Python deps**
   ```bash
   python -m venv venv
   source venv/bin/activate
   python -m pip install -e ".[dev]"
   # You may also wish to install the dependencies for the Jupyter notebook
   python -m pip install -r docs/requirements.txt

3. **Build Docker Image**
   ```bash
   ./bin/build-image
   # or if you prefer to build with the docker command directly
   docker build -t harmony-filtering-service:local -f docker/service.Dockerfile .

### Running the Service

#### Locally via Docker
   ```bash
   export EDL_USER=<your-user>
   export EDL_PASSWORD=<your-pass>
   export HARMONY_HOST_URL=https://harmony.uat.earthdata.nasa.gov
   docker run --rm \
     -p 3000:3000 \
     -e EDL_USER \
     -e EDL_PASSWORD \
     -e HARMONY_HOST_URL \
     harmony-filtering-service:local
   ```

#### Local without Docker
   ```bash
   FLASK_APP=filter_service.py \
     EDL_USER=$EDL_USER \
     EDL_PASSWORD=$EDL_PASSWORD \
     HARMONY_HOST_URL=$HARMONY_HOST_URL \
     flask run --port 3000
   ```

## Configuration

### Filter rules

Filter rules for each supported group of collections are defined in `config/config.json`, under
`<PRODUCT>.filters.pixel_filter`. Rules run in the order they are listed. A rule only runs
when its `target_var` is the variable requested from Harmony and its `level` is `"all"` or
matches the granule's processing level. For example, some TEMPO rules only run on L2 products,
so their `level` is `"2"`.

#### Comparison rules

Where `criteria_var <operator> threshold` is true, valid pixels of `target_var` are set to
`target_value` (a number, or `"nan"`).

| `operator`                 | Filters pixels where `criteria_var` is...       |
|----------------------------|-------------------------------------------------|
| `greater-than`             | `> threshold`                                   |
| `less-than`                | `< threshold`                                   |
| `greater-than-or-equal-to` | `>= threshold`                                  |
| `less-than-or-equal-to`    | `<= threshold`                                  |
| `equal-to`                 | `== threshold`                                  |
| `not-equal-to`             | `!= threshold`                                  |
| `in`                       | **not** one of the values in a `threshold` list |

A comparison rule may also include `criteria_var_AND`, `operator_AND` and `threshold_AND`, in
which case pixels are only filtered where both conditions are true.

#### Arithmetic rules

Arithmetic rules replace `target_var` with `target_var <operator> criteria_var`, pixel by pixel.
They are used to apply corrections that a product stores in a separate variable. They do not
use `threshold` or `target_value`, and cannot be combined with `criteria_var_AND`.

| `operator` | Result                       |
|------------|------------------------------|
| `add`      | `target_var + criteria_var`  |
| `subtract` | `target_var - criteria_var`  |
| `multiply` | `target_var * criteria_var`  |
| `divide`   | `target_var / criteria_var`  |

For example, the SWOT L2 LR SSH `ssh_karin` variable does not have the crossover
correction applied, it comes from the `height_cor_xover` variable:

```json
{
  "target_var": "ssh_karin",
  "criteria_var": "height_cor_xover",
  "operator": "add",
  "level": "all"
}
```

Variables are matched by dimension name; `criteria_var` must have the same dimensions as
`target_var`, or a subset of them. A pixel that is missing (NaN) in either variable is NaN in
the result, and `divide` gives NaN where `criteria_var` is zero.

Later rules for the same `target_var` see the result of an arithmetic rule, but every rule's
`criteria_var` is read as stored in the file, even if an earlier arithmetic rule changed that
same variable.

## Testing
   ```bash
    uv run pytest
   ```
