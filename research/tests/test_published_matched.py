import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import run_published_matched as matched

class AnalysisTests(unittest.TestCase):
 def test_missing_state_excludes_whole_compound(self):
  target={'target':'test','compounds':[{'id':'active','states':2,'label':'active'},{'id':'decoy','states':1,'label':'decoy'}]}
  rows=[{'target':'test','compound_id':'active','label':'active','seed':1,'ok':True,'normal':{'score':-10},'medium':{'score':-10}}, {'target':'test','compound_id':'decoy','label':'decoy','seed':1,'ok':True,'normal':{'score':-2},'medium':{'score':-2}}]
  with tempfile.TemporaryDirectory() as folder,patch.object(matched,'OUT',Path(folder)):
   matched.analyze(rows,[target],[1]);r=json.loads((Path(folder)/'comparison.json').read_text())[0]
  self.assertFalse(r['complete']);self.assertEqual(r['per_seed'][0]['complete_compounds'],1);self.assertIsNone(r['per_seed'][0]['normal']['auc'])

 def test_identical_complete_scores_have_zero_paired_delta(self):
  target={'target':'test','compounds':[{'id':str(i),'states':1,'label':'active' if i<32 else 'decoy'} for i in range(96)]};rows=[]
  for seed in [1,2,3]:
   for i in range(96):
    scores={'score':float(i),'evals':100,'search_ms':2}
    rows.append({'target':'test','compound_id':str(i),'label':'active' if i<32 else 'decoy','seed':seed,'ok':True,'normal':scores,'medium':scores})
  with tempfile.TemporaryDirectory() as folder,patch.object(matched,'OUT',Path(folder)):
   matched.analyze(rows,[target],[1,2,3]);r=json.loads((Path(folder)/'comparison.json').read_text())[0]
  self.assertTrue(r['complete']);self.assertEqual(r['paired95'],[0.,0.]);self.assertTrue(r['noninferiority_demonstrated']);self.assertEqual(r['evaluation_ratio'],1.)

if __name__=='__main__':unittest.main()
