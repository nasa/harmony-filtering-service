# ┌───────────────────────────────────────────────────────────────────┐
# │ docker/service.Dockerfile                                        │
# └───────────────────────────────────────────────────────────────────┘

# Base image
# FROM ghcr.io/osgeo/gdal:alpine-small-3.9.3

FROM python:3.12-slim

# Passing version
ARG SERVICE_VERSION
ENV SETUPTOOLS_SCM_PRETEND_VERSION=$SERVICE_VERSION

RUN apt-get update \
     && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
    gcc \
    libnetcdf-dev \
    && pip3 install --no-cache-dir --upgrade pip cython uv \
    && apt-get purge -y --auto-remove gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN adduser --quiet --disabled-password --shell /bin/sh \
--home /home/dockeruser --gecos "" --uid 1000 dockeruser

RUN mkdir -p /worker \
    && mkdir -p /worker/data/in_data /worker/data/out_data \
    && chown -R dockeruser:dockeruser /worker

WORKDIR /worker

COPY --chown=dockeruser:dockeruser pyproject.toml README.md LICENSE ./
COPY --chown=dockeruser:dockeruser src ./
COPY --chown=dockeruser config ./config
COPY --chown=dockeruser:dockeruser uv.lock ./
COPY --chown=dockeruser:dockeruser docker/docker-entrypoint.sh ./

USER dockeruser
RUN uv sync --frozen --no-dev
ENV PATH="/worker/.venv/bin:$PATH"

RUN chmod +x ./docker-entrypoint.sh

# Wire up entrypoint + default command
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["filter"]
