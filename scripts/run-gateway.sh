#!/usr/bin/env bash
set -e

DATA_DIR="${1:-./data}"
PORT="${2:-5005}"
DB_DIR="${3:-./gateway-data}"

mkdir -p "$DATA_DIR" "$DB_DIR"
DATA_DIR="$(cd "$DATA_DIR" && pwd)"
DB_DIR="$(cd "$DB_DIR" && pwd)"

echo "Starting cellxgene VIP Gateway..."
echo "  Data directory: $DATA_DIR"
echo "  DB directory:   $DB_DIR"
echo "  Port: $PORT"
echo ""
echo "Access at: http://localhost:$PORT"
echo ""

docker run --rm \
    -p "$PORT:5005" \
    -v "$DATA_DIR:/datasets" \
    -v "$DB_DIR:/home/BxGenomics/.gateway" \
    -e GATEWAY_PORT=5005 \
    -e GATEWAY_ENABLE_ANNOTATIONS=true \
    -e GATEWAY_ENABLE_BACKED_MODE=true \
    -e GATEWAY_EXPIRE_SECONDS=3600 \
    -e CELLXGENE_DATA=/datasets \
    -e GATEWAY_DB_PATH=/home/BxGenomics/.gateway/gateway.db \
    bxgenomics_vip:latest \
    gateway --host 0.0.0.0 --port 5005 /datasets
