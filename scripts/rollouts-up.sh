#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
helm repo add argo https://argoproj.github.io/argo-helm --force-update
h upgrade --install argo-rollouts argo/argo-rollouts --version "$(version argo-rollouts)" \
  --namespace argo-rollouts --create-namespace \
  --values "$PLATFORM_ROOT/platform/values/argo-rollouts.yaml" --wait --timeout 10m
k wait crd/rollouts.argoproj.io crd/analysistemplates.argoproj.io crd/analysisruns.argoproj.io \
  --for=condition=Established --timeout=120s
# Argo CD must be allowed to manage the new kinds before the overlays reference them.
k apply -f "$PLATFORM_ROOT/platform/gitops/project.yaml"
k -n argo-rollouts rollout status deployment/argo-rollouts --timeout=300s
