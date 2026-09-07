"""Research pose preflight and persistent native rescoring; not proof of search effort."""
from pathlib import Path
from itertools import combinations
import hashlib
import json
import math
import subprocess
import time
import numpy as np
from research.docking_pilot import CACHE, ROOT, first_pose


def atoms(text):
    rows=[]
    for line in text.splitlines():
        if line.startswith(('ATOM  ','HETATM')):
            if len(line)<77: raise ValueError('short atom record')
            rows.append((int(line[6:11]),line[12:16].strip(),line[77:].strip(),float(line[70:76]),[float(line[30:38]),float(line[38:46]),float(line[46:54])]))
    return rows


def tree(text):
    return [tuple(line.split()) for line in text.splitlines() if line.split() and line.split()[0] in {'ROOT','ENDROOT','BRANCH','ENDBRANCH','TORSDOF'}]


class PoseContract:
    """Fixed molecule/box, rigid-fragment and inferred local-geometry checks.

    Not a complete chemical validator: protonation/preparation and symmetric-atom
    handling require a validated chemistry pipeline before scientific deployment.
    """
    def __init__(self,spec):
        self.spec=spec
        self.reference=(CACHE/'inputs'/spec['ligand']).read_text()
        self.ref_atoms=atoms(self.reference)
        if not 1<=len(self.ref_atoms)<=128: raise ValueError('atom budget')
        self.identity=[x[:4] for x in self.ref_atoms]
        self.ref_xyz=np.array([x[4] for x in self.ref_atoms])
        self.heavy=np.array([not x[2].startswith('H') for x in self.ref_atoms])
        self.center=np.array([spec['params']['center_'+x] for x in 'xyz'])
        # Vina rounds requested dimensions up to whole grid intervals. The PDBQT
        # output rounds coordinates to 0.001 A, so allow that serialization error.
        self.half_box=np.ceil(np.array([spec['params']['size_'+x] for x in 'xyz'])/.375)*.375/2
        self.ref_tree=tree(self.reference)
        fragments=[]; current=[]; stack=[]; serials={x[0]:i for i,x in enumerate(self.ref_atoms)}
        for line in self.reference.splitlines():
            tokens=line.split()
            if not tokens: continue
            if tokens[0]=='ROOT': current=[];fragments.append(current)
            elif tokens[0]=='BRANCH': stack.append(current);current=[];fragments.append(current)
            elif tokens[0]=='ENDBRANCH': current=stack.pop()
            elif line.startswith(('ATOM  ','HETATM')):
                i=serials[int(line[6:11])]
                if self.heavy[i]:current.append(i)
        self.fragments=[x for x in fragments if len(x)>1]
        # Preserve bond lengths and valence angles, using a conservative inferred graph.
        radii={'C':0.76,'A':0.76,'N':0.71,'NA':0.71,'OA':0.66,'O':0.66,'S':1.05,'SA':1.05,'F':0.57,'Cl':1.02,'Br':1.20,'I':1.39,'P':1.07}
        adjacency={i:set() for i in np.flatnonzero(self.heavy)}
        for i,j in combinations(adjacency,2):
            d=np.linalg.norm(self.ref_xyz[i]-self.ref_xyz[j])
            limit=1.22*(radii.get(self.ref_atoms[i][2],.8)+radii.get(self.ref_atoms[j][2],.8))
            if .4<d<limit:adjacency[i].add(j);adjacency[j].add(i)
        pairs=set()
        for i,neighbors in adjacency.items():
            for j in neighbors:pairs.add(tuple(sorted((i,j))))
            for j,k in combinations(neighbors,2):pairs.add(tuple(sorted((j,k))))
        self.local_pairs=sorted(pairs)
        self.chiral=[]
        for i,neighbors in adjacency.items():
            for a,b,c in combinations(sorted(neighbors),3):
                volume=np.linalg.det(self.ref_xyz[[a,b,c]]-self.ref_xyz[i])
                if abs(volume)>.05:self.chiral.append((i,a,b,c,np.sign(volume)))

    def validate(self,payload):
        if isinstance(payload,str): payload=payload.encode()
        if len(payload)>16384:raise ValueError('byte budget')
        decoded=payload.decode('ascii')
        if sum(line.startswith('MODEL') for line in decoded.splitlines())>1:raise ValueError('one pose required')
        text=first_pose(decoded)
        row=atoms(text)
        if [x[:4] for x in row]!=self.identity:raise ValueError('atom identity/count mismatch')
        if tree(text)!=self.ref_tree:raise ValueError('torsion tree mismatch')
        xyz=np.array([x[4] for x in row])
        if not np.isfinite(xyz).all():raise ValueError('nonfinite coordinate')
        if np.any(np.abs(xyz[self.heavy]-self.center)>self.half_box+.002):raise ValueError('outside docking box')
        for fragment in self.fragments:
            a=self.ref_xyz[fragment];b=xyz[fragment]
            a=a-a.mean(axis=0);b=b-b.mean(axis=0)
            u,_,vt=np.linalg.svd(a.T@b)
            correction=np.eye(3);correction[-1,-1]=np.linalg.det(u@vt)
            if np.max(np.linalg.norm(a@(u@correction@vt)-b,axis=1))>.025:raise ValueError('rigid fragment distortion')
        for i,j in self.local_pairs:
            if abs(np.linalg.norm(xyz[i]-xyz[j])-np.linalg.norm(self.ref_xyz[i]-self.ref_xyz[j]))>.025:raise ValueError('bond/angle distortion')
        for i,a,b,c,sign in self.chiral:
            if np.linalg.det(xyz[[a,b,c]]-xyz[i])*sign<=0:raise ValueError('chirality change')
        # Reconstruct the chemistry from trusted input; only coordinates come from client.
        lines=[];index=0
        for line in self.reference.splitlines():
            if line.startswith(('ATOM  ','HETATM')):
                x,y,z=xyz[index];line=line[:30]+f'{x:8.3f}{y:8.3f}{z:8.3f}'+line[54:];index+=1
            lines.append(line)
        canonical='\n'.join(lines)+'\n'
        return canonical,xyz,hashlib.sha256(np.rint(xyz*1000).astype('<i4').tobytes()).hexdigest()


