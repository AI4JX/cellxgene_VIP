FROM continuumio/miniconda3:v25.11.1

USER root
RUN apt-get update && apt-get install -y cpio tzdata bash && rm -rf /var/lib/apt/lists/*
ENV TZ=America/Los_Angeles
RUN cp /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
RUN groupadd -g 1999 share && useradd -r -u 1999 -g share -m share
# RUN addgroup -g 1999 share && adduser -S -G share -u 1999 share

# copy source customized files for VIP
ARG condaPath=/opt/conda
RUN mkdir /home/BxGenomics;chown share:share /home/BxGenomics
WORKDIR /home/BxGenomics
COPY env_yml/VIPlight_versioned.yml vipdocker/build/install_VIPlight_indocker.sh .
COPY vipdocker/build/respatch/* .
COPY gsea/ .

# install packages
RUN ./install_VIPlight_indocker.sh

# runtime R scripts & UI (moved after install to avoid cache invalidation)
COPY vipdocker/build/plottings/* .

# install cellxgene-gateway (before switching to share user)
COPY vip-gateway/ vip-gateway/
RUN /opt/conda/envs/vip/bin/pip install ./vip-gateway && rm -rf vip-gateway

# pre-create tmp dirs and gateway db dir for share user
RUN mkdir -p /home/BxGenomics/scRNAview/tmp/.numba_cache \
             /home/BxGenomics/scRNAview/tmp/.matplotlib \
             /home/BxGenomics/scRNAview/tmp/.fontconfig \
             /home/BxGenomics/.gateway \
 && chown -R share:share /home/BxGenomics/scRNAview /home/BxGenomics/.gateway

USER share
VOLUME /home/BxGenomics/scRNAview
ENV PATH="/opt/conda/envs/vip/bin:${PATH}"
ENV NUMBA_CACHE_DIR=/home/BxGenomics/scRNAview/tmp/.numba_cache
ENV MPLCONFIGDIR=/home/BxGenomics/scRNAview/tmp/.matplotlib
ENV XDG_CACHE_HOME=/home/BxGenomics/scRNAview/tmp/.fontconfig

# prepare entrypoint
COPY vipdocker/build/vip-entrypoint /usr/local/bin/vip-entrypoint

# directly execute cellxgene
ENTRYPOINT ["vip-entrypoint"]
CMD []
