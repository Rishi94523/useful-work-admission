import unittest
from scripts.check_publication import check

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

if __name__=='__main__':unittest.main()
