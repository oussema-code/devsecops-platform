# Platform architecture

Status: foundation implementation in progress. The target delivery and telemetry
systems below are planned until marked verified in `IMPLEMENTATION_STATUS.md`.

## Approved local topology

```mermaid
flowchart TB
  Host[Ubuntu host / Docker]
  Host --> Old[Existing devsecops-lab: preserved]
  Host --> CP[Platform control plane]
  Host --> W1[Platform worker 1]
  Host --> W2[Platform worker 2]
  CP --> W1
  CP --> W2
  Cilium[Cilium: network policy enforcement] --- CP
  Cilium --- W1
  Cilium --- W2
  Cilium --> Hubble[Hubble: network flow inspection]
```

The platform uses `.platform/kubeconfig` and context `kind-devsecops-platform`.
The API listens on loopback. Pod CIDR is `10.246.0.0/16`; Service CIDR is
`10.112.0.0/16`, separate from the old lab. Cilium uses Kubernetes IPAM and
retains kube-proxy. One control plane is not HA; all three nodes share a physical
host. This simulates worker loss, not host-level disaster tolerance.

## Target delivery architecture

```mermaid
flowchart LR
  Source[Pinned upstream source] --> CI[GitHub Actions]
  CI --> Checks[Tests / Gitleaks / Trivy]
  Checks --> Images[Signed container images + SBOM]
  Images --> Change[GitOps digest update]
  Change --> Argo[Argo CD]
  Argo --> Staging[Staging]
  Staging --> Review[Reviewed production promotion]
  Review --> Production[Production environment]
  Policy[Kyverno admission] -.-> Staging
  Policy -.-> Production
  Production --> Telemetry[Prometheus / Loki / OpenTelemetry / Grafana]
  Staging --> Telemetry
  IaC[OpenTofu] --> LocalStack[Separate local AWS lab]
```

## Architecture decisions

| Date | Decision | Rationale / trade-off |
| --- | --- | --- |
| 2026-11-05 | Separate three-node cluster | Preserve existing work; permit worker recovery tests; consumes more RAM. |
| 2026-11-05 | Platform repository separate from upstream | Own infrastructure and delivery history without modifying application features. |
| 2026-11-05 | Pin Online Boutique v0.10.7 commit and workload digests | Reproduce the existing working baseline; upgrades must be explicit. |
| 2026-11-05 | Cilium with Hubble | Enforce network policies and inspect flows; more components than kindnet. |
| 2026-11-05 | Staging and production namespaces in one cluster | Affordable local promotion and isolation testing; shared control plane and host. |
| 2026-11-05 | Private `oussema-code/devsecops-platform` GitHub repository | Approved hosting destination for platform source and GitHub Actions. |

## Application request flow

```mermaid
flowchart LR
  Browser[Browser / smoke test] -->|Loopback port-forward| Frontend
  Load[Staging load generator] --> Frontend
  Frontend --> Catalog[Product catalog]
  Frontend --> Recommendations
  Recommendations --> Catalog
  Frontend --> Cart
  Cart --> Redis[Redis: environment-local carts]
  Frontend --> Checkout
  Frontend --> Currency
  Frontend --> Shipping
  Frontend --> Ads
  Checkout --> Catalog
  Checkout --> Cart
  Checkout --> Currency
  Checkout --> Shipping
  Checkout --> Payment[Mock payment]
  Checkout --> Email[Mock email]
```

Each environment has its own copy of this graph. Internal calls use stable
Kubernetes Service names and gRPC, except Cart-to-Redis. Cilium permits only the
declared dependency edges and DNS. No application edge crosses namespaces.
Production's ten stateless services run two replicas; Redis remains one replica.
Staging also runs the load generator. No ingress controller or public endpoint
has been introduced.

## Sources

- [Cilium on kind](https://docs.cilium.io/en/stable/installation/kind/)
- [Online Boutique pinned source](https://github.com/GoogleCloudPlatform/microservices-demo/tree/5b608cb1dfe317d05e4f1bb8c99b7618452fde87)
- [Argo CD automated reconciliation](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/)
