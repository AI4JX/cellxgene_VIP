#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "Stopping containers..."
docker compose down -v 2>/dev/null || true

echo "Removing Docker image..."
docker rmi bxgenomics_vip:latest 2>/dev/null || true

echo "Pruning unused Docker resources..."
docker system prune -f

echo "Clean up complete."
