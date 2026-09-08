"""Integer, fixed-conformer Vina-map screening; independent Python verifier.

Scientific objective: intermolecular map energy only. This omits flexible search,
intramolecular energy and torsional normalization; never label it full Vina.
"""
import itertools
import json
from pathlib import Path
import numpy as np

SCALE=10000
FRAC=256
DEN=FRAC**3


class Assets:
    def __init__(self,path):
        self.path=Path(path);self.meta=json.loads((self.path/'assets.json').read_text())
        self.maps=np.fromfile(self.path/'maps.bin',dtype='<i4').reshape(self.meta['map_shape'])
        self.ligands={r['id']:r for r in self.meta['ligands']}
        self.rot=np.array(self.meta['rotations'],dtype=np.int64)
        self.origin=np.array(self.meta['origin_micro'],dtype=np.int64)
        self.center=np.array(self.meta['center_milli'],dtype=np.int64)
        self.spacing=self.meta['spacing_micro']
        if int(np.abs(self.maps.astype(np.int64)).max())*DEN>=2**53:raise OverflowError('JS integer bound')

    def positions(self,identifier,indices):
        lig=self.ligands[identifier];conf=np.array(lig['conformers_milli'],dtype=np.int64)
        total=len(conf)*len(self.rot)*512
        indices=np.asarray(indices,dtype=np.int64)
        if np.any(indices<0) or np.any(indices>=total):raise ValueError('Pose range outside bank')
        ids=(indices*104729+lig['offset'])%total
        trans=ids%512;ri=(ids//512)%len(self.rot);ci=ids//(512*len(self.rot))
        shift=np.stack([(trans//(8**k))%8*375-1312 for k in range(3)],axis=1)
        xyz=(np.einsum('nij,naj->nai',self.rot[ri],conf[ci])+500000)//1000000
        return xyz+self.center+shift[:,None,:]

    def contributions(self,identifier,indices,coarse=False):
        lig=self.ligands[identifier];xyz=self.positions(identifier,indices)
        delta=xyz*1000-self.origin;cell=delta//self.spacing
        if np.any(cell<0) or np.any(cell>=np.array(self.meta['map_shape'][1:])[::-1]-1):raise ValueError('Out of box pose')
        fraction=((delta%self.spacing)*FRAC+self.spacing//2)//self.spacing
        types=np.array(lig['types']);out=np.zeros(xyz.shape[:-1],dtype=np.int64)
        for c in ([(0,0,0)] if coarse else itertools.product([0,1],repeat=3)):
            ix=cell+c
            weight=DEN if coarse else np.prod(np.where(np.array(c),fraction,FRAC-fraction),axis=-1)
            out+=self.maps[types,ix[...,2],ix[...,1],ix[...,0]]*weight
        out=(out+DEN//2)//DEN;positive=out>0
        out[positive]=(out[positive]*(1000*SCALE)+(1000*SCALE+out[positive])//2)//(1000*SCALE+out[positive])
        if np.any(abs(out)>2**31-1) or np.any(abs(out.sum(axis=1))>2**31-1):raise OverflowError('Wire int32 bound')
        return out.astype('<i4')

    def evaluate(self,identifier,start,count):
        return self.contributions(identifier,np.arange(start,start+count))
