"""Native single-CPU docking scaling experiment; includes CLI startup and setup."""
import argparse
from pathlib import Path
import platform
import random
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.docking_pilot import CASES, CACHE, ROOT, case_spec, run_vina, save_result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--smoke', action='store_true')
    args=parser.parse_args()
    cases=[case_spec(x) for x in CASES]
    jobs=[(s,e,seed,1000) for s in cases for e in [1,2,4,8] for seed in [104729,130363,155921]]
    random.Random(20260906).shuffle(jobs)
    if args.smoke:
        jobs=[(cases[0],1,104729,1000)]
    else:
        jobs += [(s,1,seed,cap) for s in cases for seed in [104729,130363,155921] for cap in [100,10000]]
        jobs += [(cases[0],e,seed,0) for e in [1,2,4] for seed in [104729,130363,155921]]
    evidence={'scope':'Official native Vina 1.2.7, one CPU, fresh process per call; includes process launch, parsing and map/setup costs. Public benchmark pairs. No binding-discovery claim.', 'platform':platform.platform(), 'cpu':platform.processor(), 'rows':[]}
    filename='native_smoke.json' if args.smoke else 'native_scaling.json'
    for s,e,seed,cap in jobs:
        label=f"{s['id']}_e{e}_cap{cap}_seed{seed}"
        row=run_vina(s,label,exhaustiveness=e,max_evals=cap,seed=seed)
        evidence['rows'].append(row)
        print(row,flush=True)
        if row.get('pose_path'):
            check=run_vina(s,label+'_score',mode='score',ligand_path=ROOT/row['pose_path'])
            check['parent']=label
            evidence['rows'].append(check)
            print(check,flush=True)
        save_result(filename,evidence)
    save_result('browser_jobs.json',{'cases':cases, 'jobs':[dict(case=s['id'],exhaustiveness=e,max_evals=1000,seed=seed) for s in cases for e in [1,4] for seed in [104729,130363]]})


if __name__=='__main__':
    main()
