"""Exercise the production frontend canary: a broken candidate must abort, a good one must promote.

Production is used because it does not self-heal: the drill's temporary Deployment edits
would otherwise be reverted by Argo CD mid-experiment. Every edit is undone before exit,
so production returns to the Git revision; no explicit sync is required afterwards.
"""
import importlib.util
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify", ROOT / "scripts/verify-platform.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)
NS = "boutique-production"
kubectl = lambda *a: verify.kubectl("-n", NS, *a)
ENV = "PRODUCT_CATALOG_SERVICE_ADDR"


def rollout():
    return json.loads(kubectl("get", "rollout", "frontend", "-o", "json"))


def wait(description, check, seconds=420):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        state = rollout()
        if check(state):
            print("PASS:", description, flush=True)
            return state
        time.sleep(5)
    raise SystemExit(f"FAIL: timed out waiting for {description}: {state.get('status')}")


def patch_env(value):
    patch = {"spec": {"template": {"spec": {"containers": [{"name": "server", "env": [{"name": ENV, "value": value}]}]}}}}
    kubectl("patch", "deployment", "frontend", "--type=strategic", "-p", json.dumps(patch))


def patch_annotation(value):
    patch = {"spec": {"template": {"metadata": {"annotations": {"platform.dev/canary-drill": value}}}}}
    kubectl("patch", "deployment", "frontend", "--type=merge", "-p", json.dumps(patch))


def latest_analysis():
    runs = json.loads(kubectl("get", "analysisruns", "-o", "json"))["items"]
    return max(runs, key=lambda r: r["metadata"]["creationTimestamp"]) if runs else None


def healthy(state):
    status = state.get("status", {})
    return (status.get("phase") == "Healthy" and not status.get("abort")
            and status.get("availableReplicas") == state["spec"]["replicas"])


def main():
    start = wait("production Rollout Healthy before the drill", healthy, 60)
    stable = start["status"]["stableRS"]
    deployment = json.loads(kubectl("get", "deployment", "frontend", "-o", "json"))
    container = next(c for c in deployment["spec"]["template"]["spec"]["containers"] if c["name"] == "server")
    original = next(e["value"] for e in container["env"] if e["name"] == ENV)
    try:
        print("Drill 1: candidate that cannot reach the product catalog", flush=True)
        patch_env("productcatalogservice:1")
        aborted = wait("broken candidate aborted by checkout analysis",
                       lambda s: s.get("status", {}).get("abort") is True)
        assert aborted["status"]["stableRS"] == stable, "Stable ReplicaSet changed during a failed canary"
        run = latest_analysis()
        assert run and run["status"]["phase"] in ("Failed", "Error"), run and run["status"]
        print("PASS: AnalysisRun", run["metadata"]["name"], run["status"]["phase"], flush=True)
        wait("aborted canary scaled down", lambda s: s["status"].get("availableReplicas") == s["spec"]["replicas"]
             and s["status"].get("updatedReplicas", 0) == 0, 180)
        verify.checkout(NS)
        print("PASS: storefront checkout still served by stable Pods after abort", flush=True)
    finally:
        patch_env(original)
    wait("reverting the template returns to the stable ReplicaSet", lambda s: healthy(s) and s["status"]["stableRS"] == stable)

    print("Drill 2: harmless candidate (Pod template annotation only)", flush=True)
    patch_annotation(str(int(time.time())))
    try:
        promoted = wait("good candidate promoted after passing analysis",
                        lambda s: healthy(s) and s["status"]["stableRS"] != stable)
        run = latest_analysis()
        assert run and run["status"]["phase"] == "Successful", run and run["status"]
        print("PASS: AnalysisRun", run["metadata"]["name"], "Successful;", "new stable", promoted["status"]["stableRS"], flush=True)
        verify.checkout(NS)
    finally:
        # null removes the annotation, returning the template to the Git definition.
        kubectl("patch", "deployment", "frontend", "--type=merge", "-p",
                json.dumps({"spec": {"template": {"metadata": {"annotations": {"platform.dev/canary-drill": None}}}}}))
    wait("Git-defined template restored through a second passing canary", healthy)
    print("Drill complete. Production frontend matches Git again.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.output or str(error))
