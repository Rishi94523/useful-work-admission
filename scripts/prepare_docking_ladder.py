"""Compile exact scaling points and prepare selected DEVELOPMENT Groth16 keys."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research.process_measure import measured_run

ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tmp/docking-ladder'
OUT=ROOT/'docs/evaluation/docking_ladder_2026-09-07'
LIB=ROOT/'research/docking-zk';CLI=LIB/'node_modules/snarkjs/build/cli.cjs'

def r1cs_header(path):
    with path.open('rb') as f:
        assert f.read(4)==b'r1cs';version,sections=struct.unpack('<II',f.read(8))
        for _ in range(sections):
            kind,size=struct.unpack('<IQ',f.read(12));end=f.tell()+size
            if kind==1:
                field_bytes=struct.unpack('<I',f.read(4))[0];f.read(field_bytes)
                wires,outputs,inputs,private=struct.unpack('<IIII',f.read(16));labels=struct.unpack('<Q',f.read(8))[0];constraints=struct.unpack('<I',f.read(4))[0]
                return dict(version=version,wires=wires,public_outputs=outputs,public_inputs=inputs,private_inputs=private,labels=labels,constraints=constraints)
            f.seek(end)
    raise ValueError('Missing R1CS header')

def main():
    p=argparse.ArgumentParser();p.add_argument('--compile',nargs='*',type=int,default=[16,32,64,128,256]);p.add_argument('--setup',nargs='*',type=int,default=[16,32,64]);args=p.parse_args()
    BASE.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(ROOT/'tmp/docking-pilot/zk/input.json',BASE/'input.json')
    target=OUT/'setup.json'
    evidence=json.loads(target.read_text()) if target.exists() else {'scope':'Exact compiled sizes for the prior reduced contact calibration; not scientific docking validation. Public phase-one setup plus local development phase-two contribution.','circuits':{},'steps':[]}
    def run(command,label):
        row={'step':label,**measured_run(command,BASE/(label+'.log'))};evidence['steps'].append(row)
        target.write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(row),flush=True)
        if row['exit_code']!=0:raise RuntimeError(label+' failed; see local log')
    for n in args.compile:
        directory=BASE/str(n);directory.mkdir(exist_ok=True)
        circuit=directory/f'contact_{n}.circom'
        circuit.write_text(f'pragma circom 2.2.3;\ninclude "contact_search.circom";\ncomponent main {{public [seed, ligand, receptor]}} = ContactSearch({n});\n')
        run([str(ROOT/'tmp/docking-pilot/circom.exe'),str(circuit),'--r1cs','--wasm','--O2','-l',str(LIB/'circuits'),'-l',str(LIB/'node_modules'),'-o',str(directory)],f'compile_{n}')
        r1cs=directory/f'contact_{n}.r1cs'
        evidence['circuits'][str(n)]={**r1cs_header(r1cs),'r1cs_bytes':r1cs.stat().st_size,'witness_wasm_bytes':(directory/f'contact_{n}_js/contact_{n}.wasm').stat().st_size,'r1cs_sha256':hashlib.sha256(r1cs.read_bytes()).hexdigest()}
        target.write_text(json.dumps(evidence,indent=2)+'\n')
    for n in args.setup:
        directory=BASE/str(n)
        run(['node',str(CLI),'groth16','setup',str(directory/f'contact_{n}.r1cs'),str(BASE/'ppot_0080_19.ptau'),str(directory/'DEV_initial.zkey')],f'setup_{n}')
        run(['node',str(LIB/'contribute.mjs'),'zkey',str(directory/'DEV_initial.zkey'),str(directory/'DEVELOPMENT_ONLY.zkey')],f'contribute_{n}')
        run(['node',str(CLI),'zkey','export','verificationkey',str(directory/'DEVELOPMENT_ONLY.zkey'),str(directory/'verification_key.json')],f'vk_{n}')
        evidence['circuits'][str(n)]['proving_key_bytes']=(directory/'DEVELOPMENT_ONLY.zkey').stat().st_size
        target.write_text(json.dumps(evidence,indent=2)+'\n')

if __name__=='__main__':main()
