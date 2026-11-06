"""Back up live Redis and restore into a newly created, isolated claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment", choices=["staging", "production"])
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser("backup")
    backup.add_argument("file", type=Path)
    restore = sub.add_parser("restore")
    restore.add_argument("file", type=Path)
    restore.add_argument("claim", help="Name for a new 1 GiB claim. Existing claims are refused.")
    args = parser.parse_args()
    os.umask(0o077)
    ns = "boutique-" + args.environment
    k = ["kubectl", "--kubeconfig", str(ROOT / ".platform/kubeconfig"), "--context",
         "kind-devsecops-platform", "-n", ns]
    path = args.file.resolve()
    checksum = path.with_name(path.name + ".sha256")
    if args.command == "backup":
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() or checksum.exists():
            parser.error("Choose a new backup filename")
        pod = subprocess.check_output(k + ["get", "pods", "-l", "app=redis-cart",
                                     "-o", "jsonpath={.items[0].metadata.name}"], text=True)
        subprocess.run(k + ["exec", pod, "--", "redis-cli", "-e", "SAVE"], check=True)
        with tempfile.NamedTemporaryFile(dir=path.parent) as tmp:
            subprocess.run(k + ["exec", pod, "--", "cat", "/data/dump.rdb"], stdout=tmp, check=True)
            tmp.flush()
            tmp.seek(0)
            if tmp.read(5) != b"REDIS":
                raise ValueError("Invalid RDB stream")
            tmp.seek(0)
            digest = hashlib.file_digest(tmp, "sha256").hexdigest()
            os.link(tmp.name, path)
        checksum.write_text(digest + "\n")
        print(f"Saved {path} ({path.stat().st_size} bytes)")
        return

    # Validate before provisioning storage. Keep the claim on failure for inspection.
    with path.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != checksum.read_text().strip():
            raise ValueError("RDB checksum mismatch")
    deployment = json.loads(subprocess.check_output(k + ["get", "deployment", "redis-cart", "-o", "json"]))
    image = deployment["spec"]["template"]["spec"]["containers"][0]["image"]
    claim = {"apiVersion": "v1", "kind": "PersistentVolumeClaim", "metadata": {"name": args.claim},
             "spec": {"storageClassName": "standard", "accessModes": ["ReadWriteOnce"],
                      "resources": {"requests": {"storage": "1Gi"}}}}
    subprocess.run(k + ["create", "-f", "-"], input=json.dumps(claim).encode(), check=True)
    helper = "rdb-restore-" + uuid.uuid4().hex[:10]
    pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": helper},
           "spec": {"restartPolicy": "Never", "activeDeadlineSeconds": 600,
                    "automountServiceAccountToken": False,
                    "securityContext": {"runAsNonRoot": True, "runAsUser": 1000, "fsGroup": 1000,
                                        "seccompProfile": {"type": "RuntimeDefault"}},
                    "volumes": [{"name": "data", "persistentVolumeClaim": {"claimName": args.claim}}],
                    "containers": [{"name": "restore", "image": image, "command": ["sleep", "600"],
                                    "volumeMounts": [{"name": "data", "mountPath": "/data"}],
                                    "securityContext": {"allowPrivilegeEscalation": False,
                                                        "capabilities": {"drop": ["ALL"]}},
                                    "resources": {"requests": {"cpu": "20m", "memory": "32Mi"},
                                                  "limits": {"cpu": "250m", "memory": "256Mi"}}}]}}
    subprocess.run(k + ["create", "-f", "-"], input=json.dumps(pod).encode(), check=True)
    try:
        subprocess.run(k + ["wait", "--for=condition=Ready", "pod/" + helper, "--timeout=180s"], check=True)
        with path.open("rb") as source:
            subprocess.run(k + ["exec", "-i", helper, "--", "sh", "-ec",
                           "cat > /data/incoming.rdb; redis-check-rdb /data/incoming.rdb; "
                           "mv /data/incoming.rdb /data/dump.rdb"], stdin=source, check=True)
        subprocess.run(k + ["exec", helper, "--", "sh", "-ec",
                       "redis-server --bind 127.0.0.1 --port 6380 --dir /data --save '' "
                       "--daemonize yes --logfile /data/restore.log --pidfile /data/restore.pid; "
                       "redis-cli -p 6380 -e INFO keyspace; redis-cli -p 6380 -e SHUTDOWN NOSAVE"], check=True)
    finally:
        subprocess.run(k + ["delete", "pod", helper, "--ignore-not-found", "--grace-period=1"], check=True)
    print(f"Verified restore into {ns}/{args.claim}. Select it in Git to cut over.")


if __name__ == "__main__":
    main()
