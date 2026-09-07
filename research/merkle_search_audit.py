"""Raw Merkle sampling experiment, not a proof of all requested computation."""
import hashlib
import json
import math

def encoded(value):return json.dumps(value,separators=(',',':'),sort_keys=True).encode('ascii')
def leaf(value):return hashlib.sha256(b'leaf\0'+encoded(value)).digest()
def parent(a,b):return hashlib.sha256(b'node\0'+a+b).digest()

class Tree:
    def __init__(self,rows):
        if not rows or len(rows)&(len(rows)-1):raise ValueError('Power-of-two leaf count required')
        self.rows=rows;self.levels=[[leaf(r) for r in rows]]
        while len(self.levels[-1])>1:
            xs=self.levels[-1];self.levels.append([parent(xs[i],xs[i+1]) for i in range(0,len(xs),2)])
        self.root=self.levels[-1][0]
    def opening(self,index):
        proof=[];cursor=index
        for level in self.levels[:-1]:proof.append(level[cursor^1].hex());cursor//=2
        return {'index':index,'row':self.rows[index],'path':proof}

def verify_opening(root,opening,count):
    index=opening['index']
    if not isinstance(index,int) or isinstance(index,bool) or not 0<=index<count:return False
    if count<1 or count&(count-1) or len(opening['path'])!=count.bit_length()-1:return False
    value=leaf(opening['row']);cursor=index
    try:
        for item in opening['path']:
            sibling=bytes.fromhex(item)
            if len(sibling)!=32:return False
            value=parent(sibling,value) if cursor&1 else parent(value,sibling);cursor//=2
    except (ValueError,TypeError):return False
    return value==root

def accept_probability(total,bad,samples):
    """Exact probability when sampling distinct positions uniformly after commit."""
    if not 0<=bad<=total or not 0<=samples<=total:raise ValueError('Invalid audit dimensions')
    return math.comb(total-bad,samples)/math.comb(total,samples) if samples<=total-bad else 0.0

def minimum_samples(total,bad,target):
    return next(q for q in range(total+1) if accept_probability(total,bad,q)<=target)
