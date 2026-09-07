"""Real browser proving with an external process-tree memory sampler."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research.process_measure import measured_run
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tmp/docking-ladder';OUT=ROOT/'docs/evaluation/docking_ladder_2026-09-07'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--counts',nargs='+',type=int,default=[2,8,16,32,64]);parser.add_argument('--repeats',type=int,default=2);parser.add_argument('--cpd',action='store_true');args=parser.parse_args()
    evidence={'scope':'Fresh actual Chrome process per sample. Prove time includes local key/WASM fetch, excludes JS library load. Memory samples sum Node asset server and Chrome descendants over the entire run, and may double-count shared pages. Not isolated proof/WASM allocation or a phone benchmark.','rows':[]}
    for n in args.counts:
        for repeat in range(args.repeats):
            tag='cpd_browser' if args.cpd else 'browser'
            result=BASE/f'{tag}_{n}_{repeat}.json';log=BASE/f'{tag}_{n}_{repeat}.log';seed=str((20260907+repeat)%2**23 if args.cpd else 20260907+repeat)
            measure=measured_run(['node',str(ROOT/'scripts/docking_ladder_browser.mjs'),str(n),seed,str(result)]+(['--cpd'] if args.cpd else []),log,timeout=600,tree=True)
            row={'n':n,'repeat':repeat,'measurement':measure}
            if measure['exit_code']==0:row.update(json.loads(result.read_text()))
            evidence['rows'].append(row);(OUT/('cpd_browser.json' if args.cpd else 'browser_scaling.json')).write_text(json.dumps(evidence,indent=2)+'\n')
            print(json.dumps({k:v for k,v in row.items() if k in ['n','repeat','prove_ms','measurement']}),flush=True)
            if measure['exit_code']!=0:raise RuntimeError('Browser run failed; retained diagnostic')

if __name__=='__main__':main()
