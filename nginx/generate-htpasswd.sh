#!/usr/bin/env bash
set -e

echo "========================================"
echo " cellxgene VIP Gateway - htpasswd Setup"
echo "========================================"
echo ""

if ! command -v htpasswd &>/dev/null; then
    echo "htpasswd not found. Installing apache2-utils..."
    if command -v apt &>/dev/null; then
        sudo apt install -y apache2-utils
    elif command -v yum &>/dev/null; then
        sudo yum install -y httpd-tools
    else
        echo "Please install apache2-utils (Debian/Ubuntu) or httpd-tools (RHEL/CentOS) manually."
        exit 1
    fi
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HTPASSWD_FILE="$SCRIPT_DIR/.htpasswd"

read -rp "Username: " USERNAME
if [[ -z "$USERNAME" ]]; then
    echo "Username cannot be empty."
    exit 1
fi

htpasswd -c "$HTPASSWD_FILE" "$USERNAME"
echo ""
echo "htpasswd file created at: $HTPASSWD_FILE"
echo "You can add more users with: htpasswd $HTPASSWD_FILE <username>"
