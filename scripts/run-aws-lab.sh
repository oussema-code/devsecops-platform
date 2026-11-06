#!/usr/bin/env bash
# Runs the full AWS lab sequence and records everything in .platform/aws-lab-run.log
# so the assistant can read the result directly. Safe to re-run.
set -uo pipefail
cd "$(dirname -- "${BASH_SOURCE[0]}")/.."
log=.platform/aws-lab-run.log
exec > >(tee "$log") 2>&1
step() { echo; echo "===== $* ====="; }
fail() { echo; echo "RESULT: FAILED at: $1"; exit 1; }
tofu=.platform/tools/tofu
step "DNS for S3 Control host"
getent hosts 000000000000.localhost.localstack.cloud || fail "DNS: 000000000000.localhost.localstack.cloud does not resolve"
step "LocalStack up"
bash scripts/aws-lab.sh up || fail "aws-lab up"
curl -fsS http://127.0.0.1:14566/_localstack/info | python3 -c 'import json,sys; d=json.load(sys.stdin); print("edition:", d.get("edition"), "license:", d.get("is_license_activated"))' || fail "LocalStack info"
step "Clear taint from the earlier failed apply (no-op if already clear)"
if "$tofu" -chdir=infra/localstack state show aws_s3_bucket.input 2>/dev/null | grep -q tainted; then
  "$tofu" -chdir=infra/localstack untaint aws_s3_bucket.input || fail "untaint"
else
  "$tofu" -chdir=infra/localstack untaint aws_s3_bucket.input 2>/dev/null || echo "bucket not tainted"
fi
step "Plan (guarded)"
bash scripts/aws-lab.sh plan || fail "plan"
step "Apply"
bash scripts/aws-lab.sh apply || fail "apply"
step "Verify"
bash scripts/aws-lab.sh verify || fail "verify"
echo; echo "RESULT: ALL PASSED"
