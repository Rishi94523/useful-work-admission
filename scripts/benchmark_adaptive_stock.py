"""Stock E8 control of every independently prepared pilot molecule, resumable."""
import argparse,json,re,subprocess,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/adaptive_docking_2026-09-08';TMP=ROOT/'tmp/adaptive-docking'
args_parser=argparse.ArgumentParser();args_parser.add_argument('--workers',type=int,default=3);args_parser.add_argument('--output',default='stock.jsonl');args_parser.add_argument('--converged-crystal',action='store_true');args_parser.add_argument('--converged-all',action='store_true');options=args_parser.parse_args()
is_converged=options.converged_crystal or options.converged_all
if is_converged and options.output=='stock.jsonl':raise ValueError('Converged follow-up needs a separate output filename')
if not 1<=options.workers<=4:raise ValueError('Use one to four independent stock processes')
if Path(options.output).name!=options.output:raise ValueError('Output must be a filename')
targets=json.loads((OUT/'science_inputs.json').read_text())['targets'];dest=OUT/options.output
if is_converged:
 converged=json.loads((OUT/'converged_inputs.json').read_text())['rows']
 for target in targets:
  if target.get('preparation_failed'):continue
  ligands=[l for l in target['ligands'] if options.converged_all or l['id']=='crystal']
  for ligand in ligands:ligand['independent']=next(r for r in converged if r['target']==target['target'] and r['id']==ligand['id'])
  target['ligands']=ligands
if options.converged_all and not dest.exists() and (OUT/'stock_converged_crystal.jsonl').exists():
 prior=[json.loads(x) for x in (OUT/'stock_converged_crystal.jsonl').read_text().splitlines()]
 for r in prior:
  source=next(x for x in converged if x['target']==r['target'] and x['id']==r['id']);assert r['input_sha256']==source['sha256']
 dest.write_text(''.join(json.dumps(r)+'\n' for r in prior))
done={r['key'] for r in map(json.loads,dest.read_text().splitlines())} if dest.exists() else set()
jobs=[]
for target in targets:
 if target.get('preparation_failed'):continue
 for ligand in target['ligands']:
  for conformer in (['source','independent'] if ligand['id']=='crystal' and not is_converged else ['independent']):
   key=':'.join([target['target'],ligand['id'],conformer]);
   if key in done:continue
   jobs.append((target,ligand,conformer,key))
def run(job):
   target,ligand,conformer,key=job
   pose=TMP/target['target']/(ligand['id']+'_'+conformer+'_'+Path(options.output).stem+'.pdbqt')
   args=[str(ROOT/'tmp/docking-pilot/native/vina_1.2.7_win.exe'),'--receptor',str(ROOT/target['receptor']),'--ligand',str(ROOT/ligand[conformer]['path']),'--cpu','1','--seed','104729','--exhaustiveness','8','--num_modes','9','--out',str(pose)]
   for axis,c in zip('xyz',target['center']):args+=['--center_'+axis,str(c),'--size_'+axis,'30']
   t=time.perf_counter();row={'key':key,'target':target['target'],'id':ligand['id'],'label':ligand['label'],'conformer':conformer,'input_sha256':ligand[conformer]['sha256'],'cpu_per_process':1,'concurrent_quality_workers':options.workers,'isolated_timing':options.workers==1}
   try:
    p=subprocess.run(args,capture_output=True,text=True,timeout=600)
    if p.returncode:raise RuntimeError((p.stdout+p.stderr)[-1500:])
    text=pose.read_text().split('ENDMDL')[0]+'ENDMDL\n';row.update(ok=True,pose=text,score=float(re.search(r'REMARK VINA RESULT:\s+([-0-9.]+)',text).group(1)))
   except Exception as e:row.update(ok=False,error=str(e))
   row['wall_ms']=(time.perf_counter()-t)*1000
   return row
with ThreadPoolExecutor(max_workers=options.workers) as pool:
 for future in as_completed([pool.submit(run,job) for job in jobs]):
  row=future.result()
  with dest.open('a') as f:f.write(json.dumps(row)+'\n')
  print(row['key'],row['ok'],round(row['wall_ms']),flush=True)
