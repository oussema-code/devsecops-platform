# Implementation status

## Working agreement

2026-11-05: implementation mode. The assistant builds and verifies the project;
the user chooses major architectural decisions. Architecture diagrams remain
required. The former learning checkpoints are historical, not implementation gates.

## Approved architecture

- New kind cluster `devsecops-platform`: one control-plane node, two workers.
- Preserve `devsecops-lab` and its kubeconfig and application.
- Separate platform repository at the workspace root; pin upstream Online Boutique.
- Cilium with Hubble for network policy enforcement and flow inspection.
- Staging and production namespaces in the shared platform cluster.
- Private GitHub repository `oussema-code/devsecops-platform`.

## Verified foundation — 2026-11-05

- Kubernetes 1.36.4: all three platform nodes Ready.
- Cilium 1.20.4 agents, Hubble Relay, and Hubble UI available.
- Staging: 12 ready application Pods, including the load generator.
- Production: 21 ready application Pods; two replicas per stateless service,
  one Redis, load generator scaled to zero.
- All 11 application Services in each namespace have ready endpoints.
- Browse, product page, add-to-cart, mock checkout: HTTP 200 in both environments.
- Allowed loadgenerator-to-frontend connection succeeds. Direct Redis access and
  cross-namespace access to production's frontend time out after successful DNS.
- Five manifest contract tests pass, including three negative cases.
- Gitleaks 8.30.1 scans the publishable tree without findings and rejects a
  generated fake AWS access-key fixture. Trivy secret scan also passed.
- Local logs are in ignored `.platform/`; no kubeconfigs or credentials are tracked.

## Verified delivery foundation

- Private repository created: https://github.com/oussema-code/devsecops-platform.
- Initial GitHub Actions validation run succeeded: 42083106997.
- Argo CD 3.6.1 (chart 10.14.0) installed with a read-only repository deploy key.
- Staging auto-sync and production explicit sync both reached Synced/Healthy on
  foundation revision `f55452ca8a9630a68faec797fe82a11d24b463a1`.
- Release artifact validation tests pass; GitHub workflow syntax passes actionlint.

## Verified since the delivery foundation (2026-11-05/06, Codex sessions)

- Redis carts in both environments moved to persistent claims (`redis-cart-data`,
  Argo CD `Prune=false`). Snapshots were restored into fresh Redis instances and
  checkout plus network isolation passed after the switch. `scripts/redis-snapshot.py`
  backs up and restores into a new claim.
- Telemetry installed in `monitoring`: kube-prometheus-stack, blackbox storefront
  probe, Loki, Tempo, OpenTelemetry Collector, Alloy. Prometheus returned probe and
  trace span-metric series. The Grafana dashboard ConfigMap failed to load on the
  first run (file not yet written); re-run `make observability-up` to load it.
- First all-service release run 42085163342 was blocked by Trivy's HIGH/CRITICAL
  gate on all 11 images; nothing was published. The reviewed patch set is in
  PR #1 (branch `security/upstream-image-patches`), with go.sum shipped as
  lockfiles after Gitleaks flagged Go module hashes. PR #1 checks: not re-confirmed.

## Verified AWS lab — 2026-11-06

- OpenTofu 1.13.9 / AWS provider 6.72.0 against LocalStack 2026.10.6 (licensed).
  Guarded plan and apply created all resources with no deletions. A re-plan reports
  no changes. `make aws-verify`: S3 upload plus duplicate SQS delivery are processed
  twice into one identical DynamoDB item, and a poison message reaches the DLQ.
  Log: `.platform/aws-lab-run.log`. One-shot runner: `scripts/run-aws-lab.sh`.
- Fixes found during the run: provider >= 6.23 reads bucket tags via S3 Control,
  which was not redirected and reached real AWS (rejected, 403, nothing created).
  S3 Control now targets `localhost.localstack.cloud:14566`. The verifier now uses
  LocalStack's own Python, which has boto3.

