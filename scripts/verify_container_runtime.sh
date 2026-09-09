#!/usr/bin/env bash
set -euo pipefail
image="${1:?Provide the candidate image reference.}"
root="$(cd "$(dirname "$0")/.." && pwd)"
fixture_dir="$(mktemp -d)"
trap 'rm -rf "$fixture_dir"' EXIT
# Official MediaPipe test asset, fetched before the offline container starts.
curl --fail --location --retry 3 https://storage.googleapis.com/mediapipe-assets/pose.jpg -o "$fixture_dir/pose.jpg"
echo 'c8a830ed683c0276d713dd5aeda28f415f10cd6291972084a40d0d8b934ed62b  '"$fixture_dir/pose.jpg" | shasum -a 256 -c -
if ! docker image inspect "$image" >/dev/null 2>&1; then
  docker pull "$image" >/dev/null
fi
configured_user="$(docker image inspect --format '{{.Config.User}}' "$image")"
if [ "$configured_user" != "10001:10001" ]; then
  echo "Candidate image must configure USER 10001:10001; found ${configured_user:-<empty>}." >&2
  exit 1
fi
docker run --rm --platform linux/amd64 --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:rw,nosuid,nodev,size=256m --tmpfs /home/peso:rw,nosuid,nodev,size=32m,uid=10001,gid=10001 \
  -e BACKEND_ENV=development -e SUPABASE_URL=https://example.supabase.co \
  -e SUPABASE_SERVICE_ROLE_KEY=offline-test-service-role \
  -e SUPABASE_JWT_SECRET=offline-test-jwt-secret -e CLEANUP_JOB_TOKEN=offline-test-cleanup \
  -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 \
  -v "$root/scripts/container_runtime_check.py:/checks/runtime.py:ro" \
  -v "$fixture_dir/pose.jpg:/checks/pose.jpg:ro" \
  -v "$root/backend/tests/fixtures/media/portrait-vp9.webm:/checks/upload.webm:ro" \
  "$image" python /checks/runtime.py
