import importlib.util, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_version_bump.py"

spec = importlib.util.spec_from_file_location("check_version_bump", SCRIPT)
cvb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cvb)

PLUGIN = '{"name": "flow", "version": "%s"}'
MARKET = ('{"name": "flow", "metadata": {"version": "%s"},'
          ' "plugins": [{"name": "flow", "version": "%s"}]}')


class TestShippedManifests(unittest.TestCase):
    """The versions this repo actually ships must agree with each other."""
    def test_consistent(self):
        found = cvb.versions(*cvb.read_tree())
        self.assertEqual(len(set(found.values())), 1, found)
        self.assertEqual(len(found), 3, found)  # plugin + metadata + one entry


class TestConsistency(unittest.TestCase):
    def check(self, plugin, metadata, entry):
        return cvb.check_consistent(
            cvb.versions(PLUGIN % plugin, MARKET % (metadata, entry)), "test")

    def test_all_equal_ok(self):
        self.assertEqual(self.check("1.2.3", "1.2.3", "1.2.3"), (1, 2, 3))

    def test_metadata_drift_rejected(self):
        with self.assertRaises(SystemExit):
            self.check("0.2.0", "0.1.0", "0.2.0")

    def test_plugin_entry_drift_rejected(self):
        with self.assertRaises(SystemExit):
            self.check("0.2.0", "0.2.0", "0.1.0")

    def test_non_semver_rejected(self):
        with self.assertRaises(SystemExit):
            self.check("v1.2", "v1.2", "v1.2")


class TestOrdering(unittest.TestCase):
    def test_patch_minor_major_all_count_as_bumps(self):
        for base, head in [("0.2.0", "0.2.1"), ("0.2.0", "0.3.0"),
                           ("0.2.9", "1.0.0"), ("0.9.0", "0.10.0")]:
            self.assertLess(cvb.parse(base, "b"), cvb.parse(head, "h"))

    def test_unchanged_and_downgrade_are_not_bumps(self):
        self.assertFalse(cvb.parse("0.3.0", "h") > cvb.parse("0.3.0", "b"))
        self.assertFalse(cvb.parse("0.2.0", "h") > cvb.parse("0.3.0", "b"))


if __name__ == "__main__":
    unittest.main()