class NativeScorer:
    def __init__(self,spec,seed=104729):
        params=[spec['params'][prefix+x] for prefix in ['center_','size_'] for x in 'xyz']
        args=[str(CACHE/'build/docking_worker.exe'),str(CACHE/'inputs'/spec['receptor']),str(CACHE/'inputs'/spec['ligand']),*map(str,params),str(seed)]
        self.proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
        line=self.proc.stdout.readline()
        if not line:raise RuntimeError('Native worker startup failed')
        self.setup=json.loads(line)
    def request(self,path,mode='S',exhaustiveness=1,max_evals=1000,output=None):
        output=output or CACHE/'runs/unused.pdbqt'
        # C++ std::quoted uses backslash escaping; use forward slashes in local paths.
        command=f'{mode} "{Path(path).resolve().as_posix()}" {exhaustiveness} {max_evals} "{Path(output).resolve().as_posix()}"\n'
        begin=time.perf_counter()
        self.proc.stdin.write(command);self.proc.stdin.flush()
        line=self.proc.stdout.readline()
        if not line:raise RuntimeError('Native worker terminated')
        result=json.loads(line);result['ipc_wall_ms']=(time.perf_counter()-begin)*1000
        return result
    def close(self):
        if self.proc.poll() is None:
            self.proc.stdin.write('QUIT\n');self.proc.stdin.flush()
            try:self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()
        self.proc.stdin.close();self.proc.stdout.close()


def check_candidate(contract,scorer,payload,claimed_score,*,tolerance=.05):
    """Actual candidate predicate. Deliberately makes no search-effort assertion."""
    if isinstance(claimed_score,bool) or not isinstance(claimed_score,(int,float)) or not math.isfinite(claimed_score):
        return {'accepted':False,'reason':'invalid_claimed_score','scorer_called':False}
    try:
        canonical,xyz,digest=contract.validate(payload)
    except (ValueError,UnicodeError,StopIteration) as exc:
        return {'accepted':False,'reason':str(exc),'scorer_called':False}
    target=CACHE/'runs/candidate-predicate.pdbqt'
    target.write_text(canonical,encoding='ascii')
    native=scorer.request(target)
    if not native['ok']:
        return {'accepted':False,'reason':native.get('error','engine_error'),'scorer_called':True}
    error=abs(native['score']-claimed_score)
    return {'accepted':error<=tolerance,'reason':'score_match' if error<=tolerance else 'score_mismatch','scorer_called':True,'actual_score':native['score'],'score_error':error,'pose_hash':digest}
