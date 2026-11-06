"""Security and connectivity contracts for rendered application manifests."""
import copy
import pathlib
import re
import subprocess
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]


def validate(objects):
    deployments = {x["metadata"]["name"]: x for x in objects if x["kind"] == "Deployment"}
    services = {x["metadata"]["name"]: x for x in objects if x["kind"] == "Service"}
    policies = {x["metadata"]["name"]: x["spec"] for x in objects if x["kind"] == "NetworkPolicy"}
    assert len(deployments) == 12
    assert len(services) == 12  # 11 application Services plus the frontend canary Service
    assert policies["default-deny"]["podSelector"] == {}
    assert set(policies["default-deny"]["policyTypes"]) == {"Ingress", "Egress"}
    assert not policies["default-deny"].get("ingress")
    assert not policies["default-deny"].get("egress")
    namespace = next(x for x in objects if x["kind"] == "Namespace")
    assert namespace["metadata"]["labels"]["pod-security.kubernetes.io/enforce"] == "restricted"
    quota = next(x for x in objects if x["kind"] == "ResourceQuota")
    assert set(quota["spec"]["hard"]) >= {"requests.cpu", "requests.memory", "limits.cpu", "limits.memory", "pods"}
    for name, dep in deployments.items():
        pod = dep["spec"]["template"]["spec"]
        assert pod["automountServiceAccountToken"] is False
        assert pod["securityContext"]["runAsNonRoot"] is True
        assert pod["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
        for c in pod["containers"] + pod.get("initContainers", []):
            assert re.search(r"@sha256:[0-9a-f]{64}$", c["image"]), c["image"]
            assert c["securityContext"]["allowPrivilegeEscalation"] is False
            assert "ALL" in c["securityContext"]["capabilities"]["drop"]
            assert set(c["resources"]["requests"]) >= {"cpu", "memory"}
            assert set(c["resources"]["limits"]) >= {"cpu", "memory"}
        for c in pod["containers"]:
            for env in c.get("env", []):
                if not env["name"].endswith("_ADDR") or ":" not in env.get("value", ""):
                    continue
                dest, port = env["value"].rsplit(":", 1)
                if env["name"] == "COLLECTOR_SERVICE_ADDR":
                    assert dest == "otel.monitoring.svc" and port == "4317"
                    rule = policies["export-traces"]["egress"][0]
                    assert rule["to"][0]["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"] == "monitoring"
                    assert rule["to"][0]["podSelector"]["matchLabels"]["app.kubernetes.io/instance"] == "otel"
                    assert {"port": 4317, "protocol": "TCP"} in rule["ports"]
                    continue
                if dest == "shoppingassistantservice":
                    continue  # Upstream optional feature is disabled in this release.
                assert dest in services, (name, dest)
                svc = services[dest]
                target = next(p["targetPort"] for p in svc["spec"]["ports"] if p["port"] == int(port))
                for policy, direction, peers, app in [(policies[name], "egress", "to", dest),
                                                       (policies[dest], "ingress", "from", name)]:
                    assert any(any(p.get("podSelector", {}).get("matchLabels", {}).get("app") == app
                                   for p in rule.get(peers, [])) and
                               {"protocol": "TCP", "port": target} in rule.get("ports", [])
                               for rule in policy.get(direction, [])), (name, dest, direction, target)
    for name, service in services.items():
        assert service["spec"].get("type", "ClusterIP") == "ClusterIP"
        owner = "frontend" if name == "frontend-canary" else name
        assert service["spec"]["selector"] == deployments[owner]["spec"]["template"]["metadata"]["labels"]
    for policy in policies.values():
        for direction, peers in [("ingress", "from"), ("egress", "to")]:
            for rule in policy.get(direction, []):
                assert rule.get(peers) and rule.get("ports"), "Unrestricted network rule"


def validate_canary(objects):
    """The frontend Rollout must gate promotion on a checkout against the candidate Pods."""
    by_kind = lambda kind: {x["metadata"]["name"]: x for x in objects if x["kind"] == kind}
    rollout = by_kind("Rollout")["frontend"]
    deployment = by_kind("Deployment")["frontend"]
    assert deployment["spec"]["replicas"] == 0, "Deployment must not run Pods beside the Rollout"
    assert rollout["spec"]["workloadRef"] == {"apiVersion": "apps/v1", "kind": "Deployment",
                                              "name": "frontend", "scaleDown": "never"}
    assert rollout["spec"]["selector"] == deployment["spec"]["selector"]
    canary = rollout["spec"]["strategy"]["canary"]
    assert canary["maxUnavailable"] == 0
    steps = canary["steps"]
    weights = [s["setWeight"] for s in steps if "setWeight" in s]
    assert weights[-1] == 100 and all(w < 100 for w in weights[:-1]) and len(weights) >= 2
    analysis_index = next(i for i, s in enumerate(steps) if "analysis" in s)
    assert analysis_index < len(steps) - 1, "Analysis must run before full promotion"
    analysis = steps[analysis_index]["analysis"]
    service = by_kind("Service")[canary["canaryService"]]
    template = by_kind("AnalysisTemplate")[analysis["templates"][0]["templateName"]]
    url = next(a["value"] for a in analysis["args"] if a["name"] == "canary-url")
    assert url == "http://" + service["metadata"]["name"], "Analysis must target only the canary Pods"
    metric = template["spec"]["metrics"][0]
    assert metric["failureLimit"] == 0
    job = metric["provider"]["job"]["spec"]
    assert job["backoffLimit"] == 0 and job["activeDeadlineSeconds"] <= 300
    pod = job["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    for c in pod["containers"]:
        assert re.search(r"@sha256:[0-9a-f]{64}$", c["image"]), c["image"]
        assert c["securityContext"]["allowPrivilegeEscalation"] is False
        assert c["securityContext"]["readOnlyRootFilesystem"] is True
        assert "ALL" in c["securityContext"]["capabilities"]["drop"]
        assert set(c["resources"]["limits"]) >= {"cpu", "memory"}
    configmaps = by_kind("ConfigMap")
    for volume in pod["volumes"]:
        assert volume["configMap"]["name"] in configmaps
    check_label = job["template"]["metadata"]["labels"]["app"]
    target_port = service["spec"]["ports"][0]["targetPort"]
    policies = [x["spec"] for x in objects if x["kind"] == "NetworkPolicy"]
    def allows(selected, direction, peers, peer_app):
        return any(p["podSelector"].get("matchLabels", {}).get("app") == selected and
                   any(any(x.get("podSelector", {}).get("matchLabels", {}).get("app") == peer_app for x in r.get(peers, []))
                       and {"protocol": "TCP", "port": target_port} in r.get("ports", [])
                       for r in p.get(direction, []))
                   for p in policies)
    assert allows(check_label, "egress", "to", "frontend"), "Canary check egress blocked"
    assert allows("frontend", "ingress", "from", check_label), "Frontend ingress blocks canary check"


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rendered = {}
        for env in ("staging", "production"):
            output = subprocess.check_output(["kubectl", "kustomize", str(ROOT / "apps/online-boutique/overlays" / env)], text=True)
            cls.rendered[env] = list(yaml.safe_load_all(output))

    def test_environments(self):
        for env, objects in self.rendered.items():
            with self.subTest(env=env):
                validate(objects)
                for x in objects:
                    if x["kind"] != "Namespace":
                        self.assertEqual(x["metadata"]["namespace"], "boutique-" + env)

    def test_redis_uses_protected_claim_and_one_writer(self):
        for objects in self.rendered.values():
            deployment = next(d for d in objects if d["kind"] == "Deployment" and d["metadata"]["name"] == "redis-cart")
            volumes = deployment["spec"]["template"]["spec"]["volumes"]
            claim = next(d for d in objects if d["kind"] == "PersistentVolumeClaim")
            self.assertEqual(volumes, [{"name": "redis-data", "persistentVolumeClaim": {"claimName": claim["metadata"]["name"]}}])
            self.assertEqual(deployment["spec"]["strategy"]["type"], "Recreate")
            self.assertEqual(deployment["spec"]["replicas"], 1)
            self.assertIn("Prune=false", claim["metadata"]["annotations"]["argocd.argoproj.io/sync-options"])

    def test_rejects_mutable_image(self):
        objects = copy.deepcopy(self.rendered["staging"])
        next(x for x in objects if x["kind"] == "Deployment")["spec"]["template"]["spec"]["containers"][0]["image"] = "redis:latest"
        with self.assertRaises(AssertionError):
            validate(objects)

    def test_rejects_broken_service_connection(self):
        objects = copy.deepcopy(self.rendered["staging"])
        next(x for x in objects if x["kind"] == "NetworkPolicy" and x["metadata"]["name"] == "cartservice")["spec"]["egress"] = []
        with self.assertRaises(AssertionError):
            validate(objects)

    def test_rejects_unrestricted_egress(self):
        objects = copy.deepcopy(self.rendered["staging"])
        next(x for x in objects if x["kind"] == "NetworkPolicy" and x["metadata"]["name"] == "frontend")["spec"]["egress"].append({})
        with self.assertRaises(AssertionError):
            validate(objects)

    def test_production_replica_and_disruption_budget_contract(self):
        objects = self.rendered["production"]
        budgets = {x["metadata"]["name"] for x in objects if x["kind"] == "PodDisruptionBudget"}
        for d in (x for x in objects if x["kind"] == "Deployment"):
            name = d["metadata"]["name"]
            expected = 0 if name in ("loadgenerator", "frontend") else 1 if name == "redis-cart" else 2
            self.assertEqual(d["spec"]["replicas"], expected)
            if expected == 2:
                self.assertIn(name, budgets)
        rollout = next(x for x in objects if x["kind"] == "Rollout")
        self.assertEqual(rollout["spec"]["replicas"], 2)
        self.assertIn("frontend", budgets)

    def test_frontend_canary_contract(self):
        for env, objects in self.rendered.items():
            with self.subTest(env=env):
                validate_canary(objects)

    def test_rejects_canary_without_analysis(self):
        objects = copy.deepcopy(self.rendered["production"])
        rollout = next(x for x in objects if x["kind"] == "Rollout")
        rollout["spec"]["strategy"]["canary"]["steps"] = [{"setWeight": 100}]
        with self.assertRaises(AssertionError):
            validate_canary(objects)

    def test_rejects_canary_check_blocked_by_policy(self):
        objects = copy.deepcopy(self.rendered["staging"])
        objects = [x for x in objects if not (x["kind"] == "NetworkPolicy" and x["metadata"]["name"] == "frontend-canary-check")]
        with self.assertRaises(AssertionError):
            validate_canary(objects)

    def test_canary_check_matches_verify_journey(self):
        self.assertEqual((ROOT / "scripts/smoke-test.py").read_bytes(),
                         (ROOT / "apps/online-boutique/base/storefront-check.py").read_bytes())


if __name__ == "__main__":
    unittest.main()
