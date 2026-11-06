#!/usr/bin/env bash
# One-time, zero-downtime hand-over of frontend Pods from the Deployment to Argo Rollouts.
# Run after `make rollouts-up` and BEFORE pushing the canary change to main: it creates
# the Rollout beside the running Deployment and waits for it, so the later Argo CD sync
# that scales the Deployment to zero never leaves the storefront without Pods.
set -Eeuo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
for env in staging production; do
  ns="boutique-$env"
  if k -n "$ns" get rollout frontend >/dev/null 2>&1; then
    echo "$ns: Rollout already present"; continue
  fi
  k kustomize "$PLATFORM_ROOT/apps/online-boutique/overlays/$env" | python3 -c '
import sys, yaml
keep = {("NetworkPolicy", "canary-check"), ("NetworkPolicy", "frontend-canary-check"),
        ("ConfigMap", "storefront-check"), ("Service", "frontend-canary"),
        ("AnalysisTemplate", "storefront-checkout"), ("Rollout", "frontend")}
docs = [d for d in yaml.safe_load_all(sys.stdin) if (d["kind"], d["metadata"]["name"]) in keep]
assert len(docs) == len(keep), "Overlay does not contain the canary resources"
yaml.safe_dump_all(docs, sys.stdout, sort_keys=False)' > "$PLATFORM_STATE/frontend-rollout-$env.yaml"
  # Same field manager Argo CD uses, so its later server-side sync adopts these fields.
  k apply --server-side --field-manager=argocd-controller -f "$PLATFORM_STATE/frontend-rollout-$env.yaml"
  k -n "$ns" wait rollout/frontend --for=jsonpath='{.status.phase}'=Healthy --timeout=300s
  echo "$ns: Rollout Healthy beside the existing Deployment"
done
