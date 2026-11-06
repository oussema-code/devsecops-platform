"""Reject destructive actions, including replacements, in a saved OpenTofu plan."""
import json
import sys

plan = json.load(sys.stdin)
if plan.get("errored") or "resource_changes" not in plan:
    sys.exit("Expected a valid OpenTofu plan with resource_changes")
deletes = [r["address"] for r in plan["resource_changes"] if "delete" in r["change"]["actions"]]
if deletes:
    sys.exit("Destructive plan blocked: " + ", ".join(deletes))
print("Plan contains no resource deletions")
