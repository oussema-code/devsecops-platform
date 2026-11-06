# Operations

## Host prerequisites

The host must permit enough inotify objects for multiple Kubernetes nodes.
The original runtime values, 128 instances and 65,536 watches, caused systemd in
new kind nodes to exit with `Failed to create control group inotify object: Too
many open files`. On 2026-11-05 the runtime values were raised to 1,024 instances
and 1,048,576 watches. This reserves a higher ceiling, not that amount of memory
up front. Runtime settings reset on reboot.

To configure the prerequisite after a reboot:

```bash
sudo sysctl -w fs.inotify.max_user_instances=1024 fs.inotify.max_user_watches=1048576
```

For persistence, an administrator can put those values in
`/etc/sysctl.d/99-devsecops-platform.conf` and run `sudo sysctl --system`.
No persistent host configuration was installed by this project.

## Verify normal operation

`make verify` checks all three Ready nodes, desired replicas, Service endpoints,
and a complete mock checkout in both environments. It also tests that staging's
load generator can reach its frontend, cannot reach Redis directly, and cannot
reach production's frontend. DNS must succeed before a denial test can pass.
These are sampled policy checks, not an exhaustive test of every possible flow.

`make test` renders both Kustomize overlays and checks immutable image references,
Pod security settings, environment names, quotas, replicas, and both sides of
required service connections. Negative tests ensure mutable images, unrestricted
egress, and missing dependency rules are rejected.

## Diagnose a failed rollout

Always use the platform's kubeconfig and context:

```bash
kubectl --kubeconfig .platform/kubeconfig --context kind-devsecops-platform get pods -A
kubectl --kubeconfig .platform/kubeconfig --context kind-devsecops-platform -n boutique-staging get events --sort-by=.lastTimestamp
kubectl --kubeconfig .platform/kubeconfig --context kind-devsecops-platform -n boutique-staging logs deployment/frontend --tail=100
```

For an image pull failure, inspect Pod events and registry access. For a Pending
Pod, inspect quota, requests and available node capacity. For a connection failure,
check Service endpoints and Hubble drops before changing network policies.

## Networking and storage boundaries

- Namespace-wide default deny applies to ingress and egress. Allow rules cover
  DNS and the explicitly enumerated application dependencies.
- HTTP access currently uses local port forwarding; no public ingress is configured.
- The optional shopping-assistant feature is disabled upstream and not deployed.
- Each environment has its own Redis on a 1 GiB `redis-cart-data` claim with
  RDB snapshots every 60 s. The claim survives Pod replacement and is excluded
  from Argo CD pruning, but it is bound to one worker's local disk. Losing that
  worker requires `scripts/redis-snapshot.py ENV restore FILE NEW_CLAIM`. Redis is
  still a single point of failure, not an HA data service.
- Production stateless services have two replicas and preferred spread across
  workers. Disruption budgets limit voluntary eviction, not abrupt node failures.
- Staging runs the upstream load generator with ten users. Production's load
  generator is scaled to zero; verification performs only a mock checkout.
- Hubble UI and Relay use ClusterIP services and are accessed through loopback
  tunnels. Relay's client-facing gRPC TLS is not enabled in this local setup.
  Agent-to-relay TLS uses the Cilium chart defaults. Do not expose Relay publicly.
- Deleting the new cluster destroys its local state. The old lab is a different
  cluster and must never be targeted by platform cleanup.

## Frontend canary

The frontend Pods belong to the `frontend` Rollout (Argo Rollouts). The frontend
Deployment remains the Pod template and is held at zero replicas. A template or
image change starts a canary: half the replicas move to the candidate, then an
AnalysisRun executes the mock checkout three times against `frontend-canary`
(candidate Pods only). Any failure aborts. The stable Pods keep serving and the
`FrontendCanaryAborted` alert fires.

```bash
kubectl --kubeconfig .platform/kubeconfig --context kind-devsecops-platform -n boutique-production get rollout frontend
kubectl --kubeconfig .platform/kubeconfig --context kind-devsecops-platform -n boutique-production get analysisruns
kubectl --kubeconfig .platform/kubeconfig --context kind-devsecops-platform -n boutique-production logs -l app=canary-check --tail=50
```

After an abort, fix forward or revert the change in Git. Returning the template to
the stable version restores the Rollout without a new canary. The Rollouts dashboard
is deliberately not installed. `make canary-drill` exercises both outcomes on
production and restores the Git-defined template.
