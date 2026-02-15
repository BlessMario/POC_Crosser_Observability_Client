#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="$(cd "$(dirname "$0")/../certs/dev" && pwd)"
mkdir -p "$OUT_DIR"

# CA
openssl req -x509 -newkey rsa:4096 -days 3650 -nodes \
  -keyout "$OUT_DIR/ca.key" -out "$OUT_DIR/ca.crt" \
  -subj "/CN=DEV-MQTT-CA"

# Client key + CSR
openssl req -newkey rsa:2048 -nodes \
  -keyout "$OUT_DIR/client.key" -out "$OUT_DIR/client.csr" \
  -subj "/CN=dev-client"

# Sign client cert
openssl x509 -req -in "$OUT_DIR/client.csr" -CA "$OUT_DIR/ca.crt" -CAkey "$OUT_DIR/ca.key" -CAcreateserial \
  -out "$OUT_DIR/client.crt" -days 825

echo "Generated DEV CA + client certs in $OUT_DIR"
