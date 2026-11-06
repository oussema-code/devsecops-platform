"""The OpenTofu plan guard must block deletions and replacements, and nothing else."""
import json
import pathlib
import subprocess
import sys
import unittest

GUARD = pathlib.Path(__file__).resolve().parents[1] / "scripts/plan-guard.py"


def run(plan):
    return subprocess.run([sys.executable, str(GUARD)], input=json.dumps(plan), text=True, capture_output=True)


def change(address, *actions):
    return {"address": address, "change": {"actions": list(actions)}}


class PlanGuardTests(unittest.TestCase):
    def test_allows_create_update_and_noop(self):
        result = run({"resource_changes": [change("aws_s3_bucket.input", "create"),
                                           change("aws_sqs_queue.work", "update"),
                                           change("aws_dynamodb_table.results", "no-op")]})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_blocks_delete(self):
        result = run({"resource_changes": [change("aws_dynamodb_table.results", "delete")]})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("aws_dynamodb_table.results", result.stderr)

    def test_blocks_replacement(self):
        for actions in (("delete", "create"), ("create", "delete")):
            with self.subTest(actions=actions):
                result = run({"resource_changes": [change("aws_sqs_queue.dead", *actions)]})
                self.assertNotEqual(result.returncode, 0)

    def test_rejects_errored_or_malformed_plan(self):
        for plan in ({"errored": True, "resource_changes": []}, {}):
            with self.subTest(plan=plan):
                self.assertNotEqual(run(plan).returncode, 0)


if __name__ == "__main__":
    unittest.main()
