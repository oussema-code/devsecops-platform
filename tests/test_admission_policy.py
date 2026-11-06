"""Every image the overlays render must be admissible under the Enforce policy."""
import fnmatch
import pathlib
import subprocess
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]


def images(objects):
    for obj in objects:
        spec = obj.get("spec", {})
        pods = [spec.get("template", {}).get("spec", {})]
        if obj["kind"] == "AnalysisTemplate":
            pods = [m["provider"]["job"]["spec"]["template"]["spec"] for m in spec["metrics"] if "job" in m["provider"]]
        for pod in pods:
            for c in pod.get("initContainers", []) + pod.get("containers", []):
                yield c["image"]


class AdmissionPolicyTests(unittest.TestCase):
    def setUp(self):
        policy = yaml.safe_load((ROOT / "platform/security/image-signatures.yaml").read_text())
        self.spec = policy["spec"]
        rule = next(r for r in self.spec["rules"] if r["name"] == "allowed-image-sources")
        self.allowed = rule["validate"]["foreach"][0]["deny"]["conditions"]["all"][0]["value"]

    def test_enforced_and_signature_scoped_to_platform_images(self):
        self.assertEqual(self.spec["validationFailureAction"], "Enforce")
        verify = next(r for r in self.spec["rules"] if r["name"] == "verify-release-signature")["verifyImages"][0]
        self.assertEqual(verify["imageReferences"], ["ghcr.io/oussema-code/boutique-*"])
        self.assertTrue(verify["required"])
        self.assertTrue(all("@sha256:" in a for a in self.allowed))

    def test_rendered_images_are_admissible(self):
        for env in ("staging", "production"):
            rendered = subprocess.check_output(["kubectl", "kustomize", str(ROOT / "apps/online-boutique/overlays" / env)], text=True)
            for image in images(yaml.safe_load_all(rendered)):
                with self.subTest(env=env, image=image):
                    self.assertTrue(any(fnmatch.fnmatch(image, a) for a in self.allowed), image)

    def test_rejects_unpinned_or_foreign_images(self):
        for image in ("ghcr.io/oussema-code/boutique-frontend:latest", "redis:alpine", "nginx@sha256:" + "a" * 64,
                      "ghcr.io/someone-else/boutique-frontend@sha256:" + "a" * 64):
            self.assertFalse(any(fnmatch.fnmatch(image, a) for a in self.allowed), image)


if __name__ == "__main__":
    unittest.main()
