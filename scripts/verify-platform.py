"""Check the platform's actual readiness, checkout, and network isolation."""
import json
import pathlib
import socket
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
K = ["kubectl", "--kubeconfig", str(ROOT / ".platform/kubeconfig"),
     "--context", "kind-devsecops-platform"]


def kubectl(*args):
    return subprocess.check_output(K + list(args), text=True)


def verify():
    nodes = json.loads(kubectl("get", "nodes", "-o", "json"))["items"]
    assert len(nodes) == 3, f"Expected 3 platform nodes, got {len(nodes)}"
    for node in nodes:
        assert any(c["type"] == "Ready" and c["status"] == "True"
                   for c in node["status"]["conditions"]), node["metadata"]["name"]
    print("PASS: all 3 platform nodes Ready", flush=True)
    for env in ("staging", "production"):
        ns = "boutique-" + env
        deps = json.loads(kubectl("-n", ns, "get", "deployments", "-o", "json"))["items"]
        assert len(deps) == 12, f"Missing deployments in {ns}"
        for dep in deps:
            desired = dep["spec"].get("replicas", 1)
            assert dep["status"].get("availableReplicas", 0) == desired, dep["metadata"]["name"]
        slices = json.loads(kubectl("-n", ns, "get", "endpointslices", "-o", "json"))["items"]
        ready_services = {s["metadata"]["labels"]["kubernetes.io/service-name"]
                          for s in slices if any(e.get("conditions", {}).get("ready")
                                                 for e in s.get("endpoints", []))}
        assert len(ready_services) == 11, f"Missing Service endpoints in {ns}: {ready_services}"
        # Let kubectl choose an unused local port, then read the bound port from its output.
        with tempfile.TemporaryFile(mode="w+t") as log:
            proc = subprocess.Popen(K + ["-n", ns, "port-forward", "--address", "127.0.0.1",
                                         "service/frontend", ":80"], stdout=log, stderr=log)
            try:
                for _ in range(100):
                    log.seek(0)
                    output = log.read()
                    lines = [line for line in output.splitlines() if line.startswith("Forwarding from 127.0.0.1:")]
                    if lines:
                        port = lines[0].split(":")[1].split()[0]
                        break
                    if proc.poll() is not None:
                        raise RuntimeError(output)
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Port-forward did not start: " + output)
                subprocess.run([sys.executable, str(ROOT / "scripts/smoke-test.py"),
                                "--url", f"http://127.0.0.1:{port}"], check=True)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        print(f"PASS: {ns} deployments, Service endpoints, and checkout", flush=True)
    code = '''
import socket
with socket.create_connection(("frontend", 80), timeout=5):
    print("PASS: allowed loadgenerator -> frontend")
for host, port in [("redis-cart", 6379), ("frontend.boutique-production.svc.cluster.local", 80)]:
    socket.getaddrinfo(host, port)  # A DNS failure must not masquerade as policy enforcement.
    try:
        s = socket.create_connection((host, port), timeout=3)
    except TimeoutError:
        print("PASS: policy denied", host)
    else:
        s.close()
        raise SystemExit("FAIL: forbidden connection succeeded: " + host)
'''
    print(kubectl("-n", "boutique-staging", "exec", "deployment/loadgenerator", "-c", "main",
                  "--", "python3", "-c", code), end="")


if __name__ == "__main__":
    verify()
