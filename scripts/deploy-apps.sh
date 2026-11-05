#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
for env in staging production; do
  k apply -k "$PLATFORM_ROOT/apps/online-boutique/overlays/$env"
  while IFS= read -r deployment; do
    k -n "boutique-$env" rollout status "$deployment" --timeout=600s
  done < <(k -n "boutique-$env" get deployments -o name)
done
