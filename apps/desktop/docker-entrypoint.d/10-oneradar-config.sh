#!/bin/sh
set -eu

api_base_url="${ONERADAR_PUBLIC_API_URL:-}"

escaped_api_base_url=$(printf '%s' "$api_base_url" | sed 's/\\/\\\\/g; s/"/\\"/g')

cat > /usr/share/nginx/html/oneradar-config.js <<EOF
window.__ONERADAR_CONFIG__ = {
  apiBaseUrl: "$escaped_api_base_url"
};
EOF
