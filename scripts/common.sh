#!/usr/bin/env bash
set -Eeuo pipefail
PLATFORM_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM_STATE="$PLATFORM_ROOT/.platform"
PLATFORM_KUBECONFIG="$PLATFORM_STATE/kubeconfig"
PLATFORM_CONTEXT=kind-devsecops-platform
mkdir -p "$PLATFORM_STATE"
chmod 700 "$PLATFORM_STATE"
k() {
  kubectl --kubeconfig "$PLATFORM_KUBECONFIG" --context "$PLATFORM_CONTEXT" "$@"
}
h() {
  helm --kubeconfig "$PLATFORM_KUBECONFIG" --kube-context "$PLATFORM_CONTEXT" "$@"
}
version() {
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$PLATFORM_ROOT/platform/versions.json" "$1"
}
