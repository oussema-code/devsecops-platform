#!/usr/bin/env bash
# Collects the result of a release in one environment into .platform/release-check-<env>.txt
set -uo pipefail
cd "$(dirname -- "${BASH_SOURCE[0]}")/.."
source scripts/common.sh
env="${1:-staging}"; ns="boutique-$env"; sync="${2:-}"
out=".platform/release-check-$env.txt"
exec > >(tee "$out") 2>&1
echo "===== $(date) $ns"
git pull -q --ff-only origin main && git log --oneline -1
k -n argocd annotate application "boutique-$env" argocd.argoproj.io/refresh=hard --overwrite >/dev/null
if [[ $env == production && $sync == --sync ]]; then
  # Running with --sync is the explicit production approval.
  echo "== explicit production sync to $(git rev-parse --short HEAD), approved by $USER"
  sleep 5
  k -n argocd patch application boutique-production --type merge -p \
    "{\"operation\":{\"initiatedBy\":{\"username\":\"$USER\"},\"sync\":{\"revision\":\"$(git rev-parse HEAD)\",\"syncOptions\":[\"CreateNamespace=true\",\"ServerSideApply=true\",\"RespectIgnoreDifferences=true\"]}}}"
fi
echo "== waiting for Argo CD and the frontend Rollout (up to 15 min)"
for _ in $(seq 1 180); do
  app=$(k -n argocd get application "boutique-$env" -o jsonpath='{.status.sync.revision} {.status.sync.status} {.status.health.status}')
  phase=$(k -n "$ns" get rollout frontend -o jsonpath='{.status.phase}')
  echo "$(date +%T) app: $app | rollout: $phase"
  [[ $app == "$(git rev-parse HEAD) Synced Healthy" && $phase == Healthy ]] && break
  [[ $phase == Degraded ]] && break
  sleep 5
done | awk '!seen[$0]++' | tail -12
echo "== rollout"; k -n "$ns" get rollout frontend -o jsonpath='{.status.phase} stable={.status.stableRS} abort={.status.abort}{"\n"}'
echo "== analysis runs"; k -n "$ns" get analysisruns --sort-by=.metadata.creationTimestamp
echo "== running images"
k -n "$ns" get pods -o jsonpath='{range .items[*]}{.status.phase}{"\t"}{range .spec.containers[*]}{.image}{" "}{end}{"\n"}{end}' | sort | uniq -c
echo "== kyverno signature results (Audit)"
k -n "$ns" get policyreports -o json | python3 -c '
import json,sys,collections
c=collections.Counter()
fails=set()
for r in json.load(sys.stdin)["items"]:
    for res in r.get("results",[]):
        if res.get("policy")!="boutique-release-signatures": continue
        c[res["result"]]+=1
        if res["result"]!="pass": fails.add((res["result"], res.get("message","")[:160]))
print(dict(c))
for f in sorted(fails)[:15]: print(*f)'
echo "== platform verification"
python3 scripts/verify-platform.py && echo "VERIFY: PASS" || echo "VERIFY: FAIL"
