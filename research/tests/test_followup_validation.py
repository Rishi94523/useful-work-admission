"""Checks for interpretation-sensitive parts of the follow-up experiments."""
import json
from pathlib import Path
import unittest
import tempfile

from scripts.validate_cost_aware_admission import costs
from scripts.portable_dense_benchmark import check_manifest


class FollowupValidationTests(unittest.TestCase):
    def test_equal_cost_selection_cannot_invent_discount(self):
        rows=[dict(target=t,id=str(j),seed=1,wall_ms=10.)
              for t in ('a','b') for j in range(4) for _ in range(3)]
        result=costs(rows)
        for r in result['rows']:
            if r['strategy']!='predicted_abstain_half' or r['probe_ms']==0:
                self.assertAlmostEqual(r['expected_cost_ratio'],1.)
            else:self.assertGreater(r['expected_cost_ratio'],1.)
        self.assertEqual(result['development_jobs'],4)
        self.assertEqual(result['heldout_jobs'],4)

    def test_portable_manifest_rejects_tampering_before_loading_dll(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p=root/'dense_check.dll';p.write_bytes(b'reviewed fixture')
            m={'files':{'dense_check.dll':hashlib.sha256(p.read_bytes()).hexdigest()}}
            (root/'manifest.json').write_text(json.dumps(m));check_manifest(root)
            p.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'checksum'):check_manifest(root)

    def test_portable_manifest_rejects_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'manifest.json').write_text(json.dumps({'files':{'../outside.dll':'0'*64}}))
            with self.assertRaisesRegex(ValueError,'path'):check_manifest(root)


if __name__=='__main__':unittest.main()
