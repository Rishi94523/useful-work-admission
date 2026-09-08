import json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.process_measure import measured_run
out=ROOT/'docs/evaluation/docking_lightweight_2026-09-07';base=ROOT/'tmp/docking-audit';results=[];extended='--extended' in sys.argv
for name,args in [('node',[]),('chrome',['--browser'])]:
    if extended:args.append('--extended')
    log=base/(name+('-extended' if extended else '')+'-bench.log')
    result=measured_run([shutil.which('node'),str(ROOT/'scripts/benchmark_lightweight_browser.mjs'),*args],log,tree=True,timeout=900,private_cap=4*1024**3)
    results.append({'runtime':name,**result});print(name,result,flush=True)
    if result['exit_code']!=0:raise RuntimeError(log.read_text())
(out/('process_memory_extended.json' if extended else 'process_memory.json')).write_text(json.dumps(results,indent=2)+'\n')
