#!/usr/bin/env bash
set -euo pipefail

: "${1:?Usage: verify_azure_backend.sh <api-url> <allowed-origin>}"
: "${2:?Usage: verify_azure_backend.sh <api-url> <allowed-origin>}"

api_url="${1%/}"
allowed_origin="$2"
unknown_origin="https://unknown-origin.invalid"
response_file="$(mktemp)"
headers_file="$(mktemp)"

cleanup() {
  rm -f "$response_file" "$headers_file"
}
trap cleanup EXIT

ready_status=""
for _attempt in $(seq 1 24); do
  ready_status="$(curl --silent --show-error --output "$response_file" --dump-header "$headers_file" \
    --write-out '%{http_code}' "$api_url/health/ready" || true)"
  if [[ "$ready_status" == "200" ]]; then
    break
  fi
  sleep 5
done

if [[ "$ready_status" != "200" ]]; then
  echo "Expected $api_url/health/ready to return 200; received $ready_status." >&2
  exit 1
fi

if ! tr -d '\r' < "$headers_file" | grep -Eiq '^cache-control:[[:space:]]*no-store([[:space:]]|$)'; then
  echo "Expected /health/ready to return Cache-Control: no-store." >&2
  exit 1
fi

allowed_status="$(curl --silent --show-error --output "$response_file" --dump-header "$headers_file" \
  --write-out '%{http_code}' --request OPTIONS \
  --header "Origin: $allowed_origin" \
  --header 'Access-Control-Request-Method: GET' \
  "$api_url/health/ready")"

if [[ "$allowed_status" != "200" ]]; then
  echo "Expected allowed CORS preflight to return 200; received $allowed_status." >&2
  exit 1
fi

if ! tr -d '\r' < "$headers_file" | grep -Fiqx "access-control-allow-origin: $allowed_origin"; then
  echo "Allowed CORS preflight did not echo the exact approved origin." >&2
  exit 1
fi

unknown_status="$(curl --silent --show-error --output "$response_file" --dump-header "$headers_file" \
  --write-out '%{http_code}' --request OPTIONS \
  --header "Origin: $unknown_origin" \
  --header 'Access-Control-Request-Method: GET' \
  "$api_url/health/ready")"

if [[ "$unknown_status" == "200" ]]; then
  echo "Expected unknown CORS origin to fail; received 200." >&2
  exit 1
fi

if tr -d '\r' < "$headers_file" | grep -Eiq '^access-control-allow-origin:'; then
  echo "Unknown CORS origin received Access-Control-Allow-Origin." >&2
  exit 1
fi

echo "Azure backend health and CORS checks passed for $api_url."
