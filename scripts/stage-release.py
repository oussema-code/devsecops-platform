"""Validate a complete CI release and update staging's immutable image references."""
import argparse
import json
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVICES = {"adservice", "cartservice", "checkoutservice", "currencyservice", "emailservice",
            "frontend", "loadgenerator", "paymentservice", "productcatalogservice",
            "recommendationservice", "shippingservice"}


def validate_release(records, expected_source):
    images = {}
    revisions = set()
    for record in records:
        name = record["service"]
        if name not in SERVICES or name in images:
            raise ValueError("Unknown or duplicate service: " + name)
        if record["source_commit"] != expected_source:
            raise ValueError("Release source differs from upstream.lock.json")
        image = record["image"]
        if not re.fullmatch(r"ghcr\.io/oussema-code/boutique-" + re.escape(name) + r"@sha256:[0-9a-f]{64}", image):
            raise ValueError("Unexpected registry, package or digest: " + image)
        if not re.fullmatch(r"[0-9a-f]{40}", record["platform_commit"]):
            raise ValueError("Invalid build configuration revision")
        revisions.add(record["platform_commit"])
        images[name] = image
    if images.keys() != SERVICES or len(revisions) != 1:
        raise ValueError("Release must contain all 11 services from one build configuration")
    return {"source_commit": expected_source, "platform_commit": revisions.pop(), "images": dict(sorted(images.items()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", type=pathlib.Path)
    args = parser.parse_args()
    source = json.loads((ROOT / "upstream.lock.json").read_text())["commit"]
    release = validate_release([json.loads(p.read_text()) for p in args.artifacts.glob("release-*.json")], source)
    overlay = ROOT / "apps/online-boutique/overlays/staging"
    kustomization = yaml.safe_load((overlay / "kustomization.yaml").read_text())
    kustomization["images"] = []
    for service, image in release["images"].items():
        name, digest = image.split("@")
        kustomization["images"].append({"name": "us-central1-docker.pkg.dev/online-boutique-ci/microservices-demo/" + service,
                                      "newName": name, "digest": digest})
    (overlay / "kustomization.yaml").write_text(yaml.safe_dump(kustomization, sort_keys=False))
    (overlay / "release.json").write_text(json.dumps(release, indent=2) + "\n")


if __name__ == "__main__":
    main()
