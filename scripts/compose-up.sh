#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -f nginx/.htpasswd ]]; then
    echo "WARNING: nginx/.htpasswd not found!"
    echo "Create one with: bash nginx/generate-htpasswd.sh"
    echo "Or run directly: docker compose up -d"
    echo ""
fi

echo "Starting VIP Gateway with Nginx..."
echo "Access at: http://localhost:8080"
echo ""

docker compose up -d
