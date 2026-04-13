# ┌───────────────────────────────────────────────────────────────────┐
# │ docker/service.Dockerfile                                        │
# └───────────────────────────────────────────────────────────────────┘

# 1) Base image
FROM ghcr.io/osgeo/gdal:alpine-small-3.9.3

# 2) System deps & Python
RUN apk add --no-cache \
        bash build-base gcc g++ gfortran openblas-dev cmake \
        python3 python3-dev libffi-dev netcdf-dev libxml2-dev \
        libxslt-dev libjpeg-turbo-dev zlib-dev hdf5 hdf5-dev

# 3) Create & activate virtualenv
RUN python3 -m venv /service-env
ENV PATH="/service-env/bin:${PATH}"
RUN python3 -m ensurepip --upgrade

# 4) Install your runtime Python packages
RUN pip3 install --no-cache-dir \
    dask \
    harmony-service-lib \
    numpy \
    xarray \
    netCDF4 \
    matplotlib \
    jsonschema \
    earthaccess \
    gdal==3.9.3 \
    cftime

# 5) Non-root user
RUN adduser -D -s /bin/sh -h /home/dockeruser -u 1000 dockeruser
ENV HOME=/home/dockeruser

# 6) Prepare workdir
USER root
RUN mkdir -p /worker \
    && mkdir -p /worker/data/in_data /worker/data/out_data \
    && chown -R dockeruser:dockeruser /worker
USER dockeruser
WORKDIR /worker

# 7) Copy your code & config
COPY --chown=dockeruser src/harmony_filtering_service/ /worker/harmony_filtering_service/
COPY --chown=dockeruser config/                    /worker/config/

# 8) Make entrypoint available in WORKDIR (for sidecar exec)
COPY --chown=dockeruser docker/docker-entrypoint.sh /worker/docker-entrypoint.sh
RUN chmod +x /worker/docker-entrypoint.sh

# 9) Also install entrypoint into PATH
COPY --chown=dockeruser docker/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 10) Wire up entrypoint + default command
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["filter"]
