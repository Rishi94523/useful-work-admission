"""Isolated Node proof timings for 16/64-candidate restricted protein design."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research.process_measure import measured_run
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tmp/docking-ladder/cpd';OUT=ROOT/'docs/evaluation/docking_ladder_2026-09-07'
evidence={'scope':'Real published CPD energy model restricted to a neighborhood of a known incumbent. Three fresh Node processes per tier. No browser timing in this file. Plain BigInt baseline excludes model parsing. Proving includes local key/witness load.','rows':[]}
for n in [16,64]:
    for repeat in range(3):
        start=(20260907+repeat)%2**23;result=BASE/f'proof_{n}_{repeat}.json'
        measured=measured_run(['node',str(ROOT/'scripts/cpd_search_prove.mjs'),str(n),str(start),str(result)],BASE/f'proof_{n}_{repeat}.log',timeout=180)
        if measured['exit_code']!=0:raise RuntimeError('Proof failed, see log')
        row={'repeat':repeat,'measurement':measured,**json.loads(result.read_text())};evidence['rows'].append(row)
        (OUT/'cpd_proofs.json').write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps({k:row[k] for k in ['n','repeat','prove_ms','feasible_candidates']}),flush=True)
