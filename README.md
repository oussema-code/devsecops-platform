# DevSecOps & GitOps platform

Production-style delivery and operations around Google's Online Boutique.
Application features remain upstream; this repository owns the platform.

**Current scope:** three-node kind cluster, Cilium/Hubble, separate staging and
production namespaces, digest-pinned application images, restricted Pod
security, explicit network policies, replicas/disruption budgets, automated
manifest checks, and checkout/isolation verification. See
[implementation status](IMPLEMENTATION_STATUS.md) for what has actually passed.
GitOps, the full security pipeline, telemetry, LocalStack, and advanced recovery
remain roadmap items until their implementation is recorded there.

## Run locally

Requirements: Linux, Docker, kind 0.33.0, kubectl 1.36.x, Helm 3.22.x, Python 3.12+
with `pip install -r requirements-dev.txt`. This development host has 32 GB RAM;
the full platform shares capacity with the preserved single-node lab. See
[host prerequisites](docs/operations.md) before creating nodes.

```bash
make test
make cluster-up
make deploy
make verify
```

These commands use only `.platform/kubeconfig`, context `kind-devsecops-platform`.
They do not change `lab/`, `.lab/kubeconfig`, or the existing `devsecops-lab` cluster.
`make deploy` is the initial local bootstrap; GitOps will replace it as the normal
deployment mechanism once Argo CD is configured.

Run each access command in its own terminal:

| Command | Local address |
| --- | --- |
| `make storefront` | http://127.0.0.1:18081 — staging |
| `make production` | http://127.0.0.1:18082 — production environment |
| `make hubble` | http://127.0.0.1:12000 — network flows |

All forwarding binds to loopback. `make verify` creates temporary tunnels,
checks out with mock payment data in each environment, and cleans the tunnels up.

## Repository map

- `platform/`: kind topology, pinned component versions, Helm values.
- `apps/online-boutique/`: vendored manifests and Kustomize environment overlays.
- `upstream.lock.json`: upstream release and exact Git commit.
- `scripts/`, `tests/`: provisioning and independent validation.
- `docs/architecture.md`: approved decisions and diagrams.
- `docs/operations.md`: operational instructions and known limits.
- `lab/`: original single-node setup, preserved.
- `.platform/`, `.lab/`, `microservices-demo/`: ignored local runtime state and upstream checkout.

The copied Online Boutique manifests retain Google's Apache-2.0 license in
`apps/online-boutique/base/LICENSE`. Their initial digest pins come from the
previously verified lab baseline. Source is pinned independently in
`upstream.lock.json`; the upstream working checkout may be at a different commit
and is never used implicitly as the release source.

This is a local production-style platform, not an Internet-facing production
deployment. Three containers still share one host. Redis cart storage remains
ephemeral; persistence and disaster recovery need a separate architecture decision.
