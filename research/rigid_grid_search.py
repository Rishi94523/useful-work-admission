"""Finite rigid-pose search using real, exported Vina affinity maps.

This is a coarse fixed-conformer pose screen, not flexible Vina or binding truth.
The integer variant defines a new quantized objective; it is not a SNARK yet.
"""
import itertools
from pathlib import Path
import numpy as np

SCALE=10000
FRAC=1024
SPACE=24*8**3


def rotations():
    out=[]
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product([-1,1],repeat=3):
            r=np.eye(3,dtype=int)[list(perm)]*np.array(signs)[:,None]
            if round(np.linalg.det(r))==1:out.append(r)
    return np.array(out)


def poses(xyz, count, seed):
    if not 1<=count<=SPACE:raise ValueError('Count outside the finite bank')
    ids=(int(seed)+5*np.arange(count,dtype=np.int64))%SPACE
    translation_id=ids%512
    translations=np.stack([(translation_id//(8**k))%8-3 for k in range(3)],axis=1)*.375
    center=xyz.mean(axis=0)
    positions=np.einsum('nij,aj->nai',rotations()[ids//512],xyz-center)+center+translations[:,None,:]
    # Matches the exchanged PDBQT coordinate resolution with an explicit rule.
    return ids,np.floor(positions*1000+.5)/1000


class Grid:
    def __init__(self,path):
        with Path(path).open() as f:
            header=[next(f) for _ in range(6)]
            self.spacing=float(header[3].split()[1])
            self.cells=np.array(list(map(int,header[4].split()[1:])))
            self.center=np.array(list(map(float,header[5].split()[1:])))
            data=np.fromstring(f.read(),sep=' ')
        self.origin=self.center-self.cells*self.spacing/2
        self.data=data.reshape(tuple((self.cells+1)[::-1]))
        self.quantized=np.floor(self.data*SCALE+.5).astype(np.int64)
        # Guarantees exact accumulation of eight weighted corners in int64.
        if np.max(np.abs(self.quantized))*8*FRAC**3>=2**63:raise OverflowError('Grid needs wider arithmetic')

    def evaluate(self,xyz,integer=False):
        location=(xyz-self.origin)/self.spacing
        valid=np.all((location>=0)&(location<self.cells),axis=-1)
        clipped=np.minimum(np.maximum(location,0),self.cells-1e-8)
        cell=np.floor(clipped).astype(int);fraction=clipped-cell
        if integer:
            fraction=np.floor(fraction*FRAC+.5).astype(np.int64)
            result=np.zeros(xyz.shape[:-1],dtype=np.int64)
        else:result=np.zeros(xyz.shape[:-1])
        for corner in itertools.product([0,1],repeat=3):
            ix=cell+corner
            weight=np.ones(xyz.shape[:-1],dtype=np.int64 if integer else float)
            for k in range(3):weight*=fraction[...,k] if corner[k] else (FRAC if integer else 1)-fraction[...,k]
            result+=(self.quantized if integer else self.data)[ix[...,2],ix[...,1],ix[...,0]]*weight
        if integer:
            result=(result+FRAC**3//2)//FRAC**3
            positive=result>0
            # Vina's positive-energy curl, v=1000, with rounded division.
            result[positive]=(result[positive]*(1000*SCALE)+(1000*SCALE+result[positive])//2)//(1000*SCALE+result[positive])
        else:
            positive=result>0;result[positive]=1000*result[positive]/(1000+result[positive])
        return result,valid


def score(maps,types,xyz,integer=False):
    result=np.zeros(xyz.shape[0],dtype=np.int64 if integer else float)
    valid=np.ones(xyz.shape[0],dtype=bool)
    for typ in sorted(set(types)):
        chosen=np.array([t==typ for t in types])
        values,inside=maps[typ].evaluate(xyz[:,chosen,:],integer)
        result+=values.sum(axis=1);valid &= inside.all(axis=1)
    result[~valid]=10**12 if integer else 1e8
    return result,valid
