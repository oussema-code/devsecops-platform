# Online Boutique on kind

Run these commands from the platform workspace root. The lab uses Docker, kind v0.33.0, a Kubernetes v1.36-compatible kubectl, and Python 3 for the smoke test.

## Start the lab

```bash
mkdir -p -m 700 .lab
KIND_EXPERIMENTAL_PROVIDER=docker kind create cluster --config lab/kind.yaml \
  --kubeconfig "$PWD/.lab/kubeconfig" --wait 180s
kubectl --kubeconfig .lab/kubeconfig apply -f lab/namespace.yaml
kubectl --kubeconfig .lab/kubeconfig -n online-boutique apply -f lab/online-boutique.yaml
kubectl --kubeconfig .lab/kubeconfig -n online-boutique \
  wait --for=condition=Available deployment --all --timeout=300s
```

The kind config fixes the node image by digest. The application manifest comes from Online Boutique v0.10.7 and includes the upstream Apache 2.0 license. The local changes pin workload images by digest, omit the external LoadBalancer Service, and run two catalog replicas. The manifest contains the complete workload, so provisioning only needs this workspace and registry access. [kind config](kind.yaml) · [Application manifest](online-boutique.yaml) · [Upstream release manifest](https://github.com/GoogleCloudPlatform/microservices-demo/blob/5b608cb1dfe317d05e4f1bb8c99b7618452fde87/release/kubernetes-manifests.yaml) · [Apache 2.0 license](LICENSE.online-boutique)

The additional catalog replica requests 100 millicores of CPU and 64 MiB of memory. Both replicas run on the same kind node, which remains a shared failure point.

## Verify the storefront

```bash
kubectl --kubeconfig .lab/kubeconfig -n online-boutique get pods,services,endpointslices
kubectl --kubeconfig .lab/kubeconfig -n online-boutique \
  port-forward --address 127.0.0.1 service/frontend 18080:80
```

Keep the forwarding command running and open [the storefront](http://127.0.0.1:18080) or run `python3 lab/smoke-test.py` in another terminal. The smoke test uses an isolated session and dummy checkout data. If the selected frontend Pod terminates, start a new forwarding session.

The Deployments manage Pod replacement. ClusterIP Services and CoreDNS provide stable addresses for callers inside the cluster. Redis cart data lives in an `emptyDir` and is lost when its Pod is replaced. A single kind node provides no node-level failover.

## Diagnose the catalog interruption

- [ ] Check the current catalog Pods with the command below. Inspect `READY`, `STATUS`, and `RESTARTS`. If a Pod is unready or restarting, describe that Pod and inspect its events and logs.

  ```bash
  kubectl --kubeconfig .lab/kubeconfig -n online-boutique get pods -l app=productcatalogservice -o wide
  ```

- [ ] Check which Pods the Service can route to. In the output below, compare `addresses` and `targetRef.name` with the Pod listing, and inspect each endpoint's `conditions.ready`. A missing or unready endpoint leads to inspecting Service selectors, Pod labels, and readiness.

  ```bash
  kubectl --kubeconfig .lab/kubeconfig -n online-boutique get endpointslices -l kubernetes.io/service-name=productcatalogservice -o yaml
  ```

- [ ] Correlate evidence at the failure time. If the system has recovered, capture Pod readiness, Service endpoint changes, and frontend errors during a repeat of the controlled experiment. A healthy snapshot after recovery cannot establish the cause of an earlier interruption.
