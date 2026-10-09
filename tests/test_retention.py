import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / "oneforall"))
from retention import prune_doctrad, REQUIRED

class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pending = self.root / "pending"
        self.pending.mkdir()
    def snapshot(self, name):
        path = self.root / "doctrad" / name
        path.mkdir(parents=True)
        for name in REQUIRED: (path / name).write_text("data")
        (path / "record.json").write_text(json.dumps({"sha": "a" * 40}))
        (path / "SHA256.json").write_text(json.dumps({name: "a" * 64 for name in REQUIRED}))
        return path
    def test_two_newest_and_latest_previous_day(self):
        old = self.snapshot("20261008T100000-aaaaaa")
        keep_day = self.snapshot("20261008T200000-bbbbbb")
        remove = self.snapshot("20261009T100000-cccccc")
        first = self.snapshot("20261009T200000-dddddd")
        second = self.snapshot("20261009T210000-eeeeee")
        removed = prune_doctrad(self.root, self.pending)
        self.assertEqual(set(removed), {old.name, remove.name})
        self.assertTrue(all(p.exists() for p in (keep_day, first, second)))
    def test_pending_and_incomplete_preserved(self):
        protected = self.snapshot("20261009T100000-aaaaaa")
        incomplete = self.snapshot("20261009T110000-bbbbbb")
        (incomplete / "SHA256.json").unlink()
        self.snapshot("20261009T200000-cccccc")
        self.snapshot("20261009T210000-dddddd")
        (self.pending / "doctrad.json").write_text(json.dumps({"snapshot": str(protected)}))
        self.assertEqual(prune_doctrad(self.root, self.pending), [])
        self.assertTrue(incomplete.exists())
    def test_invalid_pending_disables_cleanup(self):
        for hour in (10, 11, 12): self.snapshot(f"20261009T{hour}0000-aaaaaa")
        (self.pending / "doctrad.json").write_text("invalid")
        self.assertEqual(prune_doctrad(self.root, self.pending), [])
