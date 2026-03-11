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

- **Python 3.9+** (if Python-based)
- **Docker & Docker Compose** (for containerized local runs)
- **Access to Harmony’s EDL credentials** (for upstream authentication)

### Installation

1. **Clone the Harmony repo**
   ```bash
   git clone https://github.com/nasa/harmony.git
   cd harmony/filtering-service

2. **Install Python deps**
   ```bash
   pip install -r requirements.txt

3. **Build Docker Image**
   ```bash
   docker build -t harmony-filtering-service:local .

### Running the Service

#### Locally via Docker
    export EDL_USER=<your-user>
    export EDL_PASSWORD=<your-pass>
    export HARMONY_HOST_URL=https://harmony.uat.earthdata.nasa.gov
    docker run --rm \
      -p 3000:3000 \
      -e EDL_USER \
      -e EDL_PASSWORD \
      -e HARMONY_HOST_URL \
      harmony-filtering-service:local

#### Local without Docker
  FLASK_APP=filter_service.py \
    EDL_USER=$EDL_USER \
    EDL_PASSWORD=$EDL_PASSWORD \
    HARMONY_HOST_URL=$HARMONY_HOST_URL \
    flask run --port 3000

## Testing
   ```bash
    uv run pytest
   ```
