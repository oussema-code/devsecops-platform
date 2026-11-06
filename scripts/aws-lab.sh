#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
cd "$PLATFORM_ROOT"
lab_dir="$PLATFORM_ROOT/infra/localstack"
tfstate_dir="$PLATFORM_STATE/tofu"
mkdir -p "$tfstate_dir"
tofu_bin="${TOFU_BIN:-$(command -v tofu || true)}"
tofu_bin="${tofu_bin:-$PLATFORM_STATE/tools/tofu}"
compose=(docker compose -f "$lab_dir/compose.yaml")
if [[ ! -e "$PLATFORM_STATE/localstack.env" ]]; then
  (umask 077; printf '%s\n' '# Set the LocalStack auth token here with your editor; never commit it.' 'LOCALSTACK_AUTH_TOKEN=' > "$PLATFORM_STATE/localstack.env")
fi
package_worker() {
  python3 - "$tfstate_dir/worker.zip" <<'PY'
from pathlib import Path
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], "w") as archive:
    archive.writestr(zipfile.ZipInfo("index.py", (2020, 1, 1, 0, 0, 0)), Path("infra/localstack/sample/index.py").read_bytes())
PY
}
case "${1:-}" in
  up)
    if ! grep -Eq '^LOCALSTACK_AUTH_TOKEN=.+$' "$PLATFORM_STATE/localstack.env"; then
      echo 'Set LOCALSTACK_AUTH_TOKEN in .platform/localstack.env locally before starting.' >&2; exit 1
    fi
    "${compose[@]}" up -d --wait --wait-timeout 240
    ;;
  validate|plan)
    package_worker
    "$tofu_bin" -chdir="$lab_dir" init -input=false
    "$tofu_bin" -chdir="$lab_dir" validate
    if [[ $1 == plan ]]; then
      "$tofu_bin" -chdir="$lab_dir" plan -input=false -out="$tfstate_dir/plan.tfplan"
      "$tofu_bin" -chdir="$lab_dir" show -json "$tfstate_dir/plan.tfplan" | python3 scripts/plan-guard.py
    fi
    ;;
  apply)
    "$tofu_bin" -chdir="$lab_dir" show -json "$tfstate_dir/plan.tfplan" | python3 scripts/plan-guard.py
    "$tofu_bin" -chdir="$lab_dir" apply -input=false "$tfstate_dir/plan.tfplan"
    rm -f "$tfstate_dir/plan.tfplan"  # A saved plan is single-use; always re-plan.
    ;;
  verify)
    # boto3 lives in LocalStack's own virtualenv, not the image's default python.
    "${compose[@]}" exec -T localstack sh -c 'for py in /opt/code/localstack/.venv/bin/python python3 python; do
      if "$py" -c "import boto3" 2>/dev/null; then exec "$py" /lab/verify.py; fi
    done; echo "No Python with boto3 found in the LocalStack container" >&2; exit 1'
    ;;
  down)
    # Stop the emulator but keep its persisted state volume and the OpenTofu state.
    "${compose[@]}" down
    ;;
  destroy)
    # Irreversible for the lab: removes emulated resources, state volume and local state.
    if [[ "${CONFIRM:-}" != boutique-aws ]]; then
      echo 'Refusing to destroy. Re-run with CONFIRM=boutique-aws to delete the lab state.' >&2; exit 1
    fi
    package_worker
    "$tofu_bin" -chdir="$lab_dir" destroy -input=false -auto-approve || true
    "${compose[@]}" down --volumes
    rm -f "$tfstate_dir"/terraform.tfstate* "$tfstate_dir/plan.tfplan"
    ;;
  *) echo "Usage: $0 {up|validate|plan|apply|verify|down|destroy}" >&2; exit 2 ;;
esac
