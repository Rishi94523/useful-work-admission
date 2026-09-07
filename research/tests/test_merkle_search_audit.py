import unittest
from research.merkle_search_audit import Tree,verify_opening,accept_probability,minimum_samples

class AuditTests(unittest.TestCase):
    def setUp(self):self.tree=Tree([{'task':'a','index':i,'score':i*i} for i in range(16)])
    def test_valid_paths(self):
        for i in range(16):self.assertTrue(verify_opening(self.tree.root,self.tree.opening(i),16))
    def test_changed_score_and_task_fail(self):
        for field,value in [('score',999),('task','b')]:
            opening=self.tree.opening(3);opening['row']=dict(opening['row'],**{field:value})
            self.assertFalse(verify_opening(self.tree.root,opening,16))
    def test_wrong_index_and_path_fail(self):
        opening=self.tree.opening(3);opening['index']=4
        self.assertFalse(verify_opening(self.tree.root,opening,16))
        opening=self.tree.opening(3);opening['path'][0]='00'*32
        self.assertFalse(verify_opening(self.tree.root,opening,16))
    def test_one_bad_edge_requires_nearly_every_edge(self):
        self.assertEqual(accept_probability(256,1,16),240/256)
        self.assertEqual(minimum_samples(256,1,1e-6),256)
    def test_all_bad_or_all_good(self):
        self.assertEqual(accept_probability(256,256,1),0)
        self.assertEqual(accept_probability(256,0,256),1)

if __name__=='__main__':unittest.main()
