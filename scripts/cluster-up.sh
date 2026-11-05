#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
for tool in docker kind kubectl helm python3; do
  command -v "$tool" >/dev/null || { echo "Required tool missing: $tool" >&2; exit 1; }
done
if [[ "$(sysctl -n fs.inotify.max_user_instances)" -lt 1024 ]]; then
  echo 'Raise fs.inotify.max_user_instances to at least 1024; see docs/operations.md.' >&2
  exit 1
fi
if ! kind get clusters | grep -Fxq devsecops-platform; then
  KIND_EXPERIMENTAL_PROVIDER=docker kind create cluster \
    --config "$PLATFORM_ROOT/platform/kind.yaml" \
    --kubeconfig "$PLATFORM_KUBECONFIG"
else
  kind export kubeconfig --name devsecops-platform --kubeconfig "$PLATFORM_KUBECONFIG"
fi
chmod 600 "$PLATFORM_KUBECONFIG"
helm repo add cilium https://helm.cilium.io/ --force-update
h upgrade --install cilium cilium/cilium \
  --version "$(version cilium)" --namespace kube-system \
  --values "$PLATFORM_ROOT/platform/values/cilium.yaml" --wait --timeout 10m
k wait nodes --all --for=condition=Ready --timeout=300s
k -n kube-system rollout status deployment/coredns --timeout=180s
k -n kube-system rollout status daemonset/cilium --timeout=300s
k -n kube-system rollout status deployment/hubble-relay --timeout=300s
k -n kube-system rollout status deployment/hubble-ui --timeout=300s
k get nodes -o wide
