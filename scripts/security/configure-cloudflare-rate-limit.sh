#!/usr/bin/env bash
set -euo pipefail

api_token="${CLOUDFLARE_API_TOKEN:-${CLOUD_FLARE_TOKEN:-}}"
account_id="${CLOUDFLARE_ACCOUNT_ID:-${CLOUD_FLARE_ACCOUNT_ID:-}}"
app_hostname="${APP_HOSTNAME:-}"
zone_id="${CLOUDFLARE_ZONE_ID:-}"
rule_description="USA Stock Analysis public API burst guard"
api_base="https://api.cloudflare.com/client/v4"

if [[ -z "$api_token" ]]; then
  echo "CLOUDFLARE_API_TOKEN (or CLOUD_FLARE_TOKEN) is required." >&2
  exit 2
fi
if [[ -z "$zone_id" && -z "$account_id" ]]; then
  echo "CLOUDFLARE_ZONE_ID or CLOUDFLARE_ACCOUNT_ID is required." >&2
  exit 2
fi
if [[ -z "$zone_id" && -z "$app_hostname" ]]; then
  echo "APP_HOSTNAME is required when CLOUDFLARE_ZONE_ID is not set." >&2
  exit 2
fi

request() {
  curl --fail-with-body --silent --show-error \
    --header "Authorization: Bearer $api_token" \
    --header "Content-Type: application/json" \
    "$@"
}

if [[ -z "$zone_id" ]]; then
  zones="$(request "$api_base/zones?account.id=$account_id&per_page=50")"
  zone_id="$(jq -r --arg host "$app_hostname" '
    [.result[] | .name as $zone
      | select($host == $zone or ($host | endswith("." + $zone)))]
    | sort_by(.name | length) | last | .id // empty
  ' <<<"$zones")"
fi

if [[ -z "$zone_id" ]]; then
  echo "No Cloudflare zone matched APP_HOSTNAME." >&2
  exit 3
fi

rule_payload="$(jq -n --arg description "$rule_description" '{
  description: $description,
  expression: "starts_with(http.request.uri.path, \"/api/\") and not cf.client.bot",
  action: "block",
  ratelimit: {
    characteristics: ["cf.colo.id", "ip.src"],
    period: 10,
    requests_per_period: 30,
    mitigation_timeout: 10
  },
  enabled: true
}')"

entrypoint_url="$api_base/zones/$zone_id/rulesets/phases/http_ratelimit/entrypoint"
entrypoint="$(request "$entrypoint_url" 2>/dev/null || true)"
ruleset_id="$(jq -r '.result.id // empty' <<<"${entrypoint:-{}}")"

if [[ -z "$ruleset_id" ]]; then
  create_payload="$(jq -n --argjson rule "$rule_payload" '{
    name: "default",
    description: "Zone-level rate limiting rules",
    kind: "zone",
    phase: "http_ratelimit",
    rules: [$rule]
  }')"
  request --request POST --data "$create_payload" "$api_base/zones/$zone_id/rulesets" >/dev/null
  echo "Created Cloudflare API burst guard."
  exit 0
fi

rule_id="$(jq -r --arg description "$rule_description" '
  .result.rules[]? | select(.description == $description) | .id
' <<<"$entrypoint" | head -n 1)"

if [[ -n "$rule_id" ]]; then
  request --request PUT --data "$rule_payload" \
    "$api_base/zones/$zone_id/rulesets/$ruleset_id/rules/$rule_id" >/dev/null
  echo "Updated Cloudflare API burst guard."
else
  request --request POST --data "$rule_payload" \
    "$api_base/zones/$zone_id/rulesets/$ruleset_id/rules" >/dev/null
  echo "Created Cloudflare API burst guard."
fi