## Verified frontend canary — 2026-11-06 (commits 00cb8dc, f0fec3f)

- Argo Rollouts 2.43.9 installed. Frontend Pods handed to the `frontend` Rollout in
  both environments with no storefront gap; the Deployment is held at 0 replicas.
- Staging auto-synced and production was explicitly synced to `main`; both Synced.
  Argo CD ignores only the Rollouts-managed selector hash on `frontend-canary`.
- `make verify` passed: 3 nodes, checkout in both environments, network isolation.
- `make canary-drill` on production: a candidate that cannot reach the catalog was
  aborted by AnalysisRun `frontend-59d7cd498d-2-1` (Failed). Stable Pods kept serving
  checkout and the canary scaled down. A harmless candidate passed analysis
  (`frontend-659c75b9df-4-1` Successful) and was promoted. The Git-defined template
  was then restored through a second passing canary.
- Log: `.platform/platform-run.log`. Runner: `scripts/run-platform-steps.sh`.

## Verified first signed release — 2026-11-06

- Run 42245962626 (PR #1 merged as 48ce295): 11 images built from upstream
  5b608cb with reviewed patches, passed Trivy HIGH/CRITICAL, published to GHCR,
  signed with Cosign keyless and attested with CycloneDX SBOMs. The `stage` job first
  stopped on private packages, as designed. After the packages were made public it
  committed 72fbd7a.
- Staging: canary AnalysisRun `frontend-5694d6c78-2-1` Successful; all 11 services on
  `ghcr.io/oussema-code/boutique-*` digests; `verify-platform.py` PASS.
- Production: PR #2 (89b8fa6) copied the same digests, then an explicit sync approved by
  the operator. Canary AnalysisRun `frontend-5694d6c78-6-1` Successful, 2 replicas per
  service, `verify-platform.py` PASS. Evidence: `.platform/release-check-*.txt`.

## Verified admission control and recovery — 2026-11-07 (`scripts/finish-platform.sh`)

- Kyverno 3.9.2 (v1.19.2), 2 admission replicas on different workers.
  `boutique-release-signatures` in **Enforce**: platform images must be signed by
  `release.yml` on `main`; anything else must match the reviewed busybox/redis digests.
- Server-side dry runs: the signed checkoutservice digest was admitted. The upstream
  Google image, `nginx:1.29` and the tag-only `boutique-checkoutservice:latest` were
  denied by the policy. A signed workload (cartservice) restarted normally under Enforce.
- Redis restore drill: a production backup (16 keys, checksum OK) was restored into a
  new claim and loaded by an isolated Redis. The drill claim was then deleted.
- Worker-loss drill: `devsecops-platform-worker2` (7 production Pods, not Redis) was
  stopped for 8 minutes. Production checkout: 1 failure at t+10s, then 28 consecutive
  successes from t+46s. Replacement Pods scheduled on the remaining worker. After the
  node returned, every Deployment recovered and `verify-platform.py` passed in both
  environments; both Argo CD apps Synced/Healthy.
- Observation: several worker2 Pods and one Kyverno replica showed a container restart
  about 3 minutes before the drill, during the Kyverno upgrade. Not investigated.

## Remaining options (not required)

- Frontend HorizontalPodAutoscaler with a load test.
- Canary analysis for backend services (needs a mesh or per-service checks).
- Migrate the Kyverno policy to `ImageValidatingPolicy` before the legacy API is removed.

## Observed limitations

Redis is single-replica; its local volume is tied to one worker, so node loss
requires restore from backup. Both environments share one host and one control
plane. The worker-loss drill stopped a node container, not the host; losing the
worker that holds a Redis volume still requires the restore procedure. The canary uses replica-ratio traffic splitting
(no service mesh), so during analysis about half of real requests reach the
candidate. Only the frontend is canaried; backends roll with Deployment updates.
Runtime inotify limits must be raised after each reboot. No claims of production readiness.
