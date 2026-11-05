import importlib.util
import pathlib
import unittest

path = pathlib.Path(__file__).resolve().parents[1] / "scripts/stage-release.py"
spec = importlib.util.spec_from_file_location("release", path)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def records(self):
        return [{"service": name, "image": f"ghcr.io/oussema-code/boutique-{name}@sha256:" + "a" * 64,
                 "source_commit": "b" * 40, "platform_commit": "c" * 40} for name in sorted(release.SERVICES)]

    def test_complete_release(self):
        self.assertEqual(len(release.validate_release(self.records(), "b" * 40)["images"]), 11)

    def test_partial_release_rejected(self):
        with self.assertRaises(ValueError):
            release.validate_release(self.records()[:-1], "b" * 40)

    def test_wrong_registry_or_service_rejected(self):
        records = self.records()
        records[0]["image"] = records[0]["image"].replace("oussema-code", "another-owner")
        with self.assertRaises(ValueError):
            release.validate_release(records, "b" * 40)

    def test_mixed_or_stale_release_rejected(self):
        for field in ("source_commit", "platform_commit"):
            records = self.records()
            records[0][field] = "d" * 40
            with self.subTest(field=field), self.assertRaises(ValueError):
                release.validate_release(records, "b" * 40)
