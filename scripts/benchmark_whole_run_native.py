"""Actual native independent runs and conventional E8 controls; resumable evidence."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tmp/docking-runs';OUT=ROOT/'docs/evaluation/docking_whole_runs_2026-09-08'
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--smoke',action='store_true');parser.add_argument('--controls',action='store_true');args=parser.parse_args()
    plan=json.loads((OUT/'plan.json').read_text());target=OUT/('native_smoke.json' if args.smoke else 'native_controls.json' if args.controls else 'native.json')
    data=json.loads(target.read_text()) if target.exists() and not args.smoke else {'rows':[],'initialization':[],'scope':'Native single-thread pinned Vina map objective, direct server seed for E1, default upstream seed splitting for E8. Warm search and ligand initialization separate.'}
    staged=target.with_suffix('.partial')
    if staged.exists() and not args.smoke:
        recovery=json.loads(staged.read_text())
        if len(recovery['rows'])>len(data['rows']):data=recovery
    ligands=plan['ligands'][:1] if args.smoke else plan['ligands'];t=time.perf_counter()
    p=subprocess.Popen([str(BASE/'whole_run.exe'),str(ROOT/'tmp/docking-audit/maps/fa10'),str(ROOT/ligands[0]['path'])],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    def reply():
        while True:
            line=p.stdout.readline()
            if not line:raise RuntimeError('worker stopped')
            if line.startswith('{'):return json.loads(line)
    def call(line):p.stdin.write(line+'\n');p.stdin.flush();return reply()
    init=reply();assert init['ok'],init;data['initialization'].append({'maps_first_ligand_ms':(time.perf_counter()-t)*1000})
    try:
        for l in ligands:
            t=time.perf_counter();r=call('LOAD '+str(ROOT/l['path']));assert r['ok'],r;data['initialization'].append({'id':l['id'],'ligand_ms':(time.perf_counter()-t)*1000})
            caps=[1000,4000] if args.smoke else [0] if args.controls else plan['caps']
            for cap in caps:
                seeds=plan['seeds'][:2] if args.smoke else plan['seeds'][:1] if args.controls else plan['seeds']
                for idx,seed in enumerate(seeds):
                    if any(x['id']==l['id'] and x['seed']==seed and x['cap']==cap for x in data['rows']):continue
                    t=time.perf_counter();r=call(f'{seed} {cap} {8 if args.controls else 1}');wall=(time.perf_counter()-t)*1000
                    row={'id':l['id'],'label':l['label'],'seed':seed,'run':idx,'cap':cap,'exhaustiveness':8 if args.controls else 1,'wall_ms':wall,**r};data['rows'].append(row)
                    if (idx+1)%8==0 or idx+1==len(seeds):
                        staged.write_text(json.dumps(data,indent=2)+'\n')
                        for retry in range(40):
                            try:staged.replace(target);break
                            except PermissionError:
                                if retry==39:raise
                                time.sleep(.25)
                print(l['id'],cap,len(data['rows']),round(data['rows'][-1].get('search_ms',0)),data['rows'][-1].get('score'),flush=True)
    finally:p.stdin.close();p.wait(timeout=10)
if __name__=='__main__':main()
