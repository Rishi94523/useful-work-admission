import hashlib,unittest
from scripts.check_publication import check,reviewed_archives

class PublicationGuardTests(unittest.TestCase):
 def test_private_paths_and_reports_fail(self):
  for path in ['patent/filing.pdf','docs/research/status.md','docs/evaluation/result.json','local-research/results.json','.env','image.png']:
   self.assertTrue(check(path,b'ordinary content'))
 def test_identity_numbers_are_detected_without_exposing_values(self):
  number=('ABCDE'+'1234'+'F').encode()
  self.assertIn('possible-pan',check('benchmarks/settings.json',number))
  self.assertIn('possible-aadhaar',check('settings.json',b'2345'+b' '+b'6789'+b' '+b'0123'))
 def test_code_and_small_protocol_are_allowed(self):
  self.assertEqual(check('research/policy.py',b'print(1)'),[])
  self.assertEqual(check('benchmarks/protocol.json',b'{"seed":104729}'),[])
  self.assertEqual(check('README.md',b'Public reproducibility instructions'),[])
 def test_archive_review_is_bound_to_path_and_hash(self):
  payload=b'reviewed test artifact';commit='a'*40;digest=hashlib.sha256(payload).hexdigest()
  manifest={'commit':commit,'code_zip':{'file':'useful-work-admission-code-aaaaaaa.zip','sha256':digest},
            'data_zip':{'file':'useful-work-admission-results-aaaaaaa.zip','sha256':digest}}
  reviewed=reviewed_archives(manifest);path='releases/zenodo/'+manifest['code_zip']['file']
  self.assertEqual(check(path,payload,reviewed),[])
  self.assertTrue(check(path,payload+b'changed',reviewed))
  self.assertTrue(check('unreviewed.zip',payload,reviewed))
  self.assertTrue(check(path,payload))
 def test_archive_review_rejects_path_traversal(self):
  with self.assertRaises(ValueError):
   reviewed_archives({'commit':'a'*40,'code_zip':{'file':'../unexpected.zip','sha256':'0'*64}})

if __name__=='__main__':unittest.main()
