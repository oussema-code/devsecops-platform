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

## Current work

Publish the approved private repository and verify its manifest/secret CI checks.

## Observed limitations

Redis remains ephemeral and single-replica. Both environments share one physical
host and one control plane. PodDisruptionBudgets are not evidence of failure
recovery. No worker-failure or canary experiment has been performed. Runtime
inotify limits were increased for multi-node startup; persistence is documented
but was not installed. No claims of production readiness.

## Remaining roadmap

GitHub delivery and Argo CD; security scanning/signing/admission; metrics, logs,
traces and alerts; OpenTofu/LocalStack; canary rollback, scaling and recovery.
