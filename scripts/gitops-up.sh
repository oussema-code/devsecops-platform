#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
REPOSITORY=oussema-code/devsecops-platform
helm repo add argo https://argoproj.github.io/argo-helm --force-update
h upgrade --install argocd argo/argo-cd --version "$(version argocd)" \
  --namespace argocd --create-namespace --values "$PLATFORM_ROOT/platform/values/argocd.yaml" \
  --wait --timeout 10m
if ! k -n argocd get secret platform-repository >/dev/null 2>&1; then
  if [[ ! -f "$PLATFORM_STATE/argocd-repo" ]]; then
    ssh-keygen -q -t ed25519 -N '' -C devsecops-platform-argocd \
      -f "$PLATFORM_STATE/argocd-repo"
  fi
  public_key="$(cut -d ' ' -f 1,2 "$PLATFORM_STATE/argocd-repo.pub")"
  existing_keys="$(gh api "repos/$REPOSITORY/keys" --paginate --jq '.[].key')"
  if ! grep -Fxq "$public_key" <<< "$existing_keys"; then
    gh repo deploy-key add "$PLATFORM_STATE/argocd-repo.pub" --repo "$REPOSITORY" \
      --title devsecops-platform-argocd-readonly
  fi
  k -n argocd create secret generic platform-repository \
    --from-literal=type=git --from-literal="url=git@github.com:$REPOSITORY.git" \
    --from-file="sshPrivateKey=$PLATFORM_STATE/argocd-repo" --dry-run=client -o yaml | k apply -f -
  k -n argocd label secret platform-repository argocd.argoproj.io/secret-type=repository
fi
k apply -f "$PLATFORM_ROOT/platform/gitops/project.yaml"
k apply -f "$PLATFORM_ROOT/platform/gitops/applications.yaml"
k -n argocd get applications
