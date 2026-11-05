# Learning progress

> 2026-11-05: the user switched to implementation mode with architecture diagrams
> and user-owned architectural decisions. This notebook is retained as historical
> context. Resume implementation from `IMPLEMENTATION_STATUS.md`, not the pending
> learning exercise below. No new understanding is claimed from implementation.

Standing working method: [MENTORING_WORKFLOW.md](MENTORING_WORKFLOW.md). Future sessions must read it together with this notebook, as directed by [AGENTS.md](AGENTS.md).

## Phase 1 — Kubernetes foundation

### Completed milestones

- 2026-11-04 — Inspected the Ubuntu host, confirmed Docker access, and reviewed the Online Boutique v0.10.7 release manifest and registry metadata. The bundle defines 12 Deployments with application container requests totaling 1,570 millicores and 1,368 MiB.
- 2026-11-04 — Provisioned kind v0.33.0 with a Ready Kubernetes v1.36.4 node. Verified all 12 Deployments available, all 11 Services with a ready endpoint, and four Service DNS lookups from the load generator. The storefront smoke test returned HTTP 200 at each step and displayed mock order confirmation.

### Implemented components

- [kind configuration](lab/kind.yaml) and the dedicated local kubeconfig in `.lab/kubeconfig`.
- [Namespace](lab/namespace.yaml) and [digest-pinned Online Boutique workload](lab/online-boutique.yaml).
- [Browse-to-checkout smoke test](lab/smoke-test.py) and [lab instructions](lab/README.md).

### Approved decisions

