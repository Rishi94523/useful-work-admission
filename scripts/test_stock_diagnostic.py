"""Checks for ranking ties, immutable selection and redocking coordinates."""
import tempfile,unittest
from pathlib import Path
from run_stock_diagnostic import ROOT,freeze,metrics,quality

class DiagnosticTests(unittest.TestCase):
 def test_ties_do_not_depend_on_completion_order(self):
  rows=[{'ok':True,'label':'active' if i<8 else 'decoy','score':-5} for i in range(24)]
  self.assertEqual(metrics(rows),metrics(rows[::-1]))
  self.assertAlmostEqual(metrics(rows)['auc'],.5)
  self.assertAlmostEqual(metrics(rows)['ef10'],1)
 def test_perfect_ranking(self):
  rows=[{'ok':True,'label':'active','score':-9}]*8+[{'ok':True,'label':'decoy','score':-1}]*16
  self.assertEqual(metrics(rows)['auc'],1)
  self.assertEqual(metrics(rows)['ef10'],3)
 def test_immutable_selection(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'selection.json';freeze(p,{'configuration':'a'});freeze(p,{'configuration':'a'})
   with self.assertRaises(ValueError):freeze(p,{'configuration':'b'})
 def test_crystal_atom_mapping_without_alignment(self):
  p=ROOT/'tmp/vina-stock-diagnostic/dyr/crystal.pdbqt'
  if not p.exists():self.skipTest('Scientific fixture not downloaded')
  result=quality(p,p.with_suffix('.sdf'),'REMARK VINA RESULT: -1 0 0\n'+p.read_text())
  self.assertLess(result['top_rmsd_A'],.002)
if __name__=='__main__':unittest.main()
