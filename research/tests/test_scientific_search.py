import json
from pathlib import Path
import random
import unittest
import numpy as np
from research.cpd_search import read_model,energy,direct_energy,search
from research.rigid_grid_search import rotations,poses,SPACE,Grid
ROOT=Path(__file__).resolve().parents[2]


class ScientificSearchTests(unittest.TestCase):
    def test_rotation_bank_is_rigid_and_unique(self):
        bank=rotations();self.assertEqual(len({r.tobytes() for r in bank}),24)
        for r in bank:
            np.testing.assert_array_equal(r@r.T,np.eye(3));self.assertEqual(round(np.linalg.det(r)),1)

    def test_pose_bank_permutation_has_no_duplicates(self):
        xyz=np.array([[0.,0.,0.],[1.,1.,1.]])
        ids,_=poses(xyz,SPACE,20260907)
        self.assertEqual(len(set(map(int,ids))),SPACE)
        # IDs are unique; symmetric molecules may still have equivalent poses.
        with self.assertRaises(ValueError):poses(xyz,SPACE+1,1)

    def test_grid_affine_interpolation_and_outside_rejection(self):
        grid=Grid.__new__(Grid);grid.spacing=1;grid.cells=np.array([2,2,2]);grid.origin=np.zeros(3)
        z,y,x=np.indices((3,3,3));grid.data=-(x+2*y+3*z).astype(float);grid.quantized=(grid.data*10000).astype(np.int64)
        xyz=np.array([[.25,.5,.75],[3,0,0]])
        floating,valid=grid.evaluate(xyz);integer,valid_int=grid.evaluate(xyz,True)
        self.assertAlmostEqual(floating[0],-3.5);self.assertEqual(integer[0],-35000)
        self.assertEqual(valid.tolist(),[True,False]);np.testing.assert_array_equal(valid,valid_int)

    @unittest.skipUnless((ROOT/'tmp/docking-ladder/cpd/1BK2.wcsp').exists(),'Fetch CPD model first')
    def test_exact_model_and_wraparound(self):
        model=read_model(ROOT/'tmp/docking-ladder/cpd/1BK2.wcsp')
        restricted=json.loads((ROOT/'docs/evaluation/docking_ladder_2026-09-07/cpd_restricted_model.json').read_text())
        rng=random.Random(20260907);space=2**restricted['positions']
        self.assertEqual(energy(restricted,0),1133936141479)
        for identity in [0,space-1]+[rng.randrange(space) for _ in range(1000)]:
            self.assertEqual(energy(restricted,identity),direct_energy(model,restricted,identity))
        for start in [0,space-10]:
            ids=[(start+65537*i)%space for i in range(64)]
            self.assertEqual(len(set(ids)),64)
            expected=min((direct_energy(model,restricted,identity),i) for i,identity in enumerate(ids))
            self.assertEqual(search(restricted,64,start),expected)
        with self.assertRaises(ValueError):search(restricted,64,space)


if __name__=='__main__':unittest.main()
