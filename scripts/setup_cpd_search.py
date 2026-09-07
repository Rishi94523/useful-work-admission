"""Compile and prepare development keys for the authentic restricted CPD pilot."""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research.process_measure import measured_run
from scripts.prepare_docking_ladder import r1cs_header
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tmp/docking-ladder/cpd';OUT=ROOT/'docs/evaluation/docking_ladder_2026-09-07';LIB=ROOT/'research/docking-zk'
evidence={'scope':'Exact published-model restricted CPD objective; campaign-specific hardcoded coefficients and development-only keys. Not an effort lower bound.','circuits':{},'steps':[]}
def run(cmd,label):
    row={'step':label,**measured_run(cmd,BASE/(label+'.log'),timeout=600)};evidence['steps'].append(row)
    (OUT/'cpd_setup.json').write_text(json.dumps(evidence,indent=2)+'\n')
    if row['exit_code']!=0:raise RuntimeError(label+' failed: '+(BASE/(label+'.log')).read_text()[-2000:])
    print(json.dumps(row),flush=True)
for n in [16,64]:
    d=BASE/str(n)
    run([str(ROOT/'tmp/docking-pilot/circom.exe'),str(d/'main.circom'),'--r1cs','--wasm','--O2','-l',str(LIB/'node_modules'),'-o',str(d)],f'compile_{n}')
    evidence['circuits'][str(n)]={**r1cs_header(d/'main.r1cs'),'r1cs_bytes':(d/'main.r1cs').stat().st_size,'circuit_sha256':hashlib.sha256((d/'main.circom').read_bytes()).hexdigest()}
    run(['node',str(LIB/'node_modules/snarkjs/build/cli.cjs'),'groth16','setup',str(d/'main.r1cs'),str(BASE.parent/'ppot_0080_19.ptau'),str(d/'DEV_initial.zkey')],f'setup_{n}')
    run(['node',str(LIB/'contribute.mjs'),'zkey',str(d/'DEV_initial.zkey'),str(d/'DEVELOPMENT_ONLY.zkey')],f'contribute_{n}')
    run(['node',str(LIB/'node_modules/snarkjs/build/cli.cjs'),'zkey','export','verificationkey',str(d/'DEVELOPMENT_ONLY.zkey'),str(d/'verification_key.json')],f'vk_{n}')
    evidence['circuits'][str(n)]['proving_key_bytes']=(d/'DEVELOPMENT_ONLY.zkey').stat().st_size
    (OUT/f'cpd_{n}.circom').write_bytes((d/'main.circom').read_bytes())
    (OUT/'cpd_setup.json').write_text(json.dumps(evidence,indent=2)+'\n')
