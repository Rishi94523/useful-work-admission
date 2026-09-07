"""Prepare a development Groth16 calibration; keys are NOT for deployment."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research.docking_pilot import ROOT,CACHE,CASES,case_spec
from research.docking_contract import atoms

ZK=CACHE/'zk'
LIB=ROOT/'research/docking-zk'
SNARK=LIB/'node_modules/snarkjs/build/cli.cjs'

def run(args,label):
    start=time.perf_counter()
    result=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (ZK/(label+'.log')).write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    if result.returncode:raise RuntimeError(label+'\n'+result.stdout[-5000:]+'\n'+result.stderr[-3000:])
    print(label,'seconds',round(time.perf_counter()-start,3),flush=True)
    return {'step':label,'wall_seconds':time.perf_counter()-start}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--compile-only',action='store_true');args=parser.parse_args()
    ZK.mkdir(exist_ok=True)
    records=[]
    for count in [2,8]:
        out=ZK/str(count);out.mkdir(exist_ok=True)
        circuit=out/f'contact_{count}.circom'
        circuit.write_text('pragma circom 2.2.3;\ninclude "contact_search.circom";\ncomponent main {public [seed, ligand, receptor]} = ContactSearch('+str(count)+');\n')
        records.append(run([str(CACHE/'circom.exe'),str(circuit),'--r1cs','--wasm','--sym','--O2','-l',str(LIB/'circuits'),'-l',str(LIB/'node_modules'),'-o',str(out)],f'compile_{count}'))
        records.append(run(['node',str(SNARK),'r1cs','info',str(out/f'contact_{count}.r1cs')],f'r1cs_{count}'))
    s=case_spec(CASES[0]);center=np.array([s['params']['center_'+x] for x in 'xyz'])
    lig=np.array([a[4] for a in atoms((CACHE/'inputs'/s['ligand']).read_text()) if not a[2].startswith('H')])
    rec=np.array([a[4] for a in atoms((CACHE/'inputs'/s['receptor']).read_text()) if not a[2].startswith('H')])
    ligand=np.rint((lig[:8]-lig.mean(axis=0))*10+1000).astype(int)
    receptor=np.rint((rec[np.argsort(np.linalg.norm(rec-center,axis=1))[:8]]-center)*10+1000).astype(int)
    data={'seed':'20260906','ligand':ligand.tolist(),'receptor':receptor.tolist()}
    (ZK/'input.json').write_text(json.dumps(data,indent=2)+'\n')
    if not args.compile_only:
        ptau=ZK/'DEV_contributed_final.ptau'
        if not ptau.exists() or ptau.stat().st_size<75_000_000:
            records.append(run(['node',str(SNARK),'powersoftau','new','bn128','16',str(ZK/'DEVELOPMENT_ONLY_initial.ptau')],'powers_new'))
            records.append(run(['node',str(LIB/'contribute.mjs'),'ptau',str(ZK/'DEVELOPMENT_ONLY_initial.ptau'),str(ZK/'DEV_contributed.ptau')],'powers_contribute'))
            records.append(run(['node',str(SNARK),'powersoftau','prepare','phase2',str(ZK/'DEV_contributed.ptau'),str(ptau)],'powers_prepare'))
        for count in [2,8]:
            out=ZK/str(count)
            records.append(run(['node',str(SNARK),'groth16','setup',str(out/f'contact_{count}.r1cs'),str(ptau),str(out/'DEV_initial.zkey')],f'setup_{count}'))
            records.append(run(['node',str(LIB/'contribute.mjs'),'zkey',str(out/'DEV_initial.zkey'),str(out/'DEVELOPMENT_ONLY.zkey')],f'key_contribute_{count}'))
            records.append(run(['node',str(SNARK),'zkey','export','verificationkey',str(out/'DEVELOPMENT_ONLY.zkey'),str(out/'verification_key.json')],f'vk_{count}'))
    manifest={'scope':'Groth16 performance/correctness calibration only. Eight ligand and eight receptor atoms, integer contact potential, translations only. NOT Vina, not validated docking or secure proof-of-work. Local single-party phase-one and phase-two random contributions; not a reviewed multi-party ceremony. Keys must never be deployed.', 'circuits':[2,8],'input':data,'steps':records,'source_sha256':hashlib.sha256((LIB/'circuits/contact_search.circom').read_bytes()).hexdigest()}
    (ROOT/'docs/evaluation/docking_pilot_2026-09-06/zk_setup.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