- Use kind v0.33.0 with one Kubernetes v1.36.4 control-plane node that also runs workloads. Pin the node image by digest.
- Use a separate kubeconfig and an `online-boutique` namespace.
- Adapt the [upstream release manifest](https://github.com/GoogleCloudPlatform/microservices-demo/blob/5b608cb1dfe317d05e4f1bb8c99b7618452fde87/release/kubernetes-manifests.yaml), pin workload images by digest, and use the existing internal frontend Service with a temporary loopback port-forward on port 18080. Omit the external LoadBalancer Service.
- Retain upstream probes, resource settings, the Locust load generator, and ephemeral Redis cart storage for the baseline.
- 2026-11-05 — Run two catalog replicas, based on the learner's proposal. The extra replica requests 100 millicores of CPU and 64 MiB of memory.

### Concepts introduced — understanding still to confirm

- Browser HTTP, service-to-service gRPC, and Redis in the shopping flow.
- ClusterIP Services and DNS as stable endpoints for changing Pods.
- Local port-forwarding, image digest pinning, and the limits of a single-node lab.
- ReplicaSet retries during startup and readiness as the signal for eligible Service endpoints.
- 2026-11-05 — User feedback showed the implementation was insufficiently explained before the exercise. Revisit the setup from the host, Docker, and kind through application deployment, with one concrete example at a time.

### Scenarios practiced

- The first exercise was introduced before the foundations were sufficiently explained. On 2026-11-05, cleared the artificial rollout fault by reapplying the baseline manifest and verified the recommendation Deployment rolled out successfully.
- 2026-11-05 — Confirmed the missing local tunnel, restored port-forwarding, and passed all four smoke-test steps through mock order confirmation.
- 2026-11-05 — With two catalog Pods Ready, deleted the older Pod while sampling 100 product-page requests at roughly five requests per second. Observed 95 successful responses and five HTTP 500 responses during the transition. Kubernetes restored two Ready replicas automatically. The frontend logged catalog RPC connection refused errors. Follow-up checkout passed. Traffic continuity remains an open investigation. This was a controlled deletion on one node. Per-request evidence is in the ignored local file `.lab/catalog-replica-experiment.json`.

### Demonstrated understanding

- 2026-11-05 — Correctly explained that replacing a catalog Pod requires the endpoint list to reflect the new Pod IP, while the frontend configuration stays unchanged because it uses the stable Service destination. This demonstrates reasoning about the architecture; no replacement experiment was performed. Readiness eligibility and DNS resolution remain to verify.
- 2026-11-05 — Defined a working store through customer actions: view the catalog, add items to the cart, and complete a purchase. Connected these actions to deployment acceptance criteria.
- 2026-11-05 — Prioritized reestablishing the connection after connection refused. Follow-up checks confirmed the tunnel was absent and the customer journey worked after restoring access.
- 2026-11-05 — Proposed additional replicas to cover a Pod failure. Explained that ready replicas are eligible to serve traffic concurrently.

### Weak areas to revisit

Teaching needs adjustment before assessing weak areas. User prefers substantive engineering decisions, short explanations, and prediction followed by experiments. Avoid trivial quizzes and lengthy lists of definitions. Explain unfamiliar terms as they become necessary. Show diagnostic commands before executing them, explain the output fields to inspect and how results guide the next check, and maintain a visible checklist. Give the learner space to run commands and interpret evidence.

### Current module — Services and service discovery

- Objective: explain how the frontend reaches changing catalog Pods through a stable Service name and address.
- 2026-11-05 — Completed the read-only architecture walkthrough. Learner reports understanding the architecture and explicitly chose to advance; this is self-reported understanding, not a complete assessment of every component.
- Learner reports successfully browsing products, adding an item to the cart, and completing mock payment. Recognized the importance of a working customer journey as baseline evidence. Mentor clarified that Pod readiness proves only the configured readiness check, not the entire purchase workflow; learner explanation of this distinction remains to confirm.
- Explained the load generator as continuous simulated shoppers, distinct from a single smoke-test journey. Understanding not yet assessed.
- Current decision: retain the existing ClusterIP architecture while examining its behavior. No workload changes or new failure experiments are authorized by advancing the lesson alone.

### Commands examined in the current module

- `kubectl --kubeconfig .lab/kubeconfig -n online-boutique get service productcatalogservice -o yaml`: inspect Service address, selector, and port mapping.
- `kubectl --kubeconfig .lab/kubeconfig -n online-boutique get pods -l app=productcatalogservice -o wide`: identify matching Pods and their addresses.
- `kubectl --kubeconfig .lab/kubeconfig -n online-boutique get endpointslices -l kubernetes.io/service-name=productcatalogservice`: inspect destinations; use JSONPath or YAML to see each endpoint's readiness.
- Observed on 2026-11-05: Service 10.96.98.56:3550; Pod endpoints 10.244.0.18:3550 and 10.244.0.19:3550, both ready. These are a snapshot, not permanent Pod addresses.
- 2026-11-05 — Attempted `kubectl exec deployment/frontend -- sh -c 'cat /etc/resolv.conf; command -v getent; command -v nslookup'` with the dedicated kubeconfig and namespace. It could not run because the frontend image lacks `sh`; this is a tooling limitation, not evidence of DNS failure. Did not install tools or change the image.
- Used `kubectl exec deployment/loadgenerator -- python3 -c '...'` with Python's `pathlib.Path` to read `/etc/resolv.conf` and `socket.getaddrinfo("productcatalogservice", 3550, family=socket.AF_INET, type=socket.SOCK_STREAM)` to resolve the Service name. Observed nameserver 10.96.0.10 and namespace search domain online-boutique.svc.cluster.local. Resolved IPv4 address 10.96.98.56 matched the live catalog Service ClusterIP.
- Read the frontend and load-generator Pod specs: both have ClusterFirst DNS policy and no explicit hostNetwork or dnsConfig overrides. Successful lookup was observed from the load generator, not directly from the frontend. Name resolution alone does not verify TCP connectivity or a successful gRPC call. Learner interpretation remains pending.

### Troubleshooting procedure introduced — not yet independently demonstrated

Identify the failing customer action and caller, then compare Service selector, matching Pod labels and readiness, and EndpointSlice addresses. Inspect DNS and connectivity separately when indicated. A correct mapping alone does not prove successful requests. Preserve evidence from the symptom interval before assigning a cause.

### Concepts needing reinforcement and next exercise

- Distinguish the Service name and ClusterIP from Pod addresses; explain selectors and readiness-qualified endpoints.
- DNS resolution was verified from the existing load-generator Pod; direct frontend resolution and connection distribution have not been tested. Avoid assuming requests alternate evenly between replicas, particularly with persistent gRPC connections.
- Next exercise: let the learner interpret the namespace search domain and reason about the destination name if a caller moves to a separate namespace. The caller-configuration and endpoint-replacement reasoning exercise is complete. Do not delete Pods or introduce faults.
- The previous catalog interruption investigation remains paused until normal operation is understood and the learner chooses to revisit it.
