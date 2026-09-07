"""Run isolated prover measurements, preserving raw samples and memory limits."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research.process_measure import measured_run
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tmp/docking-ladder';OUT=ROOT/'docs/evaluation/docking_ladder_2026-09-07'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--counts',nargs='+',type=int,default=[2,8,16,32,64]);parser.add_argument('--repeats',type=int,default=3);args=parser.parse_args()
    target=OUT/'node_scaling.json'
    evidence={'scope':'Actual isolated Node fullProve of the original reduced contact circuit. Not a scientific docking workload. Peak memory covers process startup, reference execution, proving and checking; it is not proving-only allocation.','rows':[]}
    for n in args.counts:
        for repeat in range(args.repeats):
            result=BASE/f'node_{n}_{repeat}.json';log=BASE/f'node_{n}_{repeat}.log';seed=str(20260907+repeat)
            measured=measured_run(['node',str(ROOT/'scripts/docking_ladder_prove.mjs'),str(n),seed,str(result)],log,timeout=600)
            row={'n':n,'repeat':repeat,'measurement':measured}
            if measured['exit_code']==0:row.update(json.loads(result.read_text()))
            evidence['rows'].append(row);target.write_text(json.dumps(evidence,indent=2)+'\n')
            print(json.dumps({k:v for k,v in row.items() if k in ['n','repeat','prove_ms','measurement']}),flush=True)
            if measured['exit_code']!=0:raise RuntimeError('Proof run failed; retained diagnostic')

if __name__=='__main__':main()
