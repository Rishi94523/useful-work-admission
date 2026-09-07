"""Security boundaries of the research pose envelope; downloaded fixture required."""
import math
import unittest
from research.docking_pilot import CACHE,CASES,case_spec
from research.docking_contract import PoseContract,check_candidate

class NeverScorer:
    def request(self,*args,**kwargs):raise AssertionError('Malformed envelope reached expensive scorer')

@unittest.skipUnless((CACHE/'runs/2P16_e1_cap1000_seed104729.pdbqt').exists(),'Run docking pilot to obtain pinned public fixture')
class DockingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract=PoseContract(case_spec(CASES[0]))
        cls.raw=(CACHE/'runs/2P16_e1_cap1000_seed104729.pdbqt').read_text()
    def test_valid_pose_reconstructs_trusted_chemistry(self):
        canonical,xyz,digest=self.contract.validate(self.raw)
        self.assertNotIn('REMARK VINA RESULT',canonical)
        self.assertEqual(len(xyz),len(self.contract.ref_atoms))
        self.assertEqual(len(digest),64)
    def test_nonfinite_claim_rejected_without_score(self):
        for score in [math.nan,math.inf,-math.inf,True,'-5']:
            self.assertFalse(check_candidate(self.contract,NeverScorer(),self.raw,score)['accepted'])
    def test_oversized_rejected_without_score(self):
        self.assertFalse(check_candidate(self.contract,NeverScorer(),self.raw+' '*17000,-5)['accepted'])
    def test_more_than_one_pose_rejected(self):
        multi='MODEL 1\n'+self.raw+'ENDMDL\nMODEL 2\n'+self.raw+'ENDMDL\n'
        self.assertFalse(check_candidate(self.contract,NeverScorer(),multi,-5)['accepted'])
    def test_atom_type_change_rejected_without_score(self):
        lines=self.raw.splitlines()
        for i,line in enumerate(lines):
            if line.startswith(('ATOM  ','HETATM')):lines[i]=line[:77]+'Zn';break
        self.assertFalse(check_candidate(self.contract,NeverScorer(),'\n'.join(lines)+'\n',-5)['accepted'])
    def test_torsion_tree_change_rejected_without_score(self):
        self.assertFalse(check_candidate(self.contract,NeverScorer(),self.raw.replace('TORSDOF 5','TORSDOF 0'),-5)['accepted'])

if __name__=='__main__':unittest.main()
