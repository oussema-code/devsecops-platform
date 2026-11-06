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

## Not working / not yet verified

- Kyverno 3.9.2 install timed out (`context deadline exceeded`); the signature
  policy is not active. `make security-up` now removes a failed first install,
  waits up to 15 minutes, and prints Pod/event diagnostics on failure.
- Frontend canary (2026-11-06, authored, verified statically only): Argo Rollouts
  chart 2.43.9, `Rollout` using `workloadRef` to the frontend Deployment, 50% step,
  checkout analysis against `frontend-canary`, automatic abort. Manifests validated
  against the Rollouts v1.10.2 CRD schemas; 18 unit tests pass. Not yet installed,
  migrated or drilled on the cluster.

## Next operator steps

1. `make security-up` (after confirming the cluster is healthy).
2. `make observability-up` (loads the dashboard and the canary-abort alert).
3. `make rollouts-up`, `make rollout-migrate`, then commit and push the canary change.
4. Wait for staging to sync; explicitly sync `boutique-production`; `make verify`.
5. `make canary-drill` (production: broken candidate aborts, good one promotes).
6. Review and merge PR #1, then dispatch the release workflow.

## Observed limitations

Redis is single-replica; its local volume is tied to one worker, so node loss
requires restore from backup. Both environments share one host and one control
plane. PodDisruptionBudgets are not evidence of failure recovery. No worker-failure
experiment has been performed. The canary uses replica-ratio traffic splitting
(no service mesh), so during analysis about half of real requests reach the
candidate. Only the frontend is canaried; backends roll with Deployment updates.
Runtime inotify limits must be raised after each reboot. No claims of production readiness.
