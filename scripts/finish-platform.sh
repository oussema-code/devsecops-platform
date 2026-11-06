#!/usr/bin/env bash
# Final live steps: Kyverno Enforce with admission proofs, a Redis restore drill and a
# worker-loss drill. Everything is logged to .platform/finish-run.log for review.
# Asks once before the worker-loss drill, which stops a node container.
set -uo pipefail
cd "$(dirname -- "${BASH_SOURCE[0]}")/.."
source scripts/common.sh
log=.platform/finish-run.log
exec > >(tee "$log") 2>&1
step() { echo; echo "===== $(date +%H:%M:%S) $* ====="; }
fail() { echo; echo "RESULT: FAILED at: $1"; exit 1; }
confirm() { local a; read -r -p "$1 [y/N] " a </dev/tty; [[ $a == [yY] ]]; }

step "Preflight"
[[ "$(sysctl -n fs.inotify.max_user_instances)" -ge 1024 ]] || fail "inotify limit (sudo sysctl -w fs.inotify.max_user_instances=1024 fs.inotify.max_user_watches=1048576)"
git log --oneline -1
k wait nodes --all --for=condition=Ready --timeout=60s || fail "nodes not Ready"
python3 -m unittest discover -s tests || fail "tests"

step "Kyverno: 2 admission replicas, signature policy in Enforce"
bash scripts/security-up.sh || fail "security-up"
k -n kyverno rollout status deployment/kyverno-admission-controller --timeout=300s || fail "kyverno admission rollout"
k -n kyverno get pods -l app.kubernetes.io/component=admission-controller -o wide
k get clusterpolicy boutique-release-signatures -o jsonpath='{.spec.validationFailureAction}{"\n"}'

step "Admission proof (server-side dry runs; nothing is created)"
probe() {  # $1 name, $2 image -> prints admission result
  cat <<YAML | k -n boutique-staging create --dry-run=server -f - 2>&1
apiVersion: v1
kind: Pod
metadata: {name: admission-probe-$1, labels: {app: admission-probe}}
spec:
  automountServiceAccountToken: false
  securityContext: {runAsNonRoot: true, runAsUser: 1000, seccompProfile: {type: RuntimeDefault}}
  containers:
  - name: probe
    image: $2
    resources: {requests: {cpu: 10m, memory: 16Mi}, limits: {cpu: 50m, memory: 32Mi}}
    securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: [ALL]}}
YAML
}
signed="$(k -n boutique-staging get deployment checkoutservice -o jsonpath='{.spec.template.spec.containers[0].image}')"
upstream='us-central1-docker.pkg.dev/online-boutique-ci/microservices-demo/checkoutservice:v0.10.7@sha256:f0e72ff7b438dd2e8776fb142d5132cfa5ba02c523466f1491270c576412d33f'
out="$(probe signed "$signed")"; echo "signed release image -> $out"
[[ $out == *created* ]] || fail "signed image was not admitted"
for bad in "$upstream" "nginx:1.29" "ghcr.io/oussema-code/boutique-checkoutservice:latest"; do
  out="$(probe unsigned "$bad")"; echo "$bad -> $(tr '\n' ' ' <<<"$out" | cut -c1-260)"
  [[ $out == *boutique-release-signatures* ]] || fail "image was not rejected by the policy: $bad"
done
echo "PASS: signed image admitted; upstream, unpinned and tag-only images rejected"

step "Re-admission: restart a signed workload under Enforce"
k -n boutique-staging rollout restart deployment/cartservice
k -n boutique-staging rollout status deployment/cartservice --timeout=300s || fail "signed workload could not restart under Enforce"
echo "PASS: signed workload restarted under Enforce"

step "Redis restore drill (production backup -> new claim -> verified load)"
stamp="$(date +%Y%m%d-%H%M%S)"; backup=".platform/backups/production-drill-$stamp.rdb"; claim="redis-restore-drill-${stamp,,}"
python3 scripts/redis-snapshot.py production backup "$backup" || fail "redis backup"
python3 scripts/redis-snapshot.py production restore "$backup" "$claim" || fail "redis restore"
k -n boutique-production delete pvc "$claim" --wait=false
echo "PASS: backup restored and loaded by an isolated Redis (drill claim removed)"

step "Worker-loss drill"
redis_node="$(k -n boutique-production get pods -l app=redis-cart -o jsonpath='{.items[0].spec.nodeName}')"
victim="$(k get nodes -l '!node-role.kubernetes.io/control-plane' -o name | sed 's#node/##' | grep -vx "$redis_node" | head -1)"
echo "production Redis is on $redis_node (local volume, kept up); stopping $victim"
k get pods -n boutique-production -o wide --field-selector spec.nodeName="$victim" | head -30
if ! confirm "Stop node $victim for about 8 minutes?"; then echo "Worker drill skipped."; else
  start=$(date +%s); docker stop "$victim" >/dev/null || fail "docker stop $victim"
  trap 'docker start "$victim" >/dev/null 2>&1' EXIT
  ok=0; bad=0; first_ok=""
  while (( $(date +%s) - start < 480 )); do
    t=$(( $(date +%s) - start ))
    if python3 -c 'import importlib.util as u,sys; s=u.spec_from_file_location("v","scripts/verify-platform.py"); m=u.module_from_spec(s); s.loader.exec_module(m); m.checkout("boutique-production")' >/dev/null 2>&1; then
      ok=$((ok+1)); echo "t+${t}s checkout OK"
    else
      bad=$((bad+1)); echo "t+${t}s checkout FAILED"
    fi
    sleep 15
  done
  echo "checkouts during node loss: $ok ok, $bad failed"
  k get pods -n boutique-production -o wide | awk '{print $1, $3, $7}' | column -t
  docker start "$victim" >/dev/null; trap - EXIT
  k wait node "$victim" --for=condition=Ready --timeout=300s || fail "node did not come back"
  for ns in boutique-production boutique-staging; do
    for d in $(k -n "$ns" get deployments -o name); do k -n "$ns" rollout status "$d" --timeout=300s >/dev/null || fail "$ns $d not recovered"; done
  done
  echo "worker-loss summary: $ok ok / $bad failed checkouts over 8 minutes"
fi

step "Final verification"
python3 scripts/verify-platform.py || fail "verify-platform"
k -n argocd get applications
echo; echo "RESULT: ALL PASSED"
