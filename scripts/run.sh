#!/usr/bin/env bash
set -e

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <dataset.h5ad> [port]"
    echo ""
    echo "Launch a single dataset with cellxgene VIP."
    exit 1
fi

DATASET="$1"
PORT="${2:-5005}"
DATASET_DIR="$(cd "$(dirname "$DATASET")" && pwd)"
DATASET_NAME="$(basename "$DATASET")"

echo "Starting cellxgene VIP with: $DATASET_NAME on port $PORT"
docker run --rm \
    -p "$PORT:$PORT" \
    -v "$DATASET_DIR:/data" \
    bxgenomics_vip:latest \
    "/data/$DATASET_NAME" \
    --host 0.0.0.0 \
    -p "$PORT"
