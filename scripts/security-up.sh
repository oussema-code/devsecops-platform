#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
diagnose() {
  echo '--- Kyverno install did not become ready; current state:' >&2
  h -n kyverno status kyverno >&2 || true
  k -n kyverno get pods,jobs -o wide >&2 || true
  k -n kyverno get events --sort-by=.lastTimestamp 2>/dev/null | tail -25 >&2 || true
  for pod in $(k -n kyverno get pods -o name 2>/dev/null); do
    if ! k -n kyverno get "$pod" -o jsonpath='{.status.containerStatuses[*].ready}' | grep -qv false; then
      k -n kyverno describe "$pod" | tail -20 >&2 || true
      k -n kyverno logs "$pod" --all-containers --tail=30 >&2 || true
    fi
  done
  k top nodes >&2 2>/dev/null || true
}
trap diagnose ERR
helm repo add kyverno https://kyverno.github.io/kyverno --force-update
# A first install that timed out leaves a failed release (and possibly webhooks that
# block Pod creation). Remove it cleanly before retrying instead of upgrading it.
if h -n kyverno status kyverno -o json 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d["info"]["status"]=="failed" and d["version"]==1 else 1)'; then
  echo 'Removing failed first Kyverno install before retrying.'
  h -n kyverno uninstall kyverno --wait --timeout 5m
fi
h upgrade --install kyverno kyverno/kyverno --version 3.9.2 -n kyverno --create-namespace \
  -f "$PLATFORM_ROOT/platform/values/kyverno.yaml" --wait --wait-for-jobs --timeout 15m
k apply -f "$PLATFORM_ROOT/platform/security/image-signatures.yaml"
k wait clusterpolicy/boutique-release-signatures --for=condition=Ready --timeout=120s
trap - ERR
k get clusterpolicy boutique-release-signatures
