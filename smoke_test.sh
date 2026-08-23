#!/usr/bin/env bash
# Quick end-to-end check against a running router: submit -> poll -> download.
#
# Usage:
#   ROUTER_URL=http://localhost:8080 ROUTER_KEY=test-key-123 \
#   MODEL=bytedance/seedance-2.5 PROMPT="a cat surfing, cinematic" \
#   RESOLUTION=720p DURATION=25 ./smoke_test.sh
#
# Defaults are the flagship, Seedance 2.5 at 720p/5s.
#
# DURATION is pinned deliberately: 2.5's own default is -1, which lets the model
# pick any length up to 30s, so an unpinned run has unpredictable cost and takes
# minutes. Keep it set even when changing the value.
#
# Longer showcase clip (~8 min):
#   DURATION=25 ./smoke_test.sh
#
# Cheap fast check, e.g. after every deploy or in CI (~2 min, cents):
#   MODEL=bytedance/seedance-2.0-mini ./smoke_test.sh
#
# Duration is per-model: 2.5 accepts 4-30s, the 2.0 series 4-15s, 1.5 pro 4-12s.
# Ask for more than the model allows and BytePlus returns a precise 400.
set -euo pipefail

ROUTER_URL="${ROUTER_URL:-http://localhost:8080}"
# Remember whether the caller actually supplied a key, so a 401 can say so.
if [ -n "${ROUTER_KEY:-}" ]; then KEY_SOURCE="from your environment"; else KEY_SOURCE="the script default, you did not set ROUTER_KEY"; fi
ROUTER_KEY="${ROUTER_KEY:-test-key-123}"
MODEL="${MODEL:-bytedance/seedance-2.5}"
PROMPT="${PROMPT:-a cat surfing a big wave, cinematic, golden hour}"
RESOLUTION="${RESOLUTION:-720p}"
DURATION="${DURATION:-5}"
OUT_DIR="${OUT_DIR:-./smoke-output}"
AUTH="Authorization: Bearer ${ROUTER_KEY}"

echo "1) health"
curl -sf "${ROUTER_URL}/healthz" | jq .

echo "2) auth"
CODE=$(curl -s -o /dev/null -w '%{http_code}' "${ROUTER_URL}/api/v1/videos/models" -H "$AUTH")
if [ "$CODE" = "401" ]; then
  echo "   HTTP 401 — the router rejected the key."
  echo "   Sent: '${ROUTER_KEY}' (${KEY_SOURCE})."
  echo "   It must exactly match one of the comma-separated values of ROUTER_KEYS"
  echo "   in the server's environment (.env). Note /healthz needs no key, so a"
  echo "   healthy step 1 tells you nothing about auth."
  exit 1
fi
echo "   HTTP ${CODE} — key accepted"

echo "3) submit  (${MODEL}, ${RESOLUTION}, ${DURATION}s)"
echo "   prompt: ${PROMPT}"
RESP=$(jq -n --arg m "$MODEL" --arg p "$PROMPT" --arg r "$RESOLUTION" --argjson d "$DURATION" \
         '{model:$m, prompt:$p, resolution:$r, duration:$d}' \
       | curl -s -w '\n%{http_code}' -X POST "${ROUTER_URL}/api/v1/videos" \
              -H "$AUTH" -H "Content-Type: application/json" -d @-)
CODE=$(printf '%s' "$RESP" | tail -n1)
JOB=$(printf '%s' "$RESP" | sed '$d')
if [ "$CODE" != "202" ]; then
  echo "   submit failed (HTTP ${CODE}):"
  echo "$JOB" | jq . 2>/dev/null || echo "$JOB"
  exit 1
fi
echo "$JOB" | jq .
ID=$(echo "$JOB" | jq -r .id)

echo "4) poll until terminal"
START=$(date +%s)
while true; do
  S=$(curl -sf "${ROUTER_URL}/api/v1/videos/${ID}" -H "$AUTH")
  STATUS=$(echo "$S" | jq -r .status)
  echo "   status=${STATUS}  (t+$(( $(date +%s) - START ))s)"
  case "$STATUS" in
    completed) echo "$S" | jq 'del(.unsigned_urls, .output)'; break ;;
    failed|cancelled|expired) echo "$S" | jq .; echo "terminal failure"; exit 1 ;;
    *) sleep 5 ;;
  esac
done

echo "5) download — default path is a 302 to the presigned TOS URL"
# -L follows it. curl drops the Authorization header on a cross-host redirect,
# so our router key never reaches the CDN.
mkdir -p "$OUT_DIR"
FILE="${OUT_DIR}/$(date +%Y%m%d-%H%M%S).mp4"
curl -sfL -o "$FILE" \
  -w '   HTTP %{http_code}  %{size_download} bytes  %{content_type}  redirects=%{num_redirects}\n' \
  "${ROUTER_URL}/api/v1/videos/${ID}/content" -H "$AUTH"

echo "done -> ${FILE}"
