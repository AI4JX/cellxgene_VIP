#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "Building cellxgene VIP Docker image..."
docker buildx build -t bxgenomics_vip:latest .
echo ""
echo "Done. Image tagged: bxgenomics_vip:latest"
