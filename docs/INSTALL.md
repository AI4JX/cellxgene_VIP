# Installation

## Prerequisites

- Docker (with buildx support)
- Git

## Build the Docker Image

```bash
./scripts/build.sh
```

This runs `docker buildx build -t bxgenomics_vip:latest .` from the project root.

The build process:
1. Starts from `continuumio/miniconda3`
2. Installs Python packages and R dependencies
3. Compiles and installs cellxgene with VIP patches
4. Installs cellxgene-gateway (vendored version with custom UI)

## Verify

```bash
docker images | grep bxgenomics_vip
```

You should see `bxgenomics_vip` with tag `latest`.
