#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
if k -n argocd get application boutique-staging >/dev/null 2>&1; then
  echo 'Argo CD owns the application now. Commit configuration changes and sync through GitOps.' >&2
  exit 1
fi
for env in staging production; do
  k apply -k "$PLATFORM_ROOT/apps/online-boutique/overlays/$env"
  while IFS= read -r deployment; do
    k -n "boutique-$env" rollout status "$deployment" --timeout=600s
  done < <(k -n "boutique-$env" get deployments -o name)
done
