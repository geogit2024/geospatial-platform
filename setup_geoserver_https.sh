#!/usr/bin/env bash
set -euo pipefail

DOMAIN="136-112-52-116.sslip.io"
BASE_DIR="/opt/geoserver-proxy"

sudo mkdir -p "$BASE_DIR/caddy_data" "$BASE_DIR/caddy_config"

sudo tee "$BASE_DIR/Caddyfile" >/dev/null <<EOF
$DOMAIN {
    encode gzip
    reverse_proxy 127.0.0.1:8080
}
EOF

sudo docker rm -f geoserver-https-proxy >/dev/null 2>&1 || true
sudo docker run -d \
  --name geoserver-https-proxy \
  --restart unless-stopped \
  --network host \
  -v "$BASE_DIR/Caddyfile:/etc/caddy/Caddyfile:ro" \
  -v "$BASE_DIR/caddy_data:/data" \
  -v "$BASE_DIR/caddy_config:/config" \
  caddy:2 >/dev/null

echo "Caddy started for $DOMAIN"
