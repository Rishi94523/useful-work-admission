"""Fail closed if score-only conversion changes pose geometry or element identity."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from run_gnina_diagnostic import Chem, geometry_error, poses, validation_molecule


class GeometryTests(unittest.TestCase):
    def fixture(self):
        mol=Chem.MolFromSmiles('CO');conf=Chem.Conformer(2)
        conf.SetAtomPosition(0,(0.,0.,0.));conf.SetAtomPosition(1,(1.4,0.,0.));mol.AddConformer(conf)
        lines=[]
        for index,(x,kind) in enumerate([(0.,'C'),(1.4,'OA')],1):
            lines.append(f'ATOM  {index:5d}  C   UNL     1    {x:8.3f}{0.:8.3f}{0.:8.3f}  1.00  0.00     0.000 {kind}')
        return '\n'.join(lines)+'\n',mol

    def test_identical_and_reordered_atoms(self):
        source,mol=self.fixture()
        self.assertEqual(geometry_error(source,mol),0.)
        self.assertEqual(geometry_error(source,Chem.RenumberAtoms(mol,[1,0])),0.)

    def test_translation_is_detected_without_alignment(self):
        source,mol=self.fixture();mol.GetConformer().SetAtomPosition(0,(.1,0.,0.))
        self.assertGreater(geometry_error(source,mol),.002)

    def test_element_change_is_detected(self):
        source,mol=self.fixture();mol.GetAtomWithIdx(1).SetAtomicNum(7)
        self.assertGreater(geometry_error(source,mol),.002)

    def test_pose_count(self):
        source,_=self.fixture()
        self.assertEqual(len(poses('MODEL 1\n'+source+'ENDMDL\nMODEL 2\n'+source+'ENDMDL\n')),2)

    def test_native_pdbqt_validation(self):
        source,_=self.fixture()
        self.assertEqual(geometry_error(source,validation_molecule(source)),0.)


if __name__=='__main__':unittest.main()
