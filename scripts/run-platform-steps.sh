#!/usr/bin/env bash
# Runs the remaining live-cluster steps and records everything in
# .platform/platform-run.log so the assistant can read the result.
# Asks before the three changes that leave this machine or touch production:
# git push, the production sync, and the production canary drill.
# Safe to re-run: finished steps are skipped or are no-ops.
set -uo pipefail
cd "$(dirname -- "${BASH_SOURCE[0]}")/.."
source scripts/common.sh
log=.platform/platform-run.log
exec > >(tee "$log") 2>&1
step() { echo; echo "===== $(date +%H:%M:%S) $* ====="; }
fail() { echo; echo "RESULT: FAILED at: $1"; exit 1; }
confirm() {
  local answer
  read -r -p "$1 [y/N] " answer </dev/tty
  [[ $answer == [yY] ]]
}
app_state() { k -n argocd get application "$1" -o jsonpath='{.status.sync.revision} {.status.sync.status} {.status.health.status} {.status.operationState.phase}'; }

step "Preflight: host limits and cluster"
if [[ "$(sysctl -n fs.inotify.max_user_instances)" -lt 1024 ]]; then
  echo 'inotify limit was reset (reboot?). Run this, then re-run the script:'
  echo '  sudo sysctl -w fs.inotify.max_user_instances=1024 fs.inotify.max_user_watches=1048576'
  fail "inotify limit"
fi
k get nodes || fail "cluster unreachable"
k wait nodes --all --for=condition=Ready --timeout=120s || fail "nodes not Ready"
[[ "$(git branch --show-current)" == main ]] || fail "git is not on main (currently: $(git branch --show-current))"

step "Unit and manifest tests"
python3 -m unittest discover -s tests -v || fail "tests"
bash -n scripts/*.sh || fail "shell syntax"

step "Observability (reload dashboard + canary-abort alert)"
bash scripts/observability-up.sh || fail "observability-up"

step "Argo Rollouts controller"
bash scripts/rollouts-up.sh || fail "rollouts-up"

step "Hand frontend Pods to the Rollout beside the running Deployment"
bash scripts/migrate-frontend-rollout.sh || fail "rollout-migrate"
for ns in boutique-staging boutique-production; do k -n "$ns" get rollout frontend; done

step "Commit"
git add -A
git status --short
if git diff --cached --quiet; then
  echo "Nothing new to commit."
else
  echo "Secret scan of the tree that will be committed:"
  scan="$PLATFORM_STATE/scan-commit"; rm -rf "$scan"; mkdir -p "$scan"
  git checkout-index --all --prefix="$scan/"
  docker run --rm -v "$scan:/repo:ro" \
    ghcr.io/gitleaks/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f \
    dir /repo --redact --no-banner || { git reset -q; fail "gitleaks found a secret; nothing committed"; }
  git commit -q -F - <<'MSG' || fail "git commit"
Add frontend canary, verified LocalStack lab, Kyverno install hardening

- Argo Rollouts canary for the storefront frontend: workloadRef Rollout,
  50% step, checkout AnalysisRun against candidate Pods, automatic abort.
- OpenTofu/LocalStack AWS lab verified end to end; S3 Control endpoint fix.
- Kyverno reinstall with diagnostics; status and docs updated.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011mwto2h7N9y1dUYGi5hqPN
MSG
  git log --oneline -1
fi

step "Push to GitHub (staging auto-deploys from main)"
if [[ "$(git rev-parse HEAD)" != "$(git rev-parse '@{u}' 2>/dev/null)" ]]; then
  confirm "Push $(git rev-parse --short HEAD) to origin/main now?" || fail "push declined (re-run when ready)"
  git push origin HEAD:main || fail "git push"
fi
sha="$(git rev-parse HEAD)"

step "Apply Argo CD Application definitions"
k apply -f platform/gitops/applications.yaml || fail "apply applications"

step "Wait for staging to sync $sha"
k -n argocd annotate application boutique-staging argocd.argoproj.io/refresh=hard --overwrite >/dev/null
for _ in $(seq 1 120); do
  state="$(app_state boutique-staging)"; echo "staging: $state"
  [[ $state == "$sha Synced Healthy"* ]] && break
  sleep 5
done
[[ "$(app_state boutique-staging)" == "$sha Synced Healthy"* ]] || fail "staging did not reach Synced/Healthy"
k -n boutique-staging get rollout,deployment frontend

step "Production sync (explicit gate)"
if [[ "$(app_state boutique-production)" != "$sha Synced Healthy"* ]]; then
  confirm "Sync boutique-production to $sha now?" || fail "production sync declined (re-run when ready)"
  k -n argocd annotate application boutique-production argocd.argoproj.io/refresh=hard --overwrite >/dev/null
  k -n argocd patch application boutique-production --type merge -p \
    "{\"operation\":{\"initiatedBy\":{\"username\":\"$USER\"},\"sync\":{\"revision\":\"$sha\",\"syncOptions\":[\"CreateNamespace=true\",\"ServerSideApply=true\",\"RespectIgnoreDifferences=true\"]}}}" \
    || fail "start production sync"
  for _ in $(seq 1 120); do
    state="$(app_state boutique-production)"; echo "production: $state"
    [[ $state == "$sha Synced Healthy Succeeded" ]] && break
    [[ $state == *" Failed" || $state == *" Error" ]] && break
    sleep 5
  done
  [[ "$(app_state boutique-production)" == "$sha Synced Healthy Succeeded" ]] || {
    k -n argocd get application boutique-production -o jsonpath='{.status.operationState.message}'; echo
    fail "production sync"; }
fi
k -n boutique-production get rollout,deployment frontend

step "Platform verification (checkout + isolation, both environments)"
python3 scripts/verify-platform.py || fail "verify-platform"

step "Canary drill on production"
if confirm "Run the production canary drill now? (~6 min; half of production frontend Pods briefly run a broken build)"; then
  python3 scripts/canary-drill.py || fail "canary-drill"
else
  echo "Drill skipped."
fi

step "Kyverno (non-blocking: failure is reported, canary results above still stand)"
if bash scripts/security-up.sh; then
  echo "KYVERNO: OK"
  k get policyreports -A 2>/dev/null | head -20
else
  echo "KYVERNO: FAILED (diagnostics above)"
fi

step "Final state"
k -n argocd get applications
for ns in boutique-staging boutique-production; do k -n "$ns" get rollout frontend; done
echo; echo "RESULT: ALL REQUIRED STEPS PASSED"
