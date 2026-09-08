"""Bounded, post-commit block-opening verifier. Statistical result checks only."""
import base64,hashlib,json,math
import numpy as np
from research.docking_campaign import canonical


def digest(raw):return hashlib.sha256(raw).hexdigest()
def wire(value):return json.dumps(value,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def commitment(binding,headers):
    return digest(wire([binding,[[h[k] for k in ('id','start','count','mode','block','root','score_hash')] for h in headers]]))


def decode(raw,limit):
    if not isinstance(raw,str) or len(raw)>4*((limit+2)//3):raise ValueError('Oversized base64')
    result=base64.b64decode(raw,validate=True)
    if len(result)>limit:raise ValueError('Oversized decoded data')
    return result


def inspect_headers(assets,expected,binding,headers,root):
    if len(headers)!=len(expected) or not 1<=len(headers)<=16:raise ValueError('Job count mismatch')
    scores=[]
    for h,j in zip(headers,expected):
        if any(h[k]!=j[k] for k in ('id','start','count')):raise ValueError('Assigned range changed')
        if h['mode']!=j['mode']:raise ValueError('Assigned audit mode changed')
        if type(h['count'])!=int or not 1<=h['count']<=16384 or h['mode'] not in ('B','C','E') or h['block']!=64:raise ValueError('Unsupported bounded protocol')
        if any(not isinstance(h[k],str) or len(h[k])!=64 or any(c not in '0123456789abcdef' for c in h[k]) for k in ('root','score_hash')):raise ValueError('Hash malformed')
        raw=decode(h['scores'],4*h['count'])
        if len(raw)!=4*h['count'] or digest(raw)!=h['score_hash']:raise ValueError('Score vector mismatch')
        scores.append(np.frombuffer(raw,dtype='<i4'))
    if commitment(binding,headers)!=root:raise ValueError('Bundle binding mismatch')
    return scores


def required_indices(headers,scores,draws):
    chosen=[set() for h in headers]
    if len(draws)>128:raise ValueError('Too many challenges')
    for j,i in draws:
        if type(j)!=int or type(i)!=int or not 0<=j<len(headers) or not 0<=i<headers[j]['count']:raise ValueError('Challenge outside assignment')
        chosen[j].add(i)
    for j,(h,s) in enumerate(zip(headers,scores)):
        chosen[j].add(int(np.argmin(s)))
        if h['mode']=='E':
            for begin in range(0,h['count'],h['block']):chosen[j].add(begin+int(np.argmin(s[begin:begin+h['block']])))
    return chosen


def verify(assets,expected,binding,headers,root,draws,answers):
    try:return _verify(assets,expected,binding,headers,root,draws,answers)
    except (KeyError,TypeError,IndexError,OverflowError) as error:raise ValueError('Malformed audit message') from error


def _verify(assets,expected,binding,headers,root,draws,answers):
    scores=inspect_headers(assets,expected,binding,headers,root)
    required=required_indices(headers,scores,draws)
    if len(answers)!=len(headers):raise ValueError('Opening job count')
    checked=0;opened_bytes=0
    for j,(h,openings) in enumerate(zip(headers,answers)):
        needed={i//64 for i in required[j]}
        if len(openings)!=len(needed):raise ValueError('Missing or surplus chunks')
        depth=(math.ceil(h['count']/64)-1).bit_length();width=1 if h['mode']=='B' else len(assets.ligands[h['id']]['types'])
        rows={}
        for opening in openings:
            block=opening['block']
            if type(block)!=int or block not in needed or block in rows:raise ValueError('Wrong or duplicate chunk')
            count=min(64,h['count']-block*64);raw=decode(opening['data'],4*count*width);opened_bytes+=len(raw)
            if len(raw)!=4*count*width or len(opening['path'])!=depth:raise ValueError('Chunk/path shape')
            node=digest(wire([binding,h['id'],h['start'],h['count'],h['mode'],64,block])+b'\n'+raw);index=block
            for other in opening['path']:
                if not isinstance(other,str) or len(other)!=64:raise ValueError('Bad path hash')
                pair=bytes.fromhex(other)+bytes.fromhex(node) if index&1 else bytes.fromhex(node)+bytes.fromhex(other)
                node=digest(b'\x01'+pair);index//=2
            if node!=h['root']:raise ValueError('Merkle commitment mismatch')
            values=np.frombuffer(raw,dtype='<i4').reshape(count,width)
            if not np.array_equal(values.astype(np.int64).sum(axis=1),scores[j][block*64:block*64+count]):raise ValueError('Scores inconsistent with committed rows')
            rows[block]=values
        indices=sorted(required[j]);truth=assets.contributions(h['id'],np.array(indices)+h['start'])
        if h['mode']=='B':truth=truth.astype(np.int64).sum(axis=1)[:,None]
        for i,row in zip(indices,truth):
            if not np.array_equal(rows[i//64][i%64],row):raise ValueError('Incorrect scientific record')
            checked+=1
    return {'accepted':True,'checked_poses':checked,'opened_bytes':opened_bytes,'best_scores':[int(s.min()) for s in scores]}


def acceptance_bound(correct,total,q):
    if not 0<=correct<=total or not 0<=q<=total:raise ValueError('Invalid bound')
    if correct<q:return 0.
    return math.prod((correct-i)/(total-i) for i in range(q))
